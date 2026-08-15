# Bench MCP servers

Two MCP servers that put the bench hardware behind tools, so the cluster can be
driven and probed one change at a time.

| Server | Hardware | Port |
|---|---|---|
| `civic-can` | 2x CANable2, slcan firmware | `/dev/ttyACM1` (F-CAN 500k), `/dev/ttyACM2` (B-CAN 125k) |
| `civic-esp` | ESP8266 on the serializer's I2C bus | `/dev/ttyUSB0` (CH340) @ 115200 |

Both are registered in `.mcp.json` at the repo root and run out of `.venv`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install "python-can==4.5.0" "mcp[cli]" pyserial
```

Your user needs to be in `dialout` for the serial devices.

---

## civic-can

Transmits the reversed F-CAN frames on a proper per-frame schedule and captures
what comes back.

**Bus control:** `can_status`, `can_open`, `can_close`
**Broadcast:** `cluster_start`, `cluster_stop`
**Live values:** `set_signal(rpm=, speed_kph=)`
**Per-frame:** `frame_enable`, `frame_period`, `frame_peek`
**Raw / B-CAN:** `send_raw`, `bcan_start`, `bcan_stop`
**Listen:** `sniff`

### Why per-frame enable exists

You are the only sensor for whether a warning lamp is lit. `frame_enable` lets a
lamp be attributed to a single frame without restarting anything: drop one
frame, look at the cluster, put it back. Same for `frame_period` when a frame is
being sent but at the wrong cadence.

`frame_peek` shows the exact bytes a frame would put on the wire, including the
counter and checksum nibbles, without transmitting and without advancing the
live counter.

### Frame periods

`can_engine.DEFAULT_PERIODS_MS` holds the schedule: 10 ms for powertrain and
chassis frames, 100 ms for HUD and status. These follow the cadence noted in
PROJECT_STATUS and are **a starting point, not measured truth** -- no capture
from a real car has confirmed them. Retune live with `frame_period`.

### Before transmitting

Check `sniff` sees traffic first. On a bus with no other node powered, nothing
ACKs the frames, the controller retransmits, and it drops to bus-off. That
looks like a software fault but is not one.

---

## civic-esp

Wraps the serial CLI already flashed to the ESP.

**Port:** `esp_status`, `esp_open`, `esp_close`, `esp_firmware`
**Bring-up:** `esp_cold_start`, `esp_check`, `esp_link_status`, `esp_des_status`
**Registers:** `esp_read_reg`, `esp_write_reg` (both take `device="925"` or `"302"`)
**Pattern:** `esp_patgen`
**Sweep firmware only:** `esp_timing_list`, `esp_timing_select`, `esp_timing_step`,
`esp_set_oscillator`, `esp_set_divider`
**Escape hatch:** `esp_command` sends any raw command

### Firmware detection matters

Two firmwares exist for this board and their command letters conflict:

| | `ub925_link` | `ub925_sweep` |
|---|---|---|
| `l` | link status | list timing table |
| write 925 register | `w <reg> <v>` | `W <reg> <v>` |
| status | `a` | `s` |

Sending the wrong letter does the wrong thing silently rather than erroring, so
the firmware is identified from its own help text when the port opens, and the
named tools map onto whichever is flashed. `esp_firmware()` reports what was
found. If detection fails, the named tools refuse to guess and `esp_command`
stays available.

### The port opens with a reset

The ESP8266 auto-reset circuit is wired to DTR/RTS and the CH340 asserts them on
open. DTR and RTS are held deasserted to reduce this, but expect a reboot. On
`ub925_sweep` that is harmless -- it runs its cold-start bring-up on boot, so the
link comes back up by itself.
