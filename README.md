# DS90UB302Q Pattern Generator Tool

Serial-driven ESP8266 tool for talking directly to a **DS90UB302Q** FPD-Link III
deserializer over local I2C, and bringing up its **internal test pattern generator**.

No serializer, no FPD-Link cable, and no pixel clock are required. The point is to
prove out the panel and the deserializer's output path independently of everything
upstream.

---

## Wiring

ESP8266 / NodeMCU:

| ESP8266 | Signal | To |
|---|---|---|
| D1 (GPIO5) | SCL | 302 SCL |
| D2 (GPIO4) | SDA | 302 SDA |
| GND | GND | cluster GND |

**Share a ground.** Do **not** add pull-up resistors — the target board already has
them, and doubling up can pull the bus below the low-level threshold.

I2C address is **0x2C** (7-bit), which corresponds to IDx strapped to 0 V —
entry 1 in the DS90UB302Q address table.

---

## Usage

1. Flash the sketch.
2. Open the serial monitor at **115200**.
3. Press **`g`**.

`g` runs the full bring-up: probe → verify identity → force outputs on →
enable a white test pattern using the internal timing defaults → print status.

### Commands

| Key | Action |
|---|---|
| `h` | Help |
| `p` | Probe and verify identity (falls back to a bus scan if no ACK) |
| `s` | Status: lock, output state, patgen config, internal timing readback |
| `d` | Dump direct registers |
| `o` / `O` | Outputs on (`0x02 = 0xE0`) / off (back to OEN pin control) |
| `g` | Full bring-up sequence |
| `1`–`5` | Pattern: white / black / red / green / blue |
| `e` | Pattern with **external** timing (needs a locked link) |
| `c` | Custom internal timing example |
| `z` | Pattern generator off |
| `R` | Soft reset (`0x01` bit 0, preserves registers) |
| `W` | Toggle change-watchdog |
| `r <reg>` / `w <reg> <val>` | Read / write a direct register (hex) |
| `I <ia>` / `i <ia> <val>` | Read / write an indirect register (hex) |

All writes are read back and verified; mismatches are reported.

---

## Run `s` first

Before writing anything, run `s`. It reads the indirect timing registers back.
Expect:

```
divider N = 8
total  840 x 485
active 800 x 480
hsw=10 vsw=2 hbp=10 vbp=2
```

That confirms the indirect register map is correct for your part and that the
defaults match AN-2198's Table 3-8. If those reads come back as zeros or garbage,
stop — the map doesn't apply and nothing downstream will behave.

---

## Two things that block a picture

**Outputs are tri-stated by default.** Register `0x02` resets to `0x00`: output
enable off, and the OEN pin in control. Writing `0xE0` enables the outputs,
overrides the OEN pin, and routes the internal oscillator onto PCLK during loss of
lock — which is the state you're in with no serializer attached.

**`Wire.begin(100000)` is a slave-mode call.** The single-argument form of
`Wire.begin()` takes an *address*, not a bit rate. This sketch uses
`Wire.begin(SDA, SCL)` followed by `setClock()`. If an earlier sketch of yours used
the single-argument form, its writes never landed.

---

## Custom timing

`patgenCustom()` programs the full internal timing set through the indirect map.
Bit packing was verified against the worked example in AN-2198 §4.3 (1176×525 total,
800×480 active → `0x98`/`0xD4`/`0x20` and `0x20`/`0x03`/`0x1E`).

```c
patgenCustom(hTotal, vTotal, hActive, vActive,
             hsw, vsw, hbp, vbp, divN, negSync, pattern);
```

Indirect registers may only be written while the pattern generator is **disabled**.
`patgenCustom()` handles this; if you use `i` manually, send `z` first.

**`divN` is empirical.** AN-2198 documents a 200 MHz internal oscillator for the
92x/94x parts, but the 302 isn't in that table. Sweep it with `i 03 <n>` if the
image rolls.

---

## If nothing appears

Work through this in order:

1. **Does `p` report `0x00 = 0x58`?** If not, it's wiring or I2C init — nothing
   downstream matters.
2. **Does `s` show `out_en=1` after `o`?** If it reverts to `0x00`, another master
   is writing to the device. Turn on `W` to catch it.
3. **Is the backlight on?** It's likely driven by the host MCU, not the 302. A
   perfect pattern on a dark panel looks exactly like no pattern.
4. **Does the 302's RGB output reach the panel directly, or through a mux?** If
   it's muxed, forcing output enable puts you in contention with whatever else
   drives that bus. Trace it before leaving the outputs enabled.

The `W` watchdog polls `PGCTL`, `PGCFG`, and `CONFIG0` once a second and reports
any change it didn't make — useful for catching a host MCU that resets the part
behind you.

---

## References

- DS90UB302Q datasheet (SNLS410)
- AN-2198 / SNLA132G — *Exploring the Internal Test Pattern Generation Feature of
  FPD-Link III IVI Devices*

Note: AN-2198 §4.2 and §4.3 say to write `0x03` to PGCFG for "24-bit with internal
clock." That contradicts the register table in the same document — bit 3 is
external-clock-select and bit 2 is timing-select, so internal clock plus internal
timing is `0x04`. §4.4 is consistent with the table. This tool uses `0x04`.
