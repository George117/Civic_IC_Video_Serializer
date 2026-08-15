#!/usr/bin/env python3
"""Extract vTotal from a 2-channel .sr capture of HS + VS.

vTotal is the number of HS pulses per VS period. Counting them between
consecutive VS edges gives an exact integer per frame, which is immune to the
quantisation that makes edge-rate ratios useless here (VS has ~5 cycles in the
window, HS has ~2700).
"""
import re
import sys
import numpy as np
from pathlib import Path

d = Path(sys.argv[1] if len(sys.argv) > 1 else "vtotal_x")

meta = (d / "metadata").read_text()
rate = int(re.search(r"samplerate=(\d+) MHz", meta).group(1)) * 1_000_000
unitsize = int(re.search(r"unitsize=(\d+)", meta).group(1))
# probeN=<name>: Nth probe slot (1-based) carries bit N-1 of each sample word.
probes = {int(n): nm for n, nm in re.findall(r"probe(\d+)=(\S+)", meta)}
print(f"samplerate={rate/1e6:g} MHz  unitsize={unitsize}  probes={probes}")

chunks = sorted(d.glob("logic-1-*"), key=lambda p: int(p.name.rsplit("-", 1)[1]))
raw = b"".join(p.read_bytes() for p in chunks)
dtype = {1: np.uint8, 2: np.uint16, 4: np.uint32}[unitsize]
s = np.frombuffer(raw, dtype=dtype)
print(f"samples={s.size}  duration={s.size/rate*1e3:.3f} ms")

# Identify which bits actually toggle, rather than trusting the mapping.
active = [b for b in range(unitsize * 8) if len(np.unique((s >> b) & 1)) > 1]
print(f"toggling bits: {active}")
if len(active) != 2:
    sys.exit(f"expected 2 toggling bits, got {active}")

def edges(bit):
    v = ((s >> bit) & 1).astype(np.int8)
    dv = np.diff(v)
    return np.flatnonzero(dv < 0), np.flatnonzero(dv > 0), v

# The faster-toggling line is HS, the slower is VS.
counts = {b: int(np.count_nonzero(np.diff(((s >> b) & 1).astype(np.int8)))) for b in active}
hs_bit = max(counts, key=counts.get)
vs_bit = min(counts, key=counts.get)
print(f"HS = bit {hs_bit} ({counts[hs_bit]} edges)   VS = bit {vs_bit} ({counts[vs_bit]} edges)")

hs_fall, hs_rise, hs_v = edges(hs_bit)
vs_fall, vs_rise, vs_v = edges(vs_bit)

print(f"\nHS: {len(hs_fall)} falling edges, mean period "
      f"{np.mean(np.diff(hs_fall))/rate*1e6:.3f} us "
      f"({rate/np.mean(np.diff(hs_fall))/1e3:.3f} kHz)")
if len(vs_fall) > 1:
    vp = np.diff(vs_fall)
    print(f"VS: {len(vs_fall)} falling edges, mean period "
          f"{np.mean(vp)/rate*1e3:.4f} ms ({rate/np.mean(vp):.4f} Hz)")

# HS pulse width -> hsw in pixels (needs PCLK; reported in us here).
w = np.mean([hs_rise[np.searchsorted(hs_rise, f)] - f
             for f in hs_fall[:-1] if np.searchsorted(hs_rise, f) < len(hs_rise)])
print(f"HS pulse width: {w/rate*1e6:.4f} us")

print("\nvTotal = HS pulses per VS period:")
vt = []
for a, b in zip(vs_fall, vs_fall[1:]):
    n = int(np.count_nonzero((hs_fall > a) & (hs_fall <= b)))
    vt.append(n)
    print(f"  VS {a:>8} -> {b:>8}  ({(b-a)/rate*1e3:.4f} ms)   HS pulses = {n}")

if vt:
    u, c = np.unique(vt, return_counts=True)
    print(f"\nvTotal candidates: {dict(zip(u.tolist(), c.tolist()))}")
    print(f"MODE vTotal = {int(u[np.argmax(c)])}")
