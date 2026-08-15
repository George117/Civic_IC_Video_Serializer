"""Scan a CAN bus for ECUs that answer diagnostic requests.

The cluster broadcasts status but does not say what it is unhappy about. If a
diagnostic endpoint answers, stored DTCs turn "which lamp is lit" from something
a human has to look at into something that can be queried and diffed.

Method: send a well-formed ISO-TP single-frame request to each candidate request
ID and watch for any arbitration ID that is not part of the cluster's normal
broadcast. Requests used are read-only -- TesterPresent, OBD mode 01, and UDS
ReadDTCInformation. Nothing here writes to an ECU.

    python3 scripts/uds_scan.py --bus fcan
    python3 scripts/uds_scan.py --bus fcan --range 0x700 0x7FF
"""

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "mcp_servers"))
sys.path.insert(0, str(HERE / "rpi_can_control"))

from can_engine import BUS_DEFAULTS, ClusterBus  # noqa: E402

# Read-only probes. Each is an ISO-TP single frame: first nibble 0 = single
# frame, second nibble = payload length.
PROBES = [
    ("TesterPresent",      [0x02, 0x3E, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    ("OBD mode01 pid00",   [0x02, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
    ("UDS readDTC 19 02",  [0x03, 0x19, 0x02, 0xFF, 0x00, 0x00, 0x00, 0x00]),
    ("KWP readDTC 18 02",  [0x04, 0x18, 0x02, 0xFF, 0x00, 0x00, 0x00, 0x00]),
]


def baseline(bus, seconds):
    """Learn which IDs the bus emits on its own, so responses stand out."""
    bus.captured(clear=True)
    time.sleep(seconds)
    return {(m["id"], m["extended"]) for m in bus.captured()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bus", default="fcan", choices=["fcan", "bcan"])
    ap.add_argument("--range", nargs=2, default=["0x700", "0x7FF"],
                    help="inclusive request ID range, hex")
    ap.add_argument("--extended", action="store_true", help="send 29-bit request IDs")
    ap.add_argument("--settle", type=float, default=0.04,
                    help="seconds to wait for a reply after each probe")
    args = ap.parse_args()

    lo, hi = int(args.range[0], 16), int(args.range[1], 16)
    cfg = BUS_DEFAULTS[args.bus]
    bus = ClusterBus(args.bus, cfg["channel"], cfg["bitrate"], capture_depth=20000)
    bus.open()
    print(f"{args.bus} open on {cfg['channel']} @ {cfg['bitrate']}")

    print("learning baseline traffic (4s) ...")
    known = baseline(bus, 4.0)
    print(f"  {len(known)} IDs broadcast normally: "
          + " ".join(sorted(f"0x{i:X}" for i, _ in known)))
    print()

    print(f"probing 0x{lo:X}..0x{hi:X} with {len(PROBES)} request types "
          f"({(hi - lo + 1) * len(PROBES)} frames)")

    hits = {}
    for req_id in range(lo, hi + 1):
        for label, payload in PROBES:
            bus.captured(clear=True)
            try:
                bus.send(req_id, payload, extended=args.extended)
            except Exception as exc:
                print(f"  send failed at 0x{req_id:X}: {exc}")
                continue

            time.sleep(args.settle)

            for m in bus.captured():
                key = (m["id"], m["extended"])
                if key in known:
                    continue
                ids = f"0x{m['id']:08X}" if m["extended"] else f"0x{m['id']:03X}"
                rec = hits.setdefault((req_id, ids), [])
                entry = (label, m["data"].hex(" ").upper())
                if entry not in rec:
                    rec.append(entry)
                    print(f"  RESPONSE  req 0x{req_id:03X} -> {ids}  [{label}]  "
                          f"{m['data'].hex(' ').upper()}")

    print()
    if hits:
        print(f"=== {len(hits)} responding pair(s) ===")
        for (req, resp), entries in sorted(hits.items()):
            print(f"  request 0x{req:03X} -> response {resp}")
            for label, data in entries:
                print(f"      {label:20s} {data}")
    else:
        print("no diagnostic responders found in this range")

    bus.close()


if __name__ == "__main__":
    main()
