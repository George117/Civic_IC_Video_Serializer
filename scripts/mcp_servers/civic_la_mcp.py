"""MCP server for the DreamSourceLab DSLogic Plus logic analyser.

A thin wrapper over sigrok-cli. The point of this server is not generic logic
capture -- it is to answer one question this project is stuck on: what does the
cluster's graphics IC write to the DS90UB302Q over its local I2C bus?

PROJECT_STATUS finding 14 proved the graphics IC is an active I2C master on that
bus, and that its writes are event-driven around MID menu changes. Polling only
samples the result; this captures the actual transactions.

Wiring (302 pinout from PROJECT_STATUS "Hardware"):
    302 pin 3 = SCL  -> DSLogic channel 0   (default)
    302 pin 2 = SDA  -> DSLogic channel 1   (default)
    302 GND          -> DSLogic GND         (essential -- no ground, no capture)

Do not add pull-ups; the cluster board already has 4.7k on both lines.

Before capturing, clear the 925's I2C pass-through (`925 0x03 = 0xD2`) so the
serializer is not also driving the bus -- otherwise the capture mixes the
graphics IC's traffic with the 925's forwarded transactions and you cannot tell
them apart. See PROJECT_STATUS findings 5 and 12.
"""

import os
import re
import shutil
import subprocess
import tempfile

from mcp.server import MCPServer

mcp = MCPServer("civic-la")

DRIVER = "dreamsourcelab-dslogic"
USB_ID = "2a0e:0020"  # DSLogic Plus, confirmed by lsusb on this bench

# The 302's 7-bit address. IDx strapped to 0 -> 0x2C (PROJECT_STATUS "Hardware").
DES_ADDR = 0x2C

DEFAULT_SCL = "0"
DEFAULT_SDA = "1"
DEFAULT_SAMPLERATE = "4m"  # ~10x oversampling of 400kHz I2C; plenty for 100kHz


class LaError(Exception):
    pass


def _sigrok(args, timeout=120.0):
    """Run sigrok-cli and return stdout, raising with stderr on failure."""
    exe = shutil.which("sigrok-cli")
    if not exe:
        raise LaError(
            "sigrok-cli is not installed. Install with:\n"
            "  sudo apt-get install -y sigrok-cli libsigrokdecode4"
        )
    try:
        proc = subprocess.run(
            [exe] + args, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise LaError(f"sigrok-cli timed out after {timeout}s: {' '.join(args)}")

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise LaError(f"sigrok-cli failed (exit {proc.returncode}): {err}")
    return proc.stdout


# --- diagnostics -----------------------------------------------------------


@mcp.tool()
def la_check() -> dict:
    """Diagnose the whole capture chain before you rely on it.

    Checks sigrok-cli, the I2C decoder, the USB device, the DSLogic firmware
    blobs, and permissions -- the four things that actually go wrong.
    """
    out = {}

    exe = shutil.which("sigrok-cli")
    out["sigrok_cli"] = exe or "NOT INSTALLED"
    if not exe:
        out["fix"] = "sudo apt-get install -y sigrok-cli libsigrokdecode4"
        return out

    out["version"] = _sigrok(["--version"]).splitlines()[0].strip()

    # USB presence is independent of sigrok -- check it separately so a missing
    # device is not misreported as a driver problem.
    lsusb = shutil.which("lsusb")
    if lsusb:
        listing = subprocess.run(
            [lsusb], capture_output=True, text=True
        ).stdout
        out["usb_present"] = USB_ID in listing
        if not out["usb_present"]:
            out["hint_usb"] = f"{USB_ID} (DSLogic Plus) not seen by lsusb - plug it in"

    # DSLogic needs firmware blobs extracted from DSView; libsigrok looks in
    # these directories. Absent firmware presents as "device not found".
    fw_dirs = [
        "/usr/share/sigrok-firmware",
        os.path.expanduser("~/.local/share/sigrok-firmware"),
    ]
    fw = []
    for d in fw_dirs:
        if os.path.isdir(d):
            fw += [f for f in os.listdir(d) if "dslogic" in f.lower()]
    out["dslogic_firmware"] = sorted(set(fw)) or "NONE FOUND"
    if not fw:
        out["hint_firmware"] = (
            "DSLogic firmware is not redistributable, so it must be extracted "
            "from DSView. See la_firmware_help()."
        )

    try:
        scan = _sigrok(["--driver", DRIVER, "--scan"], timeout=30.0)
        out["scan"] = scan.strip() or "(no devices found)"
        out["device_found"] = DRIVER in scan
    except LaError as exc:
        out["scan"] = str(exc)
        out["device_found"] = False

    try:
        decoders = _sigrok(["--list-supported"], timeout=30.0)
        out["i2c_decoder"] = bool(re.search(r"^\s*i2c\s", decoders, re.M))
    except LaError:
        out["i2c_decoder"] = "unknown"

    return out


@mcp.tool()
def la_firmware_help() -> str:
    """How to obtain the DSLogic firmware blobs libsigrok needs."""
    return (
        "libsigrok's dreamsourcelab-dslogic driver needs firmware that TI/DSL do\n"
        "not allow redistribution of, so it is not in the apt package. Without it\n"
        "the device enumerates on USB but --scan reports nothing.\n"
        "\n"
        "Extract it from DSView:\n"
        "  git clone https://github.com/sigrokproject/sigrok-util\n"
        "  cd sigrok-util/firmware/dreamsourcelab-dslogic\n"
        "  ./sigrok-fwextract-dreamsourcelab-dslogic <path-to-DSView-source-or-zip>\n"
        "\n"
        "That writes dreamsourcelab-dslogic-*.fw into the current directory.\n"
        "Install them where libsigrok looks:\n"
        "  mkdir -p ~/.local/share/sigrok-firmware\n"
        "  cp dreamsourcelab-dslogic-*.fw ~/.local/share/sigrok-firmware/\n"
        "\n"
        "Permissions: the apt package installs udev rules granting plugdev access.\n"
        "If --scan still finds nothing, replug the device, and confirm you are in\n"
        "the plugdev group (`id -nG`). A logged-out group change needs a re-login."
    )


@mcp.tool()
def la_decoders(match: str = "") -> str:
    """List available protocol decoders, optionally filtered by substring."""
    out = _sigrok(["--list-supported"], timeout=30.0)
    block = out.split("Supported protocol decoders:")
    if len(block) < 2:
        return out
    lines = [l for l in block[1].splitlines() if l.strip()]
    if match:
        lines = [l for l in lines if match.lower() in l.lower()]
    return "\n".join(lines) or f"(no decoder matching {match!r})"


# --- I2C parsing -----------------------------------------------------------


def _parse_i2c(text):
    """Turn sigrok's i2c annotation stream into structured transactions.

    sigrok-cli emits one annotation per line, e.g.
        i2c-1: Start
        i2c-1: Address write: 2C
        i2c-1: Data write: 02
        i2c-1: Stop
    We group Start..Stop into transactions, then interpret them as register
    access, which is what every device on this bus actually does.
    """
    txns, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        body = line.split(":", 1)[1].strip()
        low = body.lower()

        if low.startswith("start") and "repeat" not in low:
            cur = {"addr": None, "rw": None, "bytes": [], "repeated": False}
            continue
        if cur is None:
            continue
        if low.startswith("repeat start"):
            cur["repeated"] = True
            continue

        m = re.match(r"address (write|read):\s*([0-9A-Fa-f]{1,2})", body, re.I)
        if m:
            rw = m.group(1).lower()
            addr = int(m.group(2), 16)
            # On a repeated start the address repeats; keep the first, but the
            # direction of the *second* is what makes it a register read.
            if cur["addr"] is None:
                cur["addr"], cur["rw"] = addr, rw
            elif rw == "read":
                cur["rw"] = "read"
            continue

        m = re.match(r"data (write|read):\s*([0-9A-Fa-f]{1,2})", body, re.I)
        if m:
            cur["bytes"].append((m.group(1).lower(), int(m.group(2), 16)))
            continue

        if low.startswith("stop"):
            if cur["addr"] is not None:
                txns.append(cur)
            cur = None

    return txns


def _interpret(txn):
    """Render one transaction as register access where the shape allows it."""
    addr = txn["addr"]
    data = txn["bytes"]
    tag = f"0x{addr:02X}"

    if txn["rw"] == "read" and data:
        # reg pointer written, then data read back
        writes = [v for k, v in data if k == "write"]
        reads = [v for k, v in data if k == "read"]
        if writes and reads:
            regs = ", ".join(f"0x{v:02X}" for v in reads)
            return f"{tag}  READ  reg 0x{writes[0]:02X} -> {regs}"
        if reads:
            return f"{tag}  READ  {' '.join(f'0x{v:02X}' for v in reads)}"

    vals = [v for _, v in data]
    if len(vals) >= 2:
        payload = ", ".join(f"0x{v:02X}" for v in vals[1:])
        return f"{tag}  WRITE reg 0x{vals[0]:02X} = {payload}"
    if len(vals) == 1:
        return f"{tag}  WRITE 0x{vals[0]:02X}   (reg pointer set, no data)"
    return f"{tag}  {txn['rw'] or '?'}  (no data bytes)"


# --- capture ---------------------------------------------------------------


def _capture_args(samplerate, scl, sda, ms, samples, trigger, extra_config):
    args = ["--driver", DRIVER]
    cfg = [f"samplerate={samplerate}"]
    if extra_config:
        cfg += [c.strip() for c in extra_config.split(",") if c.strip()]
    args += ["--config", ":".join(cfg)]
    args += ["--channels", f"{scl},{sda}"]
    if samples:
        args += ["--samples", str(samples)]
    else:
        args += ["--time", str(ms)]
    if trigger:
        args += ["--triggers", trigger]
    return args


@mcp.tool()
def la_capture_i2c(
    seconds: float = 5.0,
    scl: str = DEFAULT_SCL,
    sda: str = DEFAULT_SDA,
    samplerate: str = DEFAULT_SAMPLERATE,
    address: str = "",
    trigger: str = "",
    raw: bool = False,
    extra_config: str = "",
) -> dict:
    """Capture the I2C bus and return decoded transactions.

    seconds: capture window. address: hex filter, e.g. '2C' for the 302 only.
    trigger: sigrok trigger spec, e.g. '1=f' for SDA falling (approximates an
    I2C start). raw: also return the undecoded annotation stream.

    Clear the 925's pass-through (925 0x03 = 0xD2) first, or the capture will
    contain the serializer's forwarded traffic as well as the graphics IC's.
    """
    if seconds <= 0 or seconds > 120:
        raise LaError("seconds must be between 0 and 120")

    ms = int(seconds * 1000)
    args = _capture_args(samplerate, scl, sda, ms, None, trigger, extra_config)
    args += ["-P", f"i2c:scl={scl}:sda={sda}", "-A", "i2c"]

    text = _sigrok(args, timeout=seconds + 60.0)
    txns = _parse_i2c(text)

    if address:
        want = int(address.replace("0x", ""), 16)
        txns = [t for t in txns if t["addr"] == want]

    lines = [_interpret(t) for t in txns]

    # Collapse consecutive identical transactions -- polling loops otherwise
    # bury the one-off writes that actually matter.
    collapsed, prev, count = [], None, 0
    for l in lines:
        if l == prev:
            count += 1
            continue
        if prev is not None:
            collapsed.append(prev + (f"   [x{count}]" if count > 1 else ""))
        prev, count = l, 1
    if prev is not None:
        collapsed.append(prev + (f"   [x{count}]" if count > 1 else ""))

    result = {
        "seconds": seconds,
        "samplerate": samplerate,
        "channels": {"scl": scl, "sda": sda},
        "address_filter": address or "(none)",
        "transactions": len(txns),
        "unique_lines": len(collapsed),
        "decoded": collapsed,
    }
    if not txns:
        result["hint"] = (
            "No I2C transactions decoded. Check: GND connected between DSLogic "
            "and cluster board; SCL/SDA channels not swapped (scl/sda args); "
            "the bus is actually active (the graphics IC writes are "
            "event-driven -- change MID menus during the capture)."
        )
    if raw:
        result["raw"] = text
    return result


@mcp.tool()
def la_watch_302(seconds: float = 10.0, scl: str = DEFAULT_SCL,
                 sda: str = DEFAULT_SDA) -> dict:
    """Capture only traffic addressed to the 302 (0x2C).

    The project-specific shortcut: this is the finding-14 experiment. Start it,
    then change MID menus while it runs, since that is the stimulus already
    known to provoke the graphics IC into writing.
    """
    return la_capture_i2c(
        seconds=seconds, scl=scl, sda=sda, address=f"{DES_ADDR:02X}"
    )


@mcp.tool()
def la_capture_raw(seconds: float = 5.0, channels: str = "0,1",
                   samplerate: str = DEFAULT_SAMPLERATE,
                   path: str = "", trigger: str = "") -> dict:
    """Capture to a .sr session file for later re-decoding or DSView/PulseView.

    Useful when you want one capture you can decode several ways without
    re-running the stimulus.
    """
    if not path:
        path = os.path.join(tempfile.gettempdir(), "civic_capture.sr")

    args = ["--driver", DRIVER, "--config", f"samplerate={samplerate}",
            "--channels", channels, "--time", str(int(seconds * 1000)),
            "-o", path]
    if trigger:
        args += ["--triggers", trigger]
    _sigrok(args, timeout=seconds + 60.0)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return {"path": path, "bytes": size, "seconds": seconds,
            "samplerate": samplerate, "channels": channels}


@mcp.tool()
def la_decode_file(path: str, scl: str = DEFAULT_SCL, sda: str = DEFAULT_SDA,
                   address: str = "") -> dict:
    """Re-decode a saved .sr capture as I2C, without re-running the capture."""
    if not os.path.exists(path):
        raise LaError(f"no such capture file: {path}")
    text = _sigrok(["-i", path, "-P", f"i2c:scl={scl}:sda={sda}", "-A", "i2c"],
                   timeout=180.0)
    txns = _parse_i2c(text)
    if address:
        want = int(address.replace("0x", ""), 16)
        txns = [t for t in txns if t["addr"] == want]
    return {"path": path, "transactions": len(txns),
            "decoded": [_interpret(t) for t in txns]}


if __name__ == "__main__":
    mcp.run()
