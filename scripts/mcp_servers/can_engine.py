"""Transmit engine for the Civic cluster's two CAN buses.

Kept free of MCP so it can be driven from a plain script or a REPL when the
bench needs poking at directly.

Two CANable2 adapters, slcan firmware:
    F-CAN  500 kbps  USB serial 208838614D4D   powertrain, chassis, HUD
    B-CAN  125 kbps  USB serial 207D387C4D4D   body bus, extended IDs

Which adapter is on which bus was determined empirically on 2026-08-15 by
sweeping bitrates and watching where traffic appeared -- F-CAN decodes only at
500 kbps with standard IDs, B-CAN only at 125 kbps with extended IDs. Note this
is the opposite of the ttyACM numbering, so the adapters are addressed by their
stable /dev/serial/by-id path rather than by ttyACM number, which shuffles on
replug.

Frames are transmitted on their own periods by a scheduler thread rather than
as fast as a loop happens to run, because the cluster times out frames
individually.
"""

import glob
import os
import threading
import time
from collections import deque

import can

# Frame transmit periods in milliseconds. Powertrain and chassis frames are fast,
# HUD and status frames are slow. These follow the cadence noted in
# PROJECT_STATUS and are a starting point, not measured truth -- retune at
# runtime with set_period() if the cluster complains.
DEFAULT_PERIODS_MS = {
    0x158: 10,   # ENGINE_DATA
    0x17C: 10,   # POWERTRAIN_DATA
    0x1DC: 10,   # RPM_DATA
    0x1A4: 10,   # VSA_STATUS
    0x1AB: 10,   # STEER_MOTOR_TORQUE
    0x1FA: 10,   # BRAKE_COMMAND
    0x1C2: 100,  # EPB_STATUS
    0x30C: 100,  # ACC_HUD
    0x33D: 100,  # LKAS_HUD
    0x324: 100,  # CRUISE
    0x39F: 100,  # RADAR_HUD
    0x305: 100,  # SEATBELT_STATUS
    0x35E: 100,  # HIGHBEAM_CONTROL
}

FCAN = "fcan"
BCAN = "bcan"

# USB serial numbers of the two CANable2 adapters, and the ttyACM they happened
# to enumerate as when this was written -- the fallback only, if by-id is gone.
ADAPTERS = {
    FCAN: {"serial": "208838614D4D", "fallback": "/dev/ttyACM2", "bitrate": 500000},
    BCAN: {"serial": "207D387C4D4D", "fallback": "/dev/ttyACM1", "bitrate": 125000},
}


def resolve_channel(serial_short, fallback):
    """Find an adapter by USB serial, falling back to a fixed device node."""
    for link in glob.glob("/dev/serial/by-id/*CANable2*"):
        if serial_short in link:
            return os.path.realpath(link)
    return fallback


BUS_DEFAULTS = {
    name: {
        "channel": resolve_channel(cfg["serial"], cfg["fallback"]),
        "bitrate": cfg["bitrate"],
    }
    for name, cfg in ADAPTERS.items()
}


class BusError(Exception):
    pass


class ClusterBus:
    """One CANable adapter, plus a rolling capture of everything it hears."""

    def __init__(self, name, channel, bitrate, capture_depth=4000):
        self.name = name
        self.channel = channel
        self.bitrate = bitrate
        self.bus = None
        self.tx_count = 0
        self.tx_errors = 0

        self._lock = threading.Lock()
        self._capture = deque(maxlen=capture_depth)
        self._notifier = None
        self._listener = None

    @property
    def is_open(self):
        return self.bus is not None

    def open(self):
        if self.is_open:
            return
        try:
            self.bus = can.interface.Bus(
                interface="slcan",
                channel=self.channel,
                bitrate=self.bitrate,
                receive_own_messages=False,
            )
        except Exception as exc:
            raise BusError(f"could not open {self.name} on {self.channel}: {exc}") from exc

        self._listener = _CaptureListener(self._capture, self._lock)
        self._notifier = can.Notifier(self.bus, [self._listener])

    def close(self):
        if self._notifier is not None:
            self._notifier.stop()
            self._notifier = None
        if self.bus is not None:
            try:
                self.bus.shutdown()
            finally:
                self.bus = None

    def send(self, arbitration_id, data, extended=False):
        if not self.is_open:
            raise BusError(f"{self.name} is not open")

        msg = can.Message(
            arbitration_id=arbitration_id,
            data=bytearray(data),
            is_extended_id=extended,
        )
        try:
            self.bus.send(msg, timeout=0.1)
            self.tx_count += 1
        except can.CanError as exc:
            self.tx_errors += 1
            raise BusError(f"{self.name} send failed for 0x{arbitration_id:X}: {exc}") from exc

    def captured(self, clear=False):
        with self._lock:
            items = list(self._capture)
            if clear:
                self._capture.clear()
        return items

    def status(self):
        return {
            "bus": self.name,
            "channel": self.channel,
            "bitrate": self.bitrate,
            "open": self.is_open,
            "tx_frames": self.tx_count,
            "tx_errors": self.tx_errors,
            "captured": len(self._capture),
        }


class _CaptureListener(can.Listener):
    def __init__(self, capture, lock):
        self._capture = capture
        self._lock = lock

    def on_message_received(self, msg):
        with self._lock:
            self._capture.append(
                {
                    "t": msg.timestamp,
                    "id": msg.arbitration_id,
                    "extended": msg.is_extended_id,
                    "dlc": msg.dlc,
                    "data": bytes(msg.data),
                }
            )


class Broadcaster:
    """Schedules the registered frames onto a bus, each on its own period.

    Frames can be enabled and disabled individually while running, which is the
    point -- it lets a warning lamp be attributed to one frame without
    restarting anything.
    """

    def __init__(self, bus):
        self.bus = bus
        self.frames = {}       # arbitration id -> frame instance
        self.periods = {}      # arbitration id -> seconds
        self.enabled = set()
        self.tx_by_id = {}

        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self.last_error = None

    def register(self, frame, period_ms, enabled=True):
        with self._lock:
            self.frames[frame.id] = frame
            self.periods[frame.id] = period_ms / 1000.0
            self.tx_by_id.setdefault(frame.id, 0)
            if enabled:
                self.enabled.add(frame.id)
            else:
                self.enabled.discard(frame.id)

    def set_enabled(self, arbitration_id, on):
        with self._lock:
            if arbitration_id not in self.frames:
                raise BusError(f"0x{arbitration_id:X} is not registered")
            if on:
                self.enabled.add(arbitration_id)
            else:
                self.enabled.discard(arbitration_id)

    def set_period(self, arbitration_id, period_ms):
        with self._lock:
            if arbitration_id not in self.frames:
                raise BusError(f"0x{arbitration_id:X} is not registered")
            self.periods[arbitration_id] = period_ms / 1000.0

    def frame(self, arbitration_id):
        with self._lock:
            return self.frames.get(arbitration_id)

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return
        if not self.bus.is_open:
            raise BusError(f"{self.bus.name} is not open")
        self._stop.clear()
        self.last_error = None
        self._thread = threading.Thread(target=self._run, name=f"tx-{self.bus.name}", daemon=True)
        self._thread.start()

    def stop(self, timeout=2.0):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self):
        due = {}
        now = time.monotonic()
        with self._lock:
            for fid in self.frames:
                due[fid] = now

        while not self._stop.is_set():
            now = time.monotonic()
            next_wake = now + 0.05

            with self._lock:
                active = list(self.enabled)
                periods = dict(self.periods)
                frames = dict(self.frames)

            for fid in active:
                period = periods.get(fid, 0.1)
                when = due.setdefault(fid, now)

                if now >= when:
                    try:
                        frame = frames[fid]
                        self.bus.send(
                            fid, frame.encode(), extended=getattr(frame, "extended", False)
                        )
                        self.tx_by_id[fid] = self.tx_by_id.get(fid, 0) + 1
                    except BusError as exc:
                        self.last_error = str(exc)

                    # Re-base rather than accumulate drift if we fell behind.
                    when = when + period
                    if when < now:
                        when = now + period
                    due[fid] = when

                next_wake = min(next_wake, due[fid])

            sleep_for = next_wake - time.monotonic()
            if sleep_for > 0:
                self._stop.wait(sleep_for)

    def status(self):
        with self._lock:
            return {
                "running": self.running,
                "last_error": self.last_error,
                "frames": [
                    {
                        "id": f"0x{fid:03X}",
                        "name": type(self.frames[fid]).__name__,
                        "dlc": self.frames[fid].dlc,
                        "period_ms": round(self.periods[fid] * 1000),
                        "enabled": fid in self.enabled,
                        "sent": self.tx_by_id.get(fid, 0),
                    }
                    for fid in sorted(self.frames)
                ],
            }
