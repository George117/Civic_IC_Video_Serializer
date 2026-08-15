"""Broadcast the reversed F-CAN frames at the cluster, and report as it runs.

Standalone bench runner for when the MCP server is not loaded. Same engine, so
behaviour matches what the civic-can tools do.

    python3 scripts/fcan_broadcast.py [--seconds N] [--rpm N] [--speed N]
    python3 scripts/fcan_broadcast.py --without SEATBELT_STATUS

--without disables one frame so a warning lamp can be attributed to it.
"""

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "mcp_servers"))
sys.path.insert(0, str(HERE / "rpi_can_control"))

import cluster_frames  # noqa: E402
from can_engine import BUS_DEFAULTS, DEFAULT_PERIODS_MS, FCAN, Broadcaster, ClusterBus  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=0, help="0 runs until interrupted")
    ap.add_argument("--rpm", type=int, default=0)
    ap.add_argument("--speed", type=int, default=0)
    ap.add_argument("--without", action="append", default=[],
                    help="frame name to disable, repeatable")
    args = ap.parse_args()

    cfg = BUS_DEFAULTS[FCAN]
    bus = ClusterBus(FCAN, cfg["channel"], cfg["bitrate"])
    bus.open()
    print(f"F-CAN open on {cfg['channel']} @ {cfg['bitrate']}")

    tx = Broadcaster(bus)
    for cls in cluster_frames.CLUSTER_FRAMES:
        tx.register(cls(), DEFAULT_PERIODS_MS.get(cls.id, 100))

    for name in args.without:
        for fid, frame in tx.frames.items():
            if name.lower() in type(frame).__name__.lower():
                tx.set_enabled(fid, False)
                print(f"disabled {type(frame).__name__} (0x{fid:03X})")

    tx.frame(cluster_frames.Frame_RPM_DATA.id).rpm = args.rpm
    tx.frame(cluster_frames.Frame_ENGINE_DATA.id).vehicle_speed = args.speed
    print(f"rpm={args.rpm} speed={args.speed} kph")

    enabled = sorted(tx.enabled)
    print(f"broadcasting {len(enabled)} frames: " + " ".join(f"0x{f:03X}" for f in enabled))
    print()

    tx.start()
    started = time.monotonic()

    try:
        while True:
            time.sleep(2.0)
            elapsed = time.monotonic() - started
            rx = len(bus.captured())
            print(f"  t={elapsed:6.1f}s  tx={bus.tx_count:6d}  tx_err={bus.tx_errors:4d}  "
                  f"rx_from_cluster={rx:5d}  last_error={tx.last_error}")

            if bus.tx_errors:
                print("  !! transmit errors - nothing is ACKing on this bus")
            if args.seconds and elapsed >= args.seconds:
                break
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        tx.stop()
        print(f"\nstopped. {bus.tx_count} frames sent, {bus.tx_errors} errors")
        bus.close()


if __name__ == "__main__":
    main()
