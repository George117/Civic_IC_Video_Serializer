"""MCP server for the ESP8266 sitting on the serializer's I2C bus.

A thin wrapper over the serial CLI already flashed to the ESP -- the firmware
does the work, this just makes it reachable without a serial monitor.

The ESP is the CH340 device, /dev/ttyUSB0 at 115200.

Two firmwares exist for this board and their command letters CONFLICT:

    ub925_link    'l' = link status     'w <reg> <v>' = write 925
    ub925_sweep   'l' = timing table    'W <reg> <v>' = write 925

Sending the wrong letter silently does the wrong thing rather than erroring, so
the firmware is detected from its own help text at open and commands are mapped
accordingly. esp_firmware() reports what was found.

Note: opening the port generally resets the ESP8266 -- the auto-reset circuit is
wired to DTR/RTS and the CH340 asserts them on open. DTR and RTS are held
deasserted here to reduce that, but expect a reboot. On ub925_sweep that is
harmless: it runs its cold-start bring-up automatically on boot.
"""

import time

import serial
from mcp.server import MCPServer

mcp = MCPServer("civic-esp")

DEFAULT_PORT = "/dev/ttyUSB0"
BAUD = 115200

# Response quiets down between commands; treat a gap this long as end-of-reply.
QUIET_S = 0.3

# Command letters per firmware. None means the firmware has no equivalent.
FIRMWARES = {
    "ub925_sweep": {
        "detect": ("auto sweep", "list timing table", "start/stop auto sweep"),
        "cold_start": "C",
        "status": "s",
        "link_status": "s",
        "des_status": "s",
        "dump": None,
        "read_925": "r {reg}",
        "write_925": "W {reg} {val}",
        "read_302": "y {reg}",
        "write_302": "Y {reg} {val}",
        "patgen_off": "z",
    },
    "ub925_link": {
        "detect": ("MODE_SEL strap check", "full check (read-only)", "link + backchannel"),
        "cold_start": "C",
        "status": "a",
        "link_status": "l",
        "des_status": "S",
        "dump": "d",
        "read_925": "r {reg}",
        "write_925": "w {reg} {val}",
        "read_302": "y {reg}",
        "write_302": "Y {reg} {val}",
        "patgen_off": "z",
    },
    # Runs on an ESP wired to the 302's LOCAL I2C (pins 2/3), not on the
    # serializer. So there is no 925 on this bus, and the "302" actions are
    # plain direct register access rather than tunnelled through the link --
    # which is the point: this board still works when the FPD-Link back
    # channel is down. See PROJECT_STATUS finding 5 on not running this
    # concurrently with the 925's pass-through.
    "ub302_patgen": {
        "detect": ("read indirect register", "outputs on + patgen white",
                   "custom timing example"),
        "cold_start": None,
        "status": "s",
        "link_status": "s",
        "des_status": "s",
        "dump": "d",
        "read_925": None,
        "write_925": None,
        "read_302": "r {reg}",
        "write_302": "w {reg} {val}",
        "patgen_off": "z",
    },
}

PATTERNS = {"white": "1", "black": "2", "red": "3", "green": "4", "blue": "5", "ramp": "6"}


class EspError(Exception):
    pass


class Esp:
    def __init__(self, port=DEFAULT_PORT):
        self.port = port
        self.ser = None
        self.firmware = None
        self.help_text = ""

    @property
    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def open(self):
        if self.is_open:
            return
        try:
            ser = serial.Serial()
            ser.port = self.port
            ser.baudrate = BAUD
            ser.timeout = 0.1
            ser.dtr = False
            ser.rts = False
            ser.open()
        except Exception as exc:
            raise EspError(f"could not open {self.port}: {exc}") from exc

        self.ser = ser
        # The board usually reboots on open; let its banner finish before asking
        # anything, otherwise the boot text gets mistaken for a command reply.
        time.sleep(1.5)
        self.ser.reset_input_buffer()
        self._detect()

    def _detect(self):
        self.help_text = self.command("h", timeout=8.0)
        low = self.help_text.lower()

        for name, spec in FIRMWARES.items():
            if any(marker.lower() in low for marker in spec["detect"]):
                self.firmware = name
                return

        self.firmware = None

    def cmd_for(self, action):
        if self.firmware is None:
            raise EspError(
                "firmware not identified - use esp_command to drive it directly, "
                "or esp_firmware() to see the help text that was returned"
            )
        letter = FIRMWARES[self.firmware].get(action)
        if letter is None:
            raise EspError(f"{self.firmware} has no '{action}' command")
        return letter

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            finally:
                self.ser = None
                self.firmware = None

    def command(self, line, timeout=5.0):
        if not self.is_open:
            self.open()

        self.ser.reset_input_buffer()
        self.ser.write((line + "\n").encode())
        self.ser.flush()

        chunks = []
        deadline = time.monotonic() + timeout
        last_data = time.monotonic()

        while time.monotonic() < deadline:
            waiting = self.ser.in_waiting
            if waiting:
                chunks.append(self.ser.read(waiting))
                last_data = time.monotonic()
            elif chunks and (time.monotonic() - last_data) > QUIET_S:
                break
            else:
                time.sleep(0.02)

        return b"".join(chunks).decode("utf-8", errors="replace").strip()


ESP = Esp()


@mcp.tool()
def esp_status() -> dict:
    """Report the serial port state and which firmware was detected."""
    return {
        "port": ESP.port,
        "baud": BAUD,
        "open": ESP.is_open,
        "firmware": ESP.firmware,
    }


@mcp.tool()
def esp_open(port: str = DEFAULT_PORT) -> dict:
    """Open the ESP serial port and identify the firmware.

    The board will most likely reboot as the port opens.
    """
    ESP.port = port
    ESP.open()
    return {"port": ESP.port, "open": ESP.is_open, "firmware": ESP.firmware}


@mcp.tool()
def esp_close() -> dict:
    """Close the ESP serial port."""
    ESP.close()
    return {"open": ESP.is_open}


@mcp.tool()
def esp_firmware() -> dict:
    """Which firmware is flashed, plus its full help text."""
    if not ESP.is_open:
        ESP.open()
    return {"firmware": ESP.firmware, "help": ESP.help_text}


@mcp.tool()
def esp_command(command: str, timeout: float = 5.0) -> str:
    """Send a raw command to the firmware CLI and return its output.

    The escape hatch: every command is reachable this way, including ones the
    named tools below do not cover. Check esp_firmware() first so the letters
    mean what you expect.
    """
    if timeout < 0.5 or timeout > 60:
        raise EspError("timeout must be between 0.5 and 60 seconds")
    return ESP.command(command, timeout=timeout)


@mcp.tool()
def esp_cold_start() -> str:
    """Run the full cold-start bring-up ('C').

    Verifies the MODE_SEL strap, selects the 25 MHz internal oscillator, enables
    I2C pass-through and turns the 302's outputs on. This is the sequence
    PROJECT_STATUS records as confirmed working.
    """
    if not ESP.is_open:
        ESP.open()
    return ESP.command(ESP.cmd_for("cold_start"), timeout=25.0)


@mcp.tool()
def esp_check() -> str:
    """Read-only status: identity, straps, link, config."""
    if not ESP.is_open:
        ESP.open()
    return ESP.command(ESP.cmd_for("status"), timeout=12.0)


@mcp.tool()
def esp_link_status() -> str:
    """Serializer link status."""
    if not ESP.is_open:
        ESP.open()
    return ESP.command(ESP.cmd_for("link_status"), timeout=8.0)


@mcp.tool()
def esp_des_status() -> str:
    """Deserializer (302) status through the link. Needs pass-through on."""
    if not ESP.is_open:
        ESP.open()
    return ESP.command(ESP.cmd_for("des_status"), timeout=8.0)


@mcp.tool()
def esp_patgen(pattern: str = "white") -> str:
    """Drive the serializer's test pattern generator.

    pattern: white, black, red, green, blue, ramp, or off.
    """
    if not ESP.is_open:
        ESP.open()

    key = pattern.strip().lower()
    if key == "off":
        return ESP.command(ESP.cmd_for("patgen_off"), timeout=10.0)
    if key not in PATTERNS:
        raise EspError(
            f"unknown pattern '{pattern}', expected one of {', '.join(PATTERNS)}, off"
        )
    return ESP.command(PATTERNS[key], timeout=10.0)


@mcp.tool()
def esp_read_reg(reg: str, device: str = "925") -> str:
    """Read a register. device: '925' (serializer) or '302' (through the link).

    reg is hex, with or without the 0x prefix.
    """
    if not ESP.is_open:
        ESP.open()

    value = reg.strip().lower().removeprefix("0x")
    dev = device.strip()
    if dev not in ("925", "302"):
        raise EspError(f"unknown device '{device}', expected '925' or '302'")

    return ESP.command(ESP.cmd_for(f"read_{dev}").format(reg=value), timeout=6.0)


@mcp.tool()
def esp_write_reg(reg: str, value: str, device: str = "925") -> str:
    """Write a register. device: '925' or '302'. Both arguments are hex."""
    if not ESP.is_open:
        ESP.open()

    r = reg.strip().lower().removeprefix("0x")
    v = value.strip().lower().removeprefix("0x")
    dev = device.strip()
    if dev not in ("925", "302"):
        raise EspError(f"unknown device '{device}', expected '925' or '302'")

    return ESP.command(ESP.cmd_for(f"write_{dev}").format(reg=r, val=v), timeout=6.0)


# --- ub925_sweep specific -------------------------------------------------
# The video-timing search. Only meaningful on the sweep firmware.


def _require_sweep():
    if not ESP.is_open:
        ESP.open()
    if ESP.firmware != "ub925_sweep":
        raise EspError(f"this tool needs ub925_sweep, but {ESP.firmware} is flashed")


@mcp.tool()
def esp_timing_list() -> str:
    """List the candidate video timings in the sweep table."""
    _require_sweep()
    return ESP.command("l", timeout=8.0)


@mcp.tool()
def esp_timing_select(entry: int) -> str:
    """Jump to timing table entry n and apply it."""
    _require_sweep()
    if entry < 1 or entry > 20:
        raise EspError("entry must be between 1 and 20 - run esp_timing_list() to see them")
    return ESP.command(f"j {entry}", timeout=15.0)


@mcp.tool()
def esp_timing_step(direction: str = "next") -> str:
    """Step to the next or previous timing. direction: 'next' or 'prev'."""
    _require_sweep()
    key = direction.strip().lower()
    if key in ("next", "n"):
        return ESP.command("n", timeout=15.0)
    if key in ("prev", "previous", "b"):
        return ESP.command("b", timeout=15.0)
    raise EspError(f"unknown direction '{direction}', expected 'next' or 'prev'")


@mcp.tool()
def esp_set_oscillator(mhz: int) -> str:
    """Force the serializer oscillator: 25 or 33 MHz, then re-apply the timing."""
    _require_sweep()
    if mhz not in (25, 33):
        raise EspError("oscillator must be 25 or 33 MHz")
    return ESP.command(f"o {mhz}", timeout=15.0)


@mcp.tool()
def esp_set_divider(divider: int) -> str:
    """Set the PGCDC divider (2-63), then re-apply the timing.

    This is the empirical knob -- AN-2198 documents a 200 MHz internal
    oscillator for the 92x parts, but the 925/302 pairing is not in that table,
    so the real pixel clock is unconfirmed. Sweep it if the image rolls.
    """
    _require_sweep()
    if divider < 2 or divider > 63:
        raise EspError("divider must be between 2 and 63")
    return ESP.command(f"D {divider}", timeout=15.0)


if __name__ == "__main__":
    mcp.run()
