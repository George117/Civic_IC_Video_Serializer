#!/usr/bin/env python3
"""Diff the inter-board state block between video-present (A) and video-absent (B).

Per finding 21's validated procedure: capture twice per state, then report only
positions that differ A-vs-B in BOTH repeats AND are stable within each state.
Anything else is churn (sequence counters, noise).
"""
import re, subprocess, sys
from collections import defaultdict

FILES = {"A1": "A1.sr", "A2": "A2.sr", "B1": "B1.sr", "B2": "B2.sr"}
HDR = [0x10, 0x02]          # shared framing header, finding 21


def run(path, args, ann):
    out = subprocess.run(["sigrok-cli", "-i", path, "-P", args, "-A", ann],
                         capture_output=True, text=True).stdout
    return [int(m, 16) for m in re.findall(r":\s*([0-9A-Fa-f]{2})\s*$", out, re.M)]


def frames(bs):
    """Split a byte stream on the 10 02 header."""
    idx = [i for i in range(len(bs) - 1) if bs[i] == HDR[0] and bs[i + 1] == HDR[1]]
    out = []
    for a, b in zip(idx, idx[1:]):
        if b - a > 16:
            out.append(bs[a:b])
    return out


def profile(fr):
    """Per-offset set of values seen across frames -> {offset: {values}}."""
    d = defaultdict(set)
    for f in fr:
        for i, v in enumerate(f):
            d[i].add(v)
    return d


def analyse(label, args, ann):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    prof, nfr = {}, {}
    for k, f in FILES.items():
        bs = run(f, args, ann)
        fr = frames(bs)
        prof[k], nfr[k] = profile(fr), len(fr)
        lens = sorted({len(x) for x in fr})
        print(f"  {k}: {len(bs):>6} bytes, {len(fr)} frames, frame lens {lens[:6]}")

    if not all(nfr.values()):
        print("  !! a capture yielded no frames - cannot diff")
        return

    # Positions stable within each capture AND identical across the two repeats
    # of a state, but different between states.
    n = min(max(prof[k]) for k in prof) + 1
    hits, churn = [], 0
    for i in range(n):
        va1, va2 = prof["A1"].get(i, set()), prof["A2"].get(i, set())
        vb1, vb2 = prof["B1"].get(i, set()), prof["B2"].get(i, set())
        if not (va1 and va2 and vb1 and vb2):
            continue
        stable = all(len(v) == 1 for v in (va1, va2, vb1, vb2))
        if not stable:
            churn += 1
            continue
        a, b = va1 | va2, vb1 | vb2
        if len(a) == 1 and len(b) == 1 and a != b:
            hits.append((i, a.pop(), b.pop()))

    print(f"\n  compared {n} offsets; {churn} vary within a state (counters/noise)")
    if hits:
        print(f"\n  *** {len(hits)} POSITIONS TRACK VIDEO PRESENCE ***")
        print(f"  {'offset':>7}  {'video ON':>8}  {'video OFF':>9}")
        for i, a, b in hits:
            print(f"  {i:>7}  {a:>802X}  {b:>902X}")
    else:
        print("\n  NO position differs consistently between video ON and OFF.")


analyse("LINK A - SPI (clk=0 mosi=1 cs=2, mode 0)",
        "spi:clk=0:mosi=1:cs=2:cpol=0:cpha=0", "spi=mosi-data")
analyse("LINK B - I2C 0x51 (scl=3 sda=4)",
        "i2c:scl=3:sda=4", "i2c=data-write")
