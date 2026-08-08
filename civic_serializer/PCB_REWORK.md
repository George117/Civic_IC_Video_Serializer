# Civic Serializer Board — Rework Notes

Rework required on the **DS90UB925Q** serializer board (`civic_serializer`) before it
will link to the **DS90UB302Q** deserializer in the Civic Gen 10 cluster.

**No respin needed.** The chip choice is correct — TI confirms the DS90UB301/302 and
DS90UB925/926 chipsets interoperate, with performance limited to that of the
301/302. Everything below is component-level rework on the existing board.

> Scope: this document covers the **serializer board only**. The PiCAN-Zero CAN HAT
> is a separate PCB with its own review notes.

---

## Summary

| # | Item | Change | Severity |
|---|---|---|---|
| 1 | MODE_SEL | Remove `MD_SEL1`, DNP `R7`, fit `R9` = 40.2 kΩ to GND | **Blocking** |
| 2 | IDx | Remove `IDX1`, DNP `R6`, fit `R8` = 40.2 kΩ to GND | **Blocking** |
| 3 | I2C host | No Pi GPIO available in DPI24 — feed `I2C1` externally | **Blocking for diagnostics** |
| 4 | LVDS connector | `LVDS1` is a 5 mm power connector on a 1.5 Gbps pair | High |
| 5 | 12 V input | No reverse-polarity or TVS protection | Medium |

---

## 1. MODE_SEL — mandatory

**Current:** `R7` (VDDIO side) and `R9` (GND side) both have **no assigned value** in
the schematic, plus trim pot `MD_SEL1` wired across VDDIO/GND with the wiper on the
MODE_SEL net.

**Problem.** MODE_SEL is an analog strap latched at PDB release. The 925's
configuration table has eight entries, and **only entry 1 (ratio 0, i.e. MODE_SEL at
0 V) is compatible with the 302.** Every other entry breaks something:

| Entry | Ratio | What it selects | Why it fails |
|---|---|---|---|
| **1** | **0** | LFMODE L, Repeater off, BC off, I2S-B off | **correct** |
| 2, 3, 6, 7 | 0.164–0.539 | Repeater **ON** | 302 not in repeater topology |
| 4–8 | 0.285–0.728 | LFMODE **H** = 5–<15 MHz | disjoint from the 302's 15–45 MHz |
| 8 | 0.728 | Backward Compatible (FPD-Link II) | 302 is FPD-Link III |
| 3, 5, 7 | — | I2S Channel B | 302 has only 3 I2S signals |

Anywhere near mid-rail lands between entries 6 and 7 — LFMODE H **and** Repeater ON
simultaneously. The link cannot come up.

**Rework:**

```
MD_SEL1   remove (trim pot)
R7        do not populate  (open, VDDIO side)
R9        40.2 kΩ 1%  to GND
```

TI's suggested value for entry 1 is "Open / 40.2 kΩ or any". Tying MODE_SEL straight
to GND also works — the resistor just keeps the option open.

Keep test point `MDE1` for probing.

> Trim pots are the wrong part for a latched analog strap: they drift with vibration
> and temperature, and here they sat in parallel with a stiff divider that swamped
> them anyway.

**Verify:** read register `0x13` (Mode Status). **Expect `0x10`** — bit 4 set
(decode complete), bits 3:0 clear (LFMODE, Repeater, Backward Compat, I2S-B all off).

---

## 2. IDx — mandatory

**Current:** `R6` = 100 Ω to VDDIO, `R8` = 100 Ω to GND, plus trim pot `IDX1`.

**Problem.** 100/100 gives a ratio of exactly **0.5**, which is not one of the nine
valid entries in the address table (they run 0 to 0.727, with 0.389 and 0.727 either
side of your value). The resulting I2C address is undefined. The 50 Ω source
impedance also swamps the trim pot completely, and the divider burns ~16 mA
continuously against TI's suggested 30 k–294 k range.

**Rework:**

```
IDX1      remove (trim pot)
R6        do not populate  (open, VDDIO side)
R8        40.2 kΩ 1%  to GND
```

Gives **7-bit address 0x0C** (0x18 as 8-bit).

Keep test point `IDX2` for probing.

**Verify:** device ACKs at 0x0C; register `0x00` reads back with 0x0C in bits 7:1.

---

## 3. I2C host — no Pi GPIO available

**Not a board fault** — a system-level consequence of DPI24.

DPI24 consumes GPIO0–GPIO27, which is every GPIO the 40-pin header exposes. GPIO0/1
become PCLK/DE and GPIO2/3 become VSYNC/HSYNC, so **both i2c0 and i2c1 are gone**.
The `I2C1` header on this board has no host on that Pi.

Note this is strictly a diagnostic loss, not a functional one — with the straps
above, the 925 comes up correctly with no register writes at all. Registers are
volatile and reset on PDB, so there is nothing to load at boot.

**Options, best first:**

1. **The CAN Pi.** You need a second Pi regardless: GPIO7–11 are SPI0 for the PiCAN
   HAT and B3–B7 for DPI24 here, so the two boards cannot share a machine. The CAN
   Pi's i2c1 carries only its SSD1306 at 0x3C — put the 925 at 0x0C on the same bus.
   Run SDA / SCL / GND between the boards, kept short.
2. **ESP8266 or USB-I2C dongle** on the `I2C1` header.

**Do not** drop to DPI18 to free GPIO22–27. The Pi packs 18-bit data as
`rrrrrrggggggbbbbbb` across GPIO4–21, which lands red on your G4–G7/R0–R1 pins and
green on your B6–B7/G0–G3. The board is wired for the 24-bit map.

`R4`/`R5` (4.7 kΩ) are correct as pull-ups. Do not add a second set at the host end.

---

## 4. LVDS connector — high priority

**Current:** `LVDS1` is `JST_NV_B03P-NV_1x03_P5.00mm` — a 5 mm-pitch through-hole
**power** connector carrying the FPD-Link III differential pair.

At 45 MHz PCLK the line rate is 1.575 Gbps (PCLK × 35). A 5 mm power connector is a
severe impedance discontinuity at that rate.

**Rework:** replace with a controlled-impedance option and run 100 Ω differential to
the cluster:

- Automotive HSD or FAKRA (what the vehicle harness actually uses), or
- a proper 100 Ω STP pigtail, or
- as a bench bodge, short coax pairs with the shield tied to the connector's GND pin

The 302 supports AC-coupled STP up to 10 m; keep the bench run well under that.

The AC-coupling caps `C11`/`C12` (100 nF each) are correct — leave them.

---

## 5. 12 V input protection

**Current:** raw 12 V into `U8` (AP63205WU-7) with no reverse-polarity or transient
protection.

Low risk on a bench supply, but if this ever shares a rail with the cluster, stepper
motors and backlight PWM will put transients on that line.

**Rework:** add in series at the input — a Schottky or P-FET for reverse polarity,
plus an SMBJ-series TVS to GND. Optional but cheap.

---

## Not faults — leave alone

Verified correct against the DS90UB925Q datasheet:

- **DPI24 pin mapping** — all 28 nets traced against the BCM pinout, flawless.
  PCLK→GPIO0, DE→GPIO1, VSYNC→GPIO2, HSYNC→GPIO3, B0–B7→GPIO4–11,
  G0–G7→GPIO12–19, R0–R7→GPIO20–27.
- **Decoupling** exactly per datasheet: 4.7 µF on VDD33, 4.7 µF on VDDIO,
  4.7 µF on CAPHS12, 4.7 µF on CAPP12, **two** 4.7 µF on CAPL12, 0.1 µF on CMF.
- **PDB network** — `R2` 10 kΩ to VDDIO with `C13` 10 µF to GND is TI's recommended
  arrangement verbatim.
- **AC coupling** — 100 nF on both DOUT+ and DOUT−, as required.
- **INTB pull-up** — `R3` 4.7 kΩ to VDDIO, correct.
- **RES0 (pin 15), RES1 (pin 18), exposed pad** all tied to GND as required.
- **I2S pins (11–13) and NC (pin 16)** correctly left open.
- **VDD33 and VDDIO** fed from the local 3V3 rail through ferrites `FB2`/`FB1`.

---

## Bring-up order after rework

1. Power the board with no cluster attached. Read `0x00` → confirm 0x0C in bits 7:1.
2. Read `0x13` → **expect `0x10`**. If not, the MODE_SEL rework did not take.
3. Connect the cluster. Read `0x0C` bit 0 — **link detect**. This is the moment of
   truth, and it needs no video at all.
4. Watch the 302 side in parallel: `0x1C` bit 1 signal detect, bit 0 lock.
   - Signal detect 1, lock 0 → physical layer fine, configuration wrong
   - Both 0 → cable or drive problem
5. Only then start DPI. Keep the pixel clock **between 15 and 45 MHz** — the 302's
   range, not the 925's 85 MHz ceiling.
6. If the picture is garbage, flip the sampling edge. Either `0x03[0]` TRFB on the
   925, or `dpi_output_format` bit 9 on the Pi (`23` normal, `535` inverted).

---

## Software escape hatch

If you want to test before touching a soldering iron, register `0x04` overrides two
of the four strap axes:

```
0x04 = 0x8A    # bit3=1 BC from register, bit2=0 BC off
               # bit1=1 LFMODE from register, bit0=0 → 15–85 MHz
               # bit7=1 preserves the default failsafe setting
```

This fixes LFMODE and Backward Compatible regardless of the resistors. **Repeater
mode is not overridable** — that one needs the hardware fix. Changing LFMODE calls
for a PDB reset; try the self-clearing digital reset at `0x01[0]` first.

---

## BOM changes

| Ref | Was | Now |
|---|---|---|
| `MD_SEL1` | trim pot | **remove** |
| `IDX1` | trim pot | **remove** |
| `R7` | unspecified | **DNP** |
| `R9` | unspecified | **40.2 kΩ 1% 0603** |
| `R6` | 100 Ω | **DNP** |
| `R8` | 100 Ω | **40.2 kΩ 1% 0603** |
| `LVDS1` | JST NV 5.00 mm | controlled-impedance connector |
| — | — | add Schottky/P-FET + SMBJ TVS on 12 V in |
