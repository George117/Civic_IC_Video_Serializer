"""MCP server for the Civic cluster's two CAN buses.

Exposes the transmit engine in can_engine.py as tools, so the cluster can be
driven and probed one change at a time.

F-CAN carries every frame reversed so far and is what the warning lamps watch.
B-CAN is opened and can send raw frames, but has no frame definitions yet --
that is the next milestone.
"""

import sys
from pathlib import Path

from mcp.server import MCPServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rpi_can_control"))

import bcan_frames  # noqa: E402
import cluster_frames  # noqa: E402
from can_engine import (  # noqa: E402
    BCAN,
    BUS_DEFAULTS,
    DEFAULT_PERIODS_MS,
    FCAN,
    Broadcaster,
    BusError,
    ClusterBus,
)

mcp = MCPServer("civic-can")

BUSES = {
    name: ClusterBus(name, cfg["channel"], cfg["bitrate"])
    for name, cfg in BUS_DEFAULTS.items()
}

FCAN_TX = Broadcaster(BUSES[FCAN])
BCAN_TX = Broadcaster(BUSES[BCAN])

for _cls in cluster_frames.CLUSTER_FRAMES:
    FCAN_TX.register(_cls(), DEFAULT_PERIODS_MS.get(_cls.id, 100))

# Empty until B-CAN frames are identified -- the scaffolding is here so the
# first one only needs a class in bcan_frames.py.
for _entry, _period in bcan_frames.BCAN_FRAMES:
    BCAN_TX.register(_entry() if isinstance(_entry, type) else _entry, _period)


def _bus(name):
    key = name.strip().lower()
    if key not in BUSES:
        raise BusError(f"unknown bus '{name}', expected 'fcan' or 'bcan'")
    return BUSES[key]


def _resolve_frame(ref):
    """Accept a frame name, a class name, or a hex/decimal arbitration ID."""
    text = str(ref).strip()

    for fid, frame in FCAN_TX.frames.items():
        cls_name = type(frame).__name__
        if text.lower() in (cls_name.lower(), cls_name.lower().replace("frame_", "")):
            return fid

    try:
        fid = int(text, 16) if text.lower().startswith("0x") else int(text, 0)
    except ValueError:
        raise BusError(f"no frame matches '{ref}'")

    if fid not in FCAN_TX.frames:
        raise BusError(f"0x{fid:X} is not a registered frame")
    return fid


def _parse_data(data_hex):
    cleaned = data_hex.replace("0x", "").replace(",", " ").replace(":", " ").strip()
    parts = cleaned.split()
    if len(parts) == 1 and len(parts[0]) % 2 == 0:
        parts = [parts[0][i:i + 2] for i in range(0, len(parts[0]), 2)]
    try:
        data = [int(p, 16) for p in parts]
    except ValueError:
        raise BusError(f"could not parse data bytes from '{data_hex}'")
    if any(b < 0 or b > 0xFF for b in data):
        raise BusError("data bytes must be 0x00-0xFF")
    if len(data) > 8:
        raise BusError("classic CAN carries at most 8 bytes")
    return data


@mcp.tool()
def can_status() -> dict:
    """Report both buses: open state, frame counts, and the F-CAN schedule."""
    return {
        "buses": [BUSES[FCAN].status(), BUSES[BCAN].status()],
        "fcan_broadcast": FCAN_TX.status(),
        "bcan_broadcast": {
            "running": BCAN_TX.running,
            "registered_frames": len(BCAN_TX.frames),
            "note": "scaffolding only - no B-CAN frames reversed yet",
        },
    }


@mcp.tool()
def can_open(bus: str = "both") -> dict:
    """Open a CAN adapter. bus: 'fcan', 'bcan', or 'both'.

    F-CAN is /dev/ttyACM1 at 500 kbps, B-CAN is /dev/ttyACM2 at 125 kbps.
    """
    targets = [FCAN, BCAN] if bus.strip().lower() == "both" else [_bus(bus).name]
    opened, failed = [], []

    for name in targets:
        try:
            BUSES[name].open()
            opened.append(name)
        except BusError as exc:
            failed.append(str(exc))

    return {"opened": opened, "failed": failed, "status": can_status()["buses"]}


@mcp.tool()
def can_close(bus: str = "both") -> dict:
    """Stop transmitting and close the adapter(s)."""
    targets = [FCAN, BCAN] if bus.strip().lower() == "both" else [_bus(bus).name]

    for name in targets:
        if name == FCAN:
            FCAN_TX.stop()
        else:
            BCAN_TX.stop()
        BUSES[name].close()

    return {"closed": targets}


@mcp.tool()
def cluster_start() -> dict:
    """Start broadcasting every enabled F-CAN frame on its own period.

    Opens F-CAN first if it is not already open.
    """
    if not BUSES[FCAN].is_open:
        BUSES[FCAN].open()
    FCAN_TX.start()
    return FCAN_TX.status()


@mcp.tool()
def cluster_stop() -> dict:
    """Stop broadcasting on F-CAN. Leaves the adapter open."""
    FCAN_TX.stop()
    return {"running": FCAN_TX.running}


@mcp.tool()
def set_signal(rpm: int | None = None, speed_kph: int | None = None) -> dict:
    """Set live gauge values. Takes effect on the next scheduled transmit."""
    changed = {}

    if rpm is not None:
        rpm = max(0, min(8000, int(rpm)))
        FCAN_TX.frame(cluster_frames.Frame_RPM_DATA.id).rpm = rpm
        changed["rpm"] = rpm

    if speed_kph is not None:
        speed_kph = max(0, min(300, int(speed_kph)))
        FCAN_TX.frame(cluster_frames.Frame_ENGINE_DATA.id).vehicle_speed = speed_kph
        changed["speed_kph"] = speed_kph

    return changed


@mcp.tool()
def frame_enable(frame: str, on: bool = True) -> dict:
    """Enable or disable one F-CAN frame while running.

    Use this to attribute a warning lamp to a single frame: drop one, look at
    the cluster, put it back.

    frame: a name like 'SEATBELT_STATUS' or an ID like '0x305'.
    """
    fid = _resolve_frame(frame)
    FCAN_TX.set_enabled(fid, on)
    return {
        "frame": type(FCAN_TX.frames[fid]).__name__,
        "id": f"0x{fid:03X}",
        "enabled": on,
    }


@mcp.tool()
def frame_period(frame: str, period_ms: int) -> dict:
    """Retune one frame's transmit period, in milliseconds."""
    if period_ms < 1 or period_ms > 10000:
        raise BusError("period_ms must be between 1 and 10000")
    fid = _resolve_frame(frame)
    FCAN_TX.set_period(fid, period_ms)
    return {
        "frame": type(FCAN_TX.frames[fid]).__name__,
        "id": f"0x{fid:03X}",
        "period_ms": period_ms,
    }


@mcp.tool()
def frame_peek(frame: str) -> dict:
    """Show the bytes a frame would put on the wire right now, without sending."""
    fid = _resolve_frame(frame)
    obj = FCAN_TX.frames[fid]
    saved_counter = obj.counter
    data = obj.encode()
    obj.counter = saved_counter  # peeking must not advance the live counter

    return {
        "frame": type(obj).__name__,
        "id": f"0x{fid:03X}",
        "dlc": obj.dlc,
        "data": " ".join(f"{b:02X}" for b in data),
        "counter": (data[obj.dlc - 1] >> 4) & 0x3,
        "checksum": data[obj.dlc - 1] & 0xF,
    }


@mcp.tool()
def send_raw(bus: str, can_id: str, data_hex: str, extended: bool = False) -> dict:
    """Send one arbitrary frame. Works on either bus.

    This is the B-CAN write path until real frame definitions exist.

    can_id: '0x305' or '305' (hex). data_hex: '00 11 22' or '001122'.
    """
    target = _bus(bus)
    if not target.is_open:
        target.open()

    text = can_id.strip()
    fid = int(text, 16)
    data = _parse_data(data_hex)

    target.send(fid, data, extended=extended)

    return {
        "bus": target.name,
        "id": f"0x{fid:X}",
        "extended": extended,
        "data": " ".join(f"{b:02X}" for b in data),
    }


@mcp.tool()
def bcan_start() -> dict:
    """Start broadcasting any registered B-CAN frames.

    Scaffolding: no frames are defined yet, so this transmits nothing until
    entries are added to BCAN_FRAMES in bcan_frames.py. Opens B-CAN first.
    """
    if not BUSES[BCAN].is_open:
        BUSES[BCAN].open()

    if not BCAN_TX.frames:
        return {
            "running": False,
            "registered_frames": 0,
            "note": "no B-CAN frames defined yet - add them to bcan_frames.BCAN_FRAMES",
        }

    BCAN_TX.start()
    return BCAN_TX.status()


@mcp.tool()
def bcan_stop() -> dict:
    """Stop broadcasting on B-CAN. Leaves the adapter open."""
    BCAN_TX.stop()
    return {"running": BCAN_TX.running}


@mcp.tool()
def sniff(bus: str = "bcan", seconds: float = 3.0, clear_first: bool = True) -> dict:
    """Listen on a bus and summarise what arrived, grouped by arbitration ID.

    Points at B-CAN by default -- that is where the cluster's extended frames
    were seen, and where the diagnostic layer would live.
    """
    import time as _time

    if seconds < 0.1 or seconds > 60:
        raise BusError("seconds must be between 0.1 and 60")

    target = _bus(bus)
    if not target.is_open:
        target.open()

    if clear_first:
        target.captured(clear=True)

    _time.sleep(seconds)
    msgs = target.captured()

    by_id = {}
    for m in msgs:
        key = (m["id"], m["extended"])
        entry = by_id.setdefault(
            key,
            {
                "id": f"0x{m['id']:08X}" if m["extended"] else f"0x{m['id']:03X}",
                "extended": m["extended"],
                "dlc": m["dlc"],
                "count": 0,
                "first_seen": m["t"],
                "last_seen": m["t"],
                "sample": m["data"].hex(" ").upper(),
                "payload_varies": False,
            },
        )
        entry["count"] += 1
        entry["last_seen"] = m["t"]
        if m["data"].hex(" ").upper() != entry["sample"]:
            entry["payload_varies"] = True

    rows = []
    for entry in by_id.values():
        span = entry["last_seen"] - entry["first_seen"]
        entry["approx_period_ms"] = (
            round(span * 1000 / (entry["count"] - 1)) if entry["count"] > 1 and span > 0 else None
        )
        del entry["first_seen"], entry["last_seen"]
        rows.append(entry)

    rows.sort(key=lambda r: (not r["extended"], -r["count"]))

    return {
        "bus": target.name,
        "listened_s": seconds,
        "total_frames": len(msgs),
        "unique_ids": len(rows),
        "extended_ids": sum(1 for r in rows if r["extended"]),
        "ids": rows,
    }


if __name__ == "__main__":
    mcp.run()
