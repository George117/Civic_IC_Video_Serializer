# Civic Gen 10 Cluster — Project Status

**Last updated:** 2026-08-08
**Goal:** Drive a Honda Civic Gen 10 instrument cluster from a racing simulator —
gauges over CAN, video into the MID (centre display).

---

## TL;DR for a future session

| Subsystem | Status |
|---|---|
| CAN gauges (RPM, speed) | **Working**, confirmed on bench |
| CAN warning lamps | Off (some frames have invalid checksums — see below) |
| FPD-Link III video link | **Working** — link up, lock confirmed both ends |
| Video on the MID | **Blocked** — compositor IC between the 302 and the panel |

The video link problem is **solved**. The remaining blocker is a graphics IC
with external DRAM sitting between the deserializer and the panel, which
composites and gates what reaches the glass. It shows "loading" and is waiting
on something — most likely a CAN handshake from the head unit.

---

## Hardware

### Cluster
Honda Civic Gen 10 instrument cluster. Contains:

```
Head unit → FPD-Link III → DS90UB302Q → [graphics IC + DRAM] → MID panel
                                              ↑
                                    cluster MCU / CAN state
```

The **DS90UB302Q** deserializer (60-pin WQFN) is accessible on the cluster board.
- SDA = pin 2, SCL = pin 3 (4.7k pull-ups already present, do not add more)
- LOCK = pin 32, OEN = pin 31, IDx = pin 56, PCLK out = pin 5
- I2C 7-bit address **0x2C** (IDx strapped to 0)
- Device ID reads `0x58`, Rev ID `0xA0`

The **graphics IC** was identified late in the session — big package with
external DRAM, does LVDS blending. **Part number not yet read.** This is the
single most valuable missing piece of information.

### PiCAN-Zero (separate PCB, George's design)
Dual MCP2518FD + MCP2542FD-E/SN, Pi Zero HAT.
- Split termination with per-channel DIP switch, PESD2CAN on both channels
- Separate INT lines per controller
- VIO on 3V3 / VDD on 5V — correct level translation
- can0 @ 500 kbps (F-CAN), can1 @ 125 kbps (B-CAN, **configured but never used**)
- SSD1306 OLED on i2c1 at 0x3C
- Open item: verify MCP2542FD STBY pins aren't floating
- Open item: single 33Ω series resistor feeds two OSC1 pins (low priority)

### Civic Serializer board (separate PCB, George's design)
DS90UB925Q-Q1 + Pi Zero HAT, DPI24 input, FPD-Link III output.
- **DPI24 pin mapping verified flawless** — PCLK→GPIO0, DE→GPIO1, VSYNC→GPIO2,
  HSYNC→GPIO3, B0–B7→GPIO4–11, G0–G7→GPIO12–19, R0–R7→GPIO20–27
- Decoupling exactly per datasheet, PDB network per TI recommendation,
  RES0/RES1/EP grounded, AC coupling 100nF on both DOUT pins — all correct
- I2C 7-bit address **0x0C** after rework

---

## Rework completed

| Ref | Was | Now | Why |
|---|---|---|---|
| `MD_SEL1` | trim pot | **removed** | latched analog strap, pot drifts |
| `R7` | unspecified | **DNP** | |
| `R9` | unspecified | **40.2 kΩ to GND** | MODE_SEL = 0V = entry 1 |
| `IDX1` | trim pot | **removed** | |
| `R6` | 100 Ω | **DNP** | |
| `R8` | 100 Ω | **40.2 kΩ to GND** | IDx = 0V → address 0x0C |

**Why MODE_SEL mattered:** the 925 has eight MODE_SEL entries and only entry 1
(ratio 0) is compatible with a 302. Mid-rail lands between entries 6 and 7,
selecting LFMODE = H (5–15 MHz, disjoint from the 302's 15–45 MHz) *and*
Repeater ON simultaneously. Verified fixed: `0x13` now reads `0x10`.

### Still outstanding on the serializer board
- `LVDS1` is `JST_NV_B03P-NV_1x03_P5.00mm` — a 5 mm power connector carrying a
  875 Mbps pair. **Not currently causing problems** (link is stable), but should
  be replaced with HSD/FAKRA or 100 Ω STP eventually.
- No reverse-polarity or TVS protection on the 12 V input.

---

## Key findings

### 1. DS90UB925Q ↔ DS90UB302Q ARE compatible
Initially thought incompatible. **Wrong.** TI applications engineer on E2E:
the DS90UB301/302 are compatible with the DS90UB925/926, with performance
limited to that of the 301/302, and no special configuration required.

Structural confirmation from the datasheets:
- Both use a **35-bit symbol**, same payload, same 10 Mbps back channel
- Serializer register maps are essentially 1:1 (925 vs 301)
- Line rate = PCLK × 35 on both

**Constraint:** the 302 caps PCLK at **15–45 MHz** (1.575 Gbps), against the
925's 5–85 MHz. Also no repeater, no backward-compat, no I2S channel B.

### 2. The 302's parallel outputs are gated by LOCK
Datasheet Table 2, page 19. With no active serial input, Data outputs are held
**LOW** regardless of output enable. The deserializer-side pattern generator
therefore **cannot** be used as a standalone display test — it needs a locked
link. (Earlier assumption to the contrary was wrong.)

Valid data requires: active serial input, Lock = H, OEN = H, **and OSS_SEL = H**.
That means `0x02 = 0xF0`, not `0xE0`.

### 3. The two things that were actually blocking the link
1. **MODE_SEL strap** (fixed in hardware, above)
2. **`0x14` OSC Clock Source defaults to `0x00` = External Pixel Clock.** With no
   DPI running there is no clock, so no serial stream, so nothing to lock to.
   Writing `0x14 = 0x06` selects the 25 MHz internal oscillator → 875 Mbps.
   (`0x02` = 33 MHz is the other option. 12.5 MHz requires LFMODE = 1, which the
   302 doesn't support.)

### 4. I2C pass-through must be enabled explicitly
`0x03[3]` defaults to 0. Without it, transactions addressed to 0x2C are not
forwarded over the control channel. Set `0x03 = 0xDA` (`0xD2 | 0x08`).
`0x17` Pass-All is *not* needed since DESID auto-populates with 0x2C.

### 5. Two I2C masters collide
Once the link is up, the 925 can act as a master on the 302's local bus. With
an ESP also attached there, you get `err 4` arbitration failures. **Reach the
302 through the link, keep its local ESP unplugged.**

### 6. AN-2198 indirect register map is valid on the 302
Confirmed empirically — readback gave divider N=8, total 840×485, active
800×480, hsw=10 vsw=2 hbp=10 vbp=2, matching AN-2198 Table 3-8 exactly.
Bit packing verified against the §4.3 worked example.

**AN-2198 typo:** §4.2 and §4.3 say write `0x03` to PGCFG for "24-bit with
internal clock". That contradicts the register table in the same document —
bit 3 is external-clock-select, bit 2 is timing-select, so it should be `0x04`.
§4.4 is consistent. Use `0x04`.

### 7. Raspberry Pi DPI24 leaves no I2C
DPI24 consumes GPIO0–27, which is every GPIO on the 40-pin header. Both i2c0
(GPIO0/1) and i2c1 (GPIO2/3) become PCLK/DE and VSYNC/HSYNC.

- Not a functional problem — with correct straps the 925 needs no register writes
- TRFB (`0x03[0]`, default falling edge) can be matched from the Pi side via
  `dpi_output_format` bit 9: `23` = normal, `535` = inverted pixel clock
- The PiCAN and serializer boards **cannot share a Pi** (GPIO7–11 = SPI0 vs B3–B7)
- Best I2C host: the CAN Pi's i2c1, which only carries the OLED at 0x3C
- **Do not** drop to DPI18 to free pins — the Pi packs 18-bit as
  `rrrrrrggggggbbbbbb` on GPIO4–21, which scrambles this board's 24-bit wiring

---

## Working bring-up sequence

From cold power-on, serializer-side ESP only:

```
0x13  read   → must be 0x10           (MODE_SEL strap)
0x14  = 0x06                          (25 MHz internal oscillator)
0x0C  read   → bit 0 = 1              (link detect)
0x06  read   → 0x58                   (DESID auto-loads on RX lock)
0x03  = 0xDA                          (I2C pass-through on)
302 0x64 = 0x00                       (disable 302's own patgen)
302 0x02 = 0xF0                       (outputs on, override, OSC clk, OSS_SEL)
0x65  = 0x04                          (24-bit, internal clock + timing)
0x64  = 0x11                          (white pattern, enabled)
302 0x1C read → 0x03                  (lock = 1, signal detect = 1)
```

**This sequence is confirmed working.** It is automated as `C` in
`ub925_link.ino` and runs on boot in `ub925_sweep.ino`.

---

## Tools written

| File | Purpose |
|---|---|
| `ub302_patgen.ino` | ESP8266, direct local I2C to the 302. Pattern generator, indirect timing, register access. **Note: its README claims no serializer needed — that is wrong, see finding 2.** |
| `ub925_link.ino` | ESP8266 on the serializer. `C` = full cold-start bring-up. Reaches the 302 through the link (`S`, `o`, `y`, `Y`). Strap decode, link/backchannel status, patgen. |
| `ub925_sweep.ino` | Cold start + sweeps 11 candidate video timings through the 925 patgen. |
| `PCB_REWORK.md` | Serializer board rework instructions. |

All ESP8266 sketches: `Wire.begin(SDA, SCL)` + `setClock()`. **Never**
`Wire.begin(100000)` — the single-argument form is the slave-mode constructor.

---

## Where it's blocked

Everything electrical is confirmed green:

```
925 link      : 1
302 lock      : 1
302 outputs   : 0xF0
925 patgen    : 0x11
```

But **nothing appears on the MID**, and the cluster sits at "loading" on the nav
screen. Swept 11 plausible timings (800×480 ×4 variants incl. sync polarity,
640×480, 720×480, 480×272, 400×240, 800×600, 1024×600, 1280×480) — no change.

The graphics IC between the 302 and the panel is compositing and gating. A
resolution mismatch would more likely give black or garbage than a persistent
loading state, so the working hypothesis is that it's **waiting on a handshake**
— probably CAN from the head unit announcing that video is being sent.

Note: the 302's LOCK pin is documented as usable as "Link Status or Display
Enable". If it's routed to the graphics IC, the compositor already knows a link
exists and is still saying "loading" — which argues further for a handshake
rather than a presence gate.

---

## Next steps, in order

1. **Read the part number off the graphics IC.** Photograph the markings. If it's
   a Socionext MB86R, Renesas R-Car, or similar documented part, the problem
   becomes tractable. Highest value action available.
2. **Scope PCLK on 302 pin 5** with a pattern running. Confirms the deserializer
   is genuinely driving the compositor, and measures the real pixel clock —
   which resolves an open question about whether PGCDC is in the clock path.
   (The sweep script's Hz figures assume PCLK = the `0x14` oscillator; AN-2198
   documents a 200 MHz internal oscillator for the 92x parts but the 925/302
   pairing isn't in that table.)
3. **Source a donor Display Audio head unit.** Unblocks everything:
   scope its FPD-Link output for exact expected timing; log B-CAN while cycling
   the MID to find the trigger frames; see whether "loading" resolves with the
   real unit present.
4. **Failing that, passively log B-CAN (125 kbps) from a running Gen 10** while
   someone cycles the MID through its screens, and diff.

---

## Open item: CAN checksums

Separate from the video work, in `cluster_frames.py`:

`encode()` builds byte7 with the **previous** call's checksum, then computes the
new one — so the transmitted checksum lags one frame. This was empirically
compensated by using `checksum_offset = 7` instead of 8, which works for three
counter values out of four but breaks at the 3→0 wrap (error jumps by 4).

Simulated against the reference Honda algorithm:
- Frames with `offset = 7` (ACC_HUD, EPB, LKAS, STEER, VSA, BRAKE, POWERTRAIN,
  RPM, ENGINE): **3/4 valid**
- Frames with `offset = 5` (CRUISE 0x324, RADAR_HUD 0x39F, SEATBELT 0x305,
  HIGHBEAM 0x35E): **0/4 valid**

Fix — reorder and use a uniform offset of 8:

```python
def encode(self):
    self.counter = (self.counter + 1) & 0x3
    chk_byte = self.dlc - 1
    self.data[chk_byte] = self.counter << 4
    self.checksum = calc_checksum(self.data, self.id, self.dlc, 8)
    self.data[chk_byte] = (self.counter << 4) | self.checksum
    return self.data
```

Also: `Frame_SEATBELT_STATUS` writes the checksum into byte6 without the counter
nibble, unlike every other class. And `main.py` has no TX cadence at all — the
loop rate is set by the SSD1306 refresh. Frames should be scheduled on
per-frame periods (~10 ms powertrain, ~100 ms HUD/status) with the display and
switch polling moved to a separate thread.

Not urgent — lamps being off is not currently causing symptoms, and the
`offset = 5` frames appear not to be load-bearing for this cluster.
