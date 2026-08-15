# Civic Gen 10 Cluster — Project Status

**Last updated:** 2026-08-15
**Goal:** Drive a Honda Civic Gen 10 instrument cluster from a racing simulator —
gauges over CAN, video into the MID (centre display).

---

## TL;DR for a future session

| Subsystem | Status |
|---|---|
| CAN gauges (RPM, speed) | **Working**, confirmed on bench |
| CAN frame checksums | **Fixed + hardware-confirmed** — 874/874 vs real cluster traffic |
| CAN warning lamps | **Nearly clean** — airbag info + autohold flashing remain |
| Cluster diagnostics (UDS) | No responder on either bus — see negative result below |
| B-CAN observability | **Working** — cluster gateways F-CAN onto B-CAN, finding 9 |
| FPD-Link III video link | **Working** — link up, lock confirmed both ends |
| Video timing we send | **MEASURED exactly** — 22.89 MHz, 840x485, 800x480, hsw 10, 56.19 Hz, finding 23 |
| Video on the MID | **Blocked, cause NOT identified.** 24 geometries swept and rejected (finding 24); no feedback signal exists (finding 25). Next: dump the flash |
| Inter-board link | **Decoded, WRITE-ONLY** — SPI + I2C 0x51, main -> sub only; parts of finding 21/22's field map retracted, finding 25 |

The video *link* problem is **solved** — the FPD-Link is up and the pixels we
deliver are now measured, not inferred. The remaining blocker is the compositor,
and **why it rejects our video is still unknown**: the leading hypothesis (VIU
geometry) survived 24 tests without a hit, and the assumption underneath it —
that the Vybrid's VIU is running at all — has never been tested.

### State as of 2026-08-15 (end of session)

**The compositor is identified: an NXP Vybrid VF522R3 (`SVF522R3CMK4`)** on a
video sub-board, with 1 Gbit ISSI DDR3 and **two** 64 MB Spansion S25FL512S SPI
flashes. It hangs off a larger main board carrying a **Fujitsu MB91F577BHS**
cluster MCU, linked by a 16-pin connector. All documented, off-the-shelf parts.
See "Cluster ICs".

**There is no missing handshake — the cluster is already in video mode
(finding 22).** Selecting nav sets the inter-board video-source field to `0x43`;
phone sets `0x41`; both display the loading animation. The main board has
commanded video and the Vybrid has switched to it. Searches for a CAN, I2C or
inter-board trigger are closed (findings 19, 20, 22).

**VIU geometry was the live suspect. It is now much weaker** — see finding 24
below. The hypothesis rests entirely on the *names* of error codes in
`doc/fsl-viu.c` (`ERR_LINE_TOO_LONG`, `ERR_TOO_MANG_LINES`, ...); no evidence has
ever been collected that the VIU is rejecting anything. See "Where it's blocked".

**The video we send is now MEASURED, not inferred (finding 23):**
**22.89 MHz PCLK, 840x485 total, 800x480 active, hsw 10, 56.19 Hz** — vTotal
confirmed as an exact integer on five consecutive frames, and every figure
reproduced across a cluster power cycle. The 302's outputs are *measured* to be
physically driving, closing the caveat findings 13 and 16 both left open.

**PGCDC IS in the pixel-clock path** (`PCLK = 182.9 MHz / divN`, proven by
changing divN and re-measuring: 8 -> 22.885 MHz, 6 -> 30.443 MHz, ratio 1.3302 vs
1.3333). **Finding 6 is settled.** Note this file first recorded the *opposite*
conclusion — see the correction inside finding 23.

**The totals sweep is DONE and is a clean negative (finding 24).** 24 distinct
total geometries at 800x480 active, both sync polarities, PCLK 22.9-36.6 MHz, all
with link and lock verified — the MID showed the loading animation on every one.

**This weakens the geometry hypothesis and exposes an assumption nobody tested:
there is no evidence the Vybrid's VIU is enabled at all.** Finding 22 showed the
*main board* requesting video; that the Vybrid acted on the request has been
assumed ever since. The BT.656 input-*mode* hypothesis is also re-opened — its
"refutation" was about what the hardware supports and how the board is wired, not
about how the firmware configures the VIU.

**That search for a feedback signal is also DONE and negative (finding 25).** No
byte on either inter-board link tracks video presence, and both links are
**write-only** — the Vybrid reports nothing back to the main board on pins 6-10.
So there is no automated score, the human stays in the loop, and the "is the VIU
enabled?" question has no cheap instrument left.

**Next action: dump both S25FL512S flashes** (next steps 4). Every cheap
black-box avenue is now closed — CAN, the 302's I2C, the inter-board link, and a
24-geometry totals sweep. The firmware is the only remaining place that says what
the VIU is configured to expect, whether it is enabled, and what input mode it
uses. Read the desolder/interleaving warnings there first; the cluster must
survive.

**Bench state as of end of session:** cluster healthy, 925 ESP running the
**rebuilt 26-entry `ub925_sweep`** on **`/dev/ttyUSB0`** (it has moved between
`ttyUSB0` and `ttyUSB1` repeatedly — **always confirm with `esp_open`, never
trust the port number**). 302-local ESP **unplugged**; keep it that way, finding
15's reproduction note. Timing left on entry 1 (CTRL 840x485). Verified live:
`925 0x0C=01`, `925 0x14=06`, `302 0x1C=03`, `302 0x02=F0`, and the DSLogic sees
22.88 MHz / 840 / 485 on the 302's outputs.

**DSLogic probe map as left wired:** CH0-CH4 = 16-pin connector pins 6,7,8,9,10;
**CH12-CH15 = 302 pins 5,8,7,6 (PCLK, HS, VS, DE)**. Both sets can be captured
simultaneously at 20 MHz — but at that rate **PCLK aliases to 2.88 MHz and looks
like a valid clock**, so use **DE (CH15) as the video-presence witness**, never
PCLK.

**RETRACTIONS AND CORRECTIONS — check these before citing anything in this file.**
This project has a repeated failure mode: **a measurement consistent with a
conclusion gets recorded as proof of it.** Five instances so far:

| claim | status | why it failed |
|---|---|---|
| Finding 13 | **retracted outright** | state never verified during the observation window |
| Finding 16 | **overstated** | its test inherited our own timing, so it never disproved the timing hypothesis |
| Findings 14, 17 | **corrected** by 19 and 22 | |
| Finding 23's "PGCDC is NOT in the clock path" | **wrong, reversed** | 200/8 and 25/1 predict the same number; the test did not discriminate |
| Finding 22's `[216]`, `[182]/[183]` | **unreliable** | captures were in time order, so a free-running counter mimics a state field (finding 25) |

**The lesson, stated once: before recording a conclusion, ask what OTHER
hypothesis predicts the same observation — then design the test that separates
them.** Reversal controls and divider changes are cheap; retractions are not.

**Instruments now available:** a working DSLogic + `civic-la` MCP server
(finding 18) with a validated video-timing analyser
(`scripts/video_timing.py`, finding 23) and inter-board differ
(`scripts/interboard_diff.py`, finding 25); a rebuilt 26-entry totals sweep
(finding 24); and a local ESP on the 302's I2C (finding 12) — **which must stay
unplugged while the link is up**, finding 15.

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

#### 302 parallel-output probe points — from the datasheet, 2026-08-15
Pin Descriptions, `doc/DS90UB302Q_datasheet.pdf` p.4. **The four video timing
signals are contiguous on one edge**, so a single tack-on session gets all of
them:

| signal | 302 pin | type | suggested DSLogic channel |
|---|---|---|---|
| **PCLK** | **5** | O, LVCMOS | CH0 |
| **DE** | **6** | O, LVCMOS | CH3 |
| **VS** | **7** | O, LVCMOS | CH2 |
| **HS** | **8** | O, LVCMOS | CH1 |

**Set the DSLogic threshold from a measurement, not an assumption.** The 302's
VDDIO is dual-range — `1.71–1.89 V` **or** `3.0–3.6 V` (datasheet p.6,
Recommended Operating Conditions) — and its LVCMOS outputs swing to whichever
rail the cluster fitted. **Do not infer it from the I2C bus being 3.3 V**; the
parallel bus feeds the Vybrid's VIU and may sit on a different rail.

Meter **VDDIO on pin 13, 24 or 38** first, then set threshold:
- VDDIO ≈ 3.3 V → threshold **1.6 V**
- VDDIO ≈ 1.8 V → threshold **0.9 V**

Getting this wrong yields an **empty capture that still exits 0** (finding 18) —
it fails silently, so it will look like "no signal" rather than "wrong setting".

**Soldering hazards on this edge (60-pin WQFN, fine pitch):**
- **Pin 13 is VDDIO**, five pins from the work area. Bridging an output to that
  rail is the expensive mistake here.
- **Pins 9–12 are B[4:7]**, immediately adjacent to HS on pin 8. A bridge
  between two data lines corrupts the blue channel with no obvious symptom.
- Keep the probe stubs **short** (a few cm, ground return twisted alongside).
  A long flying lead hangs capacitance on a live 25 MHz line feeding the VIU and
  can degrade the signal being characterised. There is no spare cluster.

**Sample-rate staging** — the DSLogic Plus trades channels against rate, so this
is three captures, not one. Note the pixel clock cannot be measured at 25–50 MHz
(Nyquist); it needs the top of the range:
1. **CH0 alone @ 400 MHz** → actual pixel clock. Decisive on its own: 25 MHz
   vindicates the sweep's assumption, ~3.1 MHz means PGCDC divides by 8 in the
   clock path and every timing result to date is void.
2. **CH0 + CH1 (PCLK + HS) @ 200 MHz** → PCLK cycles per HS period = **hTotal**,
   the number the VIU validates.
3. **CH1/CH2/CH3 (HS/VS/DE) @ low rate** → HS per VS = **vTotal**; DE gives the
   active window. These are kHz/Hz signals and need no speed.

### Cluster ICs — IDENTIFIED 2026-08-15
Markings read under a microscope through conformal coating (`doc/ic.txt`,
`doc/top.jpg`, `doc/bottom.jpg`). Some characters were uncertain; the
identifications below are inferred from partial markings and should be
confirmed against the silicon where they matter.

Conformal coating was removed for the second pass, so these markings are full
and reliable (`doc/ic.txt`, `doc/top.jpg`, `doc/bottom.jpg` — colour-boxed).

| ref | marking | identified as |
|---|---|---|
| top, red | `SVF522R3CMK4` `2N02G` `PTCTCTEA1715H` | **NXP Vybrid VF522R3** — Cortex-A5 + Cortex-M4, VIU + DCU. `SVF` = automotive. `2N02G` mask set, `1715` = 2017 wk15. The video processor. |
| top, green | `ISSI1716` `IS46TR16640B-15GBLA2` | **ISSI IS46TR16640B-15GBLA2** — 1 Gbit (64M x16) DDR3-1333, automotive temp. Vybrid frame buffer. |
| top, blue | `72CET2UG3` `UB302QSQ` | **TI DS90UB302QSQ** deserializer — full part number now confirmed. |
| top, yellow | `D90590` `7196` | **ROHM BD90590** (inferred) — ~20-pin, by the power input. ROHM omits the leading `B` in package marking. Multi-rail PMIC for the Vybrid. *Inferred, not confirmed.* |
| top, magenta | `D90525` `7206` | **ROHM BD90525EFJ** — automotive synchronous buck, **1.5 V fixed / 2 A / HTSOP-8**. 1.5 V is the DDR3 rail, and it sits by the inductors. |
| bottom, pink | `G02` `FL512SSVF01` `704Q0065.A` `(C)11 SPANSION` | **Spansion/Cypress S25FL512S — 512 Mbit (64 MB) SPI NOR.** Vybrid boots QuadSPI from it. |
| bottom, pink (2nd) | identical markings | **A second S25FL512S** — same part, same markings. Two flashes, 2 x 64 MB = **128 MB total**, matching the Vybrid's 2x QuadSPI. See the interleaving warning below. |
| **main board** | `MB91F577BHS` | **Fujitsu FR81S, MB91570 series** automotive cluster MCU, on the larger board this one mounts to. Handles CAN and the gauges. |

**Flash density is ambiguous optically.** `ic.txt` records `FL412S`, the photo
reads `FL512S`; `S25FL512S` is a real part and `S25FL412S` is not. **Do not
resolve this by eye — read the JEDEC ID** (`RDID` / `9Fh`) when the programmer is
attached. Definitive and free.

### WARNING: the two flashes are probably INTERLEAVED — dump both
The Vybrid QuadSPI supports a **parallel / dual-data-flash mode** in which two
identical devices are read simultaneously, each supplying half of every data
word, to double read bandwidth. **A matched pair of identical parts sitting
adjacent is exactly that configuration's signature.**

If so, **dumping one chip alone returns every other nibble/byte** — which looks
like noise, not firmware. The failure mode is subtle and expensive: it is easy to
conclude the dump failed, the programmer is wrong, or the image is encrypted,
when it is simply split across two devices.

Procedure:
1. `RDID` both devices first; confirm identical part and density.
2. **Dump both**, keeping them clearly labelled by position / chip select.
3. Sanity-check each image alone — look for ASCII strings, an ARM vector table,
   or a bootloader header. If neither is sane alone, **de-interleave**: try
   byte-wise and nibble-wise interleaving of the pair and re-check.
4. Confirm the actual mode against the QuadSPI chapter of the Vybrid reference
   manual (still not in `doc/` — the datasheet and fact sheet do not cover it).

Total image size is 128 MB across both.

### 16-pin inter-board connector — pinout (measured 2026-08-15)
Accessible on the sub-board underside (`doc/bottom.jpg`, right side, pins
silkscreened). Measured with a meter/scope, recorded in `doc/16_pin_connector.txt`:

| pin | measured | reading |
|---|---|---|
| 1, 2, 5, 11, 14, 15 | 5 V | power |
| 3, 12 | GND | ground |
| 4 | 0 V | idle-low signal, or further ground |
| **6** | **clock, 3.3 V, 2 MHz** | **the only 3.3 V signal** |
| **7** | data, 5 V | |
| **8** | pulses every **21 ms**, 5 V | chip select / frame sync (~47.6 Hz) |
| **9** | clock, 5 V | |
| **10** | data, 5 V | |
| **13** | **12 V** | **NEVER connect to the DSLogic** — its threshold range stops at 5 V. Supply feed, no information in it. |
| 16 | 1.5 V | DDR3 rail |

**Two synchronous links, not one** — there are two separate clocks (6 and 9).

**The voltage split is the key clue.** Pin 6 is the only 3.3 V signal; 7-10 are
all 5 V. The Vybrid is a 3.3 V part and the Fujitsu MB91F577 is very likely 5 V
I/O, so pin 6 is plausibly **sub-board -> main board** and 7-10 are
**main board -> sub-board**. That would make the MB91F577 the master and the
Vybrid the slave, consistent with the architecture. *Inferred from voltage
domains, not confirmed.*

**Pin 8's 21 ms cadence** looks like a periodic frame sync or chip select — a
regular status exchange between the two processors, which is exactly where a
"head unit present / show video" flag would live.

Suggested probe mapping (skip pin 13, wire GND from pin 3 or 12):
`CH0->6, CH1->7, CH2->8, CH3->9, CH4->10`, optionally `CH5->4`.
Threshold `1.6 V` works for both 3.3 V and 5 V signals.

**The Vybrid is the breakthrough.** It is a standard, publicly documented NXP
part with a full reference manual — not a custom ASIC. Its DCU does hardware
layer blending, which is exactly the compositing behaviour we have been fighting.

**The SPI flash is the biggest opportunity.** It is SOIC-16 on the *outside* of
the board, so it is **dumpable in-circuit with a test clip**. It holds the
Vybrid's firmware and almost certainly its graphics assets. Every finding in this
file so far is black-box inference about why the compositor rejects our pixels;
that flash contains the code making the decision.

### Vybrid VF522R3 — what the documentation says (2026-08-15)
Sources now in `doc/`: `VF5XXRFAMFS.pdf` (VF5xxR fact sheet),
`VYBRIDFSERIESEC-3139538.pdf` (datasheet rev 10), `AN4947.pdf` (architecture),
`fsl-viu.c` (Linux driver).

**CORRECTION 2026-08-15: the Vybrid is a video SUB-MODULE, not the cluster brain.**
The photographed board sits on a larger main board carrying an
**MB91F577BHS** — a Fujitsu FR81S (MB91570 series) 32-bit automotive MCU, a
standard instrument-cluster part. **All data reaches the sub-board through a
16-pin connector on its underside** (visible in `doc/bottom.jpg`, pins numbered
1..16 next to the `DIP` marking).

Revised architecture:

```
                     [ MAIN BOARD ]                    [ VIDEO SUB-BOARD ]
  F-CAN / B-CAN --> MB91F577BHS  --16-pin connector--> Vybrid VF522R3 --> MID panel
                    (gauges, CAN)                       ^  DDR3, SPI flash
  Head unit -------> FPD-Link ---> DS90UB302Q ----------/  (VIU capture -> DCU)
```

Consequences for earlier findings:
- **The B-CAN source address `0x50` is the MB91F577**, not the Vybrid. Findings 9,
  10 and 20 are about the main-board MCU.
- The Vybrid's 2x FlexCAN are probably **unused** — CAN terminates at the FR81S.
- The 17 Hz I2C poll of the 302 (finding 19) is the Vybrid, on the sub-board.
- **The "loading" decision most likely arrives over the 16-pin connector.** The
  path for head-unit presence would be: head unit -> CAN -> MB91F577 -> 16-pin
  link -> Vybrid. That link has never been examined.

**The 16-pin connector is now the prime target**, and it is a perfect fit for the
16-channel DSLogic. See next steps.

VF5xxR features still map onto the sub-board line for line:

| feature | on this board |
|---|---|
| 400 MHz Cortex-A5 + 167 MHz Cortex-M4 | (note: VF5xx**R** has both; plain VF5xx is A5-only) |
| **2x FlexCAN** | F-CAN + B-CAN — this is the gateway behind finding 9 |
| **2x QuadSPI flash** | the S25FL512S on the underside = boot flash |
| **VIU, 24-bit parallel camera input** | fed from the 302 |
| **DCU, dual display up to WVGA** | 800x480 MID panel |
| 364-pin MAPBGA 17x17 mm | matches the package in `doc/top.jpg` |

`EVB-VF522R3` is a real NXP evaluation board for this exact part.

**The video path is confirmed viable end to end.** Every hardware parameter
checks out against what we are already sending:

| parameter | spec | ours |
|---|---|---|
| VIU data width | `VIU_D[23:0]`, 24-bit parallel | **24 traces confirmed on the board** — 3 groups of 8 through series resistor packs, 302 -> VIU |
| VIU max pixel clock | 64 MHz | 25 MHz |
| platform bus clock | must be >= 2.5x pixel clock (62.5 MHz) | Vybrid platform bus is far above |
| VIU setup / hold | tDSU 4 ns, tDHD 1 ns | comfortable at 25 MHz |
| DCU max resolution | WVGA | 800x480 |

**REFUTED hypothesis — worth recording so it is not re-raised.** The VIU is
usually demonstrated in 8-bit ITU-R BT.656 mode (NXP's own examples feed it from
an ADV7180), which suggested our 24-bit RGB with separate syncs might be the
wrong *format* and would explain every failure. **It is wrong**: the fact sheet
states "Video ADC/camera Input: 4x composite **24-bit parallel**", the datasheet
timing diagram shows `VIU_D[23:0]`, and the board physically routes 24 data
lines. Format is not the problem.

**The VIU interface is a 1:1 native match for the 302's output.** Datasheet pin
names: `VIU_PCLK`, `VIU_DE`, `VIU_HSYNC`, `VIU_VSYNC`, `VIU_DATA0..VIU_DATA23`.
The 302 emits exactly that set. No conversion, no mux, nothing missing.

**Consequence: no hardware incompatibility remains to explain the blank MID.**
Format, width, sync scheme, resolution, pixel clock and setup/hold are all within
spec and natively matched.

### The sharpened timing hypothesis — VIU rejects mismatched geometry
> **TESTED AND DID NOT PAY OUT — read finding 24 before acting on this section.**
> 24 distinct total geometries were swept at 800x480 active with link and lock
> verified on every entry; none produced a picture. The hypothesis is not
> disproven (the space is ~150 and both axes must match simultaneously), but note
> as you read that **its entire support is the error-code names quoted below.**
> No evidence has ever been gathered that the VIU is rejecting anything — or that
> it is enabled. See "Where it's blocked" for the four live hypotheses.

`doc/fsl-viu.c` exposes the VIU's hardware error codes:

```
ERR_LINE_TOO_LONG       /* Line too long */
ERR_LINE_TOO_SHORT      /* Line too short */
ERR_TOO_MANG_LINES      /* Too many lines in field */
ERR_NOT_ENOUGH_LINE     /* Not enough lines in field */
ERR_FIFO_OVERFLOW / UNDERFLOW
```

**The VIU validates incoming video against a configured expected geometry and
discards frames that do not match.** So timing matters — but not as "any valid
800x480 will do". The firmware programs specific expected line length and line
count, presumably matching the real head unit. Anything else is rejected and
nothing is captured, which looks exactly like a permanent "loading" screen.

This reframed the original eleven-timing sweep, which searched a space of
*plausible* timings when what is needed is the *one* geometry the firmware
expects — total line length and lines per field, not just active resolution.
**That reframing was acted on** in the rebuilt 26-entry sweep, and it produced a
clean negative (finding 24).

**Where that number lives:** in the S25FL512S firmware (VIU config registers), or
measurable from a real head unit. The flash dump remains the decisive step — but
after finding 24, read it for **whether the VIU is enabled and what input mode it
uses**, not only for the geometry. See next steps 4.

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

### 8. HAZARD: never enable the 302 patgen's internal timing before programming the indirect map
**2026-08-15 — this bricked the control channel and cost a power cycle.**

Writing `302 0x65 = 0x04` then `302 0x64 = 0x11` killed I2C to the deserializer:
every 302 register then read `0xFF`, and `C` aborted at
`link up, DESID=0x58 / ABORT: 302 unreachable`. The 925 side was unaffected
throughout — link stayed up, `0x0C=03`, `0x14=06`.

**The registers were the right ones; the sequence was wrong.** Per the
DS90UB302Q datasheet p.40–41 (`doc/DS90UB302Q_datasheet.pdf`), on the 302
`0x64` *is* PGCTL (`[7:4]` pattern select, default `0x10`; `[0]` enable) and
`0x65` *is* PGCFG (`[4]` 18/24-bit, `[3]` ext clk, `[2]` timing select, `[1]`
invert, `[0]` auto-scroll). Both values written were individually legal.

The fault: `0x65[2] = 1` selects **internal timing**, which makes the patgen
build its own frame from the Total/Active Frame Size, Sync Width, Back Porch and
Sync Config registers — all of which live in the **indirect** map behind
`0x66`/`0x67` (finding 6, AN-2198). Those are at power-on defaults on a fresh
boot, and PGCDC (the clock divider) with them. So this told the part to clock a
degenerate frame with an unset divider, which hangs the video clock domain and
takes the back-channel I2C down with it.

`ub302_patgen.ino` already does it correctly — see `applyTiming()`: it calls
`patgenOff()` first ("required before touching indirect"), writes all thirteen
indirect registers, and only then enables the pattern.

**Correct order, always:**
1. patgen **off** (`0x64 = 0x00`) — indirect registers cannot be written while it runs
2. program the indirect timing set via `0x66`/`0x67` (PGCDC, PGTFS1-3, PGAFS1-3,
   PGHSW, PGVSW, PGHBP, PGVBP, PGSC)
3. `0x65` = mode bits
4. `0x64` = pattern + enable

Alternatively skip the whole hazard with **external timing** (`0x65[2] = 0`):
the patgen then rides the recovered timing off the link and needs no indirect
setup at all. Note this does *not* isolate a timing fault — it reuses whatever
timing the 925 is sending — so it answers a different question than the test in
"Where it's blocked". (And see finding 11: it is also nearly redundant with what
the 925 patgen already does.)

**Second attempt, correct sequence, same outcome — this is a property of the
part, not a mistake.** Ran the full ordered sequence through the link: patgen
off, all 12 indirect registers written *and read back verified* (PGCDC=`08`,
PGTFS1=`48`, PGTFS2=`53`, PGSC=`03`), then `0x65 = 0x04`, which **read back
cleanly as `0x04`** where the first attempt had already died by this point. The
sequence fix is real and confirmed. But the very next write, `0x64 = 0x11`
(enable), took the control channel down again — `0x64`, `0x1C`, `0x02` all
`0xFF`.

So: **enabling the 302 patgen in internal-clock mode always costs the I2C
channel.** The mechanism is presumably that the 302 stops using the recovered
link clock, which the back channel depends on. Treat this test as **one-shot**:
arm it, look at the glass, power-cycle. Do not expect to read anything back
afterwards.

**Recovery confirmed: a cluster power cycle fixes it completely.** `C` then ran
all six steps, `302 0x1C` read back `03` and `0x02` read `F0`, and both clobbered
registers returned to their `0x00` defaults. Nothing is persistent — the damage
is one power cycle deep, so this is a cheap mistake to make but a loud one.

Rules going forward:
- **The datasheets are in `doc/`** — `DS90UB302Q_datasheet.pdf` and
  `DS90UB925Q_datasheet.pdf`. Register map p.40–41 of the 302 sheet. Check there
  before writing anything; this incident was one `grep` away from not happening.
- `0x64`/`0x65` exist on **both** parts with similar meanings, so a value that is
  correct on the 925 may still be wrong *in context* on the 302. Identical
  register numbers are not the hazard — unsatisfied preconditions are.
- The write command returns **empty output on both success and failure**. It is
  not an ack. Always read back before sending a second write.

**Trap — `esp_check` reports a false green when the 302 is unreachable.** It
decodes lock/sigdet out of `0x1C`, so `0x1C=0xFF` prints `lock=1 sigdet=1`.
Read the raw values, not the decoded flags: healthy is `0x1C=03` / `0x02=F0`,
and `0xFF` on both means no ACK, not a healthy link.

### 9. The cluster gateways F-CAN onto B-CAN — confirmed live
**2026-08-15.** B-CAN was sniffed twice: once with both buses open but nothing
transmitting, then again with the F-CAN schedule broadcasting at 800 rpm / 0 kph.
Six frames changed:

| ID | Bus idle | F-CAN live |
|---|---|---|
| `0x12F85050` | `FF FF FF 00 00 00` | **`00 03 20 00 00 00`** |
| `0x12F96D50` | `CF 00 00 00 00 00 00 00` | `45 00 04 00 00 20 00 00` |
| `0x12F85250` | `FF 00 23 70` | `00 00 23 70` |
| `0x12F97650` | `80` | `00` |
| `0x12F91550` | `…43 50 80 3F` | `…43 40 80 3F` |
| `0x12F85150` | `00 01 03 00 00` | `00 01 00 00 00` |

`0x12F85050` bytes 1–2 = `0x0320` = 800 — our RPM, verbatim, in the same layout
as F-CAN `0x1DC`. The leading `FF FF FF` is the cluster's "no powertrain data"
invalid marker. **This is a confirmed stimulus→response path**: set a signal on
F-CAN, watch it appear on B-CAN. Useful as a live probe for attributing B-CAN
bytes to gauge values without a donor head unit.

B-CAN traffic here is 28 extended IDs, all ending `50`, 125 kbps.

### 10. Nothing on B-CAN moves while the MID sits at "loading"
Same session, 10 s capture with the cluster awake and the nav loading animation
running: **all 28 IDs had `payload_varies: false`** — no counter, no retry, no
poll. The compositor is not soliciting video over B-CAN in any way visible from
this tap.

Consequence for the handshake hypothesis: the trigger has to be **injected, not
observed**. Passive logging of a running car (next step 4) only helps if there
is a donor unit to diff *against* — logging this bench rig will show a flat
capture no matter how long it runs.

### 11. RESOLVED: internal-timing patgen drops LOCK, which gates its own outputs
**2026-08-15.** Armed the 302's internal-timing patgen (white, entry-1 timing)
per the correct sequence in finding 8. Nothing changed on the MID. That looked
like a compositor negative — **it was not.** A local ESP (finding 12) read the
302 while it was in that exact state:

```
0x1C GEN_STATUS = 0x02   lock=0  signal_detect=1
0x02 CONFIG0    = 0xF0   out_en=1 oen_override=1 osc_clk=1 oss_sel=1
0x64 PGCTL      = 0x11   pattern=white enabled=1
0x65 PGCFG      = 0x04   int_timing=1
```

**LOCK = 0.** Per finding 2 the data outputs are held LOW whenever LOCK is low,
regardless of `out_en`. So the panel received nothing and there was nothing for
the compositor to gate. The blank screen was an artifact of the test.

**The catch-22: internal-timing patgen works by abandoning the recovered link
clock, and that is the very clock LOCK depends on. So it drops the LOCK that
gates its own outputs, and can never drive this panel.** That branch is closed
permanently — do not retry it in any variation.

The same readback confirms every through-link write from finding 8 landed and
persisted (divider N=8, total 840×485, active 800×480, hsw=10 vsw=2 hbp=10
vbp=2, sync_cfg=0x03). The *sequence* was correct; the *mode* is unusable.

Do not read the 925's `0x0C` as evidence here. Its bits are `[0]` LINK Detect,
`[1]` **DES Error** (back-channel CRC), `[2]` PCLK Detect, `[3]` BIST CRC Error.
It went `03 → 01` during the test, which is the *error* bit clearing, not the
link dropping — bit 0 stayed set. `0x0C[1]` is an error flag, so `03` is the
*worse* of the two readings, not the healthier one.

### 12. A local ESP on the 302's I2C is the single biggest workflow win
**2026-08-15.** An ESP running `ub302_patgen.ino` wired to the 302's local
SDA/SCL (pins 2/3) does **not** depend on the FPD-Link back channel. That
changes three things:

1. **It can read the 302 while the back channel is dead** — which is the only
   reason finding 11 could be resolved at all.
2. **`z` recovers a wedged patgen without a power cycle.** The one-shot
   constraint is gone; 302-side experiments are now freely iterable.
3. Full local register access, including the indirect map and `d` (dump).

**Mandatory: hand the bus over before using it.** With the 925's pass-through on,
both masters drive the 302's local bus and two-transaction indirect reads get
interleaved and silently corrupted — observed as `read 0x67 addr phase failed
(err 2/3)` and garbage timing (`total 3912x495`, `vbp=255`), while single-byte
direct reads still looked fine. **Clear pass-through first: 925 `0x03 = 0xD2`**
(finding 4's `0xDA` with bit 3 cleared). Restore `0xDA` to go back through the
link. This is finding 5's collision, now with a clean fix.

**Do not let the MCP server open the 925's port while the local ESP is in use.**
Opening resets the ESP8266 via DTR/RTS, `ub925_sweep` re-runs cold start on boot,
and that both collides on the bus and drops the FPD-Link — destroying any LOCK
state you are trying to measure. The MCP `Esp` object is a single global
connection, so pointing it at `/dev/ttyUSB1` closes `/dev/ttyUSB0`. To read the
local board without disturbing the 925, talk to `/dev/ttyUSB1` with a standalone
pyserial script instead and leave the MCP server holding `/dev/ttyUSB0`.

`ub302_patgen` is now in the MCP server's `FIRMWARES` map, so the named tools
work against it (`read_302`/`write_302` map to plain `r`/`w` — on this board they
are direct local access, not tunnelled).

### 13. RETRACTED — was "clean negative", is actually confounded too
**Retracted 2026-08-15, same session.** Finding 14 shows a third I2C master
clears `0x02` (output enable) and `0x64` (patgen enable) on its own. The test
below read those registers **once, immediately after arming**, and never
confirmed they were still valid while the screen was being observed. A later
dump found `0x02 = 0x00` (`out_en=0`) with no write from us — so the outputs may
well have been off by the time the glass was checked.

**Do not cite this as evidence that the compositor discards pixels.** The
conclusion is unproven, not disproven. To settle it, arm and then *poll
continuously* through the observation window, so the state is evidenced at the
moment of looking rather than a second beforehand.

**Superseded by finding 16**, which re-ran it correctly and reached the same
conclusion on sound evidence. Cite 16, never this.

The original text follows for the record.

#### (retracted) Clean negative: the compositor discards valid pixels
**2026-08-15.** The test finding 11 was supposed to be. With the 302's patgen in
**external timing** mode (`0x65 = 0x00`), it generates pixels at the 302's own
output stage using the recovered link timing — so it never touches the clock, and
**LOCK stays high**:

```
0x1C = 0x03   lock=1  signal_detect=1
0x02 = 0xF0   out_en=1 oen_override=1 oss_sel=1
0x64 = 0x11   pattern=white enabled=1
0x65 = 0x00   int_timing=0   <- external
```

Every condition finding 2 requires for valid output is satisfied. **The MID still
showed the loading animation — nothing on screen.**

This also corrects an earlier claim in this file that external timing was
"redundant with the 925 patgen". It is not: the 925's pattern travels the link
and could in principle arrive mangled, whereas this one is generated *after* the
link, at the output stage. It isolates the compositor from everything upstream.

**Conclusion: valid pixels are present at the 302's parallel outputs and the
compositor is discarding them.** The timing hypothesis is dead — no 925-side
timing sweep can help, because the failure survives bypassing the link payload
entirely.

**Caveat, stated honestly:** "the outputs are driving" is inferred from register
bits, not measured. Scoping pin 5 (PCLK) would close that last gap. It is now a
much narrower question than before — one confirmation, not an open search.

### 14. A third I2C master on the 302's bus — READ THE CORRECTION FIRST
**Correction 2026-08-15.** The third master is real and is now directly
identified (finding 17: the graphics IC, polling at 17 Hz). But the
*interpretation* below — that it selectively wrote `0x02` and `0x64` — is
probably wrong. A 45 s bus capture recorded **zero writes from it**, only reads.

`0x64 = 0x10` and `0x02 = 0x00` are both the datasheet **power-on defaults**, so
those observations are better explained by a **302 reset** (finding 15's
whole-config zeroing) than by selective writes. Treat the table below as "these
registers changed", not "the graphics IC wrote them".

What survives unchanged: the `err 4` arbitration loss, which is hard proof of
another master on the bus, and the consequence that any 302-side visual test
must be bracketed by polling (which is what made finding 16 sound).

#### (original claim) CONFIRMED: a third I2C master on the 302's local bus
**2026-08-15.** With the 925's pass-through disabled (`925 0x03 = 0xD2`,
verified) and the local ESP issuing **reads only**, the 302's registers changed
underneath us:

| reg | before | after | meaning |
|---|---|---|---|
| `0x02` CONFIG0 | `F0` | `00` | outputs disabled, back to OEN pin |
| `0x64` PGCTL | `11` | `10` | patgen enable bit cleared (`10` = datasheet default) |
| `0x2C` SSCG | `8B` | `0E` | changed |

Neither the ESP nor the 925 wrote these. Corroborated independently by
`read 0x02 addr phase failed (err 4)` during a poll — **err 4 is arbitration
loss, which requires another master physically driving the bus.** The cluster's
graphics IC / MCU is therefore an active I2C master on this segment, not a
passive consumer.

It is *not* continuously policing: an armed patgen (`0x64=0x11`) survived 30 s
untouched. The observed changes correlate with cycling the MID through its
menus, so the writes look event-driven — which makes **its traffic a direct
window into the handshake the compositor is waiting for.**

**Consequences:**
- Finding 13 is retracted; any 302-side visual test must poll through the
  observation window (finding 12's `armverify.py` pattern).
- Corrupted single reads are expected on this bus. `0xFF` and one-off odd values
  (e.g. `0x64 = 0x13`, which sets reserved bits 3:1) are contention artifacts,
  not real state. Re-read before believing anything surprising.

### 15. The 302's whole configuration can get zeroed, which kills the link
**2026-08-15.** After the finding-14 activity the 302 was found with nearly every
writable register at `0x00` — `0x01`, `0x03`, `0x04`, `0x05`, `0x07`, `0x24`,
`0x41`, `0x44`, `0x56`. Reads were healthy (`0x00`=`58` device ID, `0x1D`=`A0`
rev ID, and our own writes all read back correctly), so the zeros were real, not
read failures.

**This is not a reset** — a reset restores defaults (`0x03`=`F0`, `0x04`=`FE`,
`0x07`=`18`), not zeros.

The link death is fully explained by **`0x01 = 0x00`**: bit 2 is back-channel
enable (default `0x04`). No back channel means the 925 reports LINK Detect = 0
(`0x0C`=`02`) while the 302 reports `lock=0, signal_detect=1` — carrier present,
link unestablishable. Cold start `C` cannot recover this; it aborts after step
[3].

Writing `0x01 = 0x04` back is verified to take, but **does not restore lock on
its own** — the rest of the config, `0x44` EQ included, is still zeroed.
**Power-cycle the cluster; do not try to hand-restore the register set.**

#### REPRODUCED 2026-08-15, with a probable trigger
Happened again during the finding-23 timing measurement, and this time the
sequence was timestamped, so there is a candidate cause.

Kernel log: the 302-local ESP was plugged onto the 302's I2C bus at **17:11:33**.
The parallel outputs were **alive and correct** ~1 minute later (finding 23), and
**completely static LOW** ~1 minute after that. Nothing was touched in between —
no writes, no commands, no physical contact, and `ub925_sweep`'s `sweeping` flag
defaults false so no timing step ran. The decay was spontaneous.

Register state after, read locally (so these are valid reads, not a dead bus):

```
0x00 = 0x58   device ID correct — the part is alive and answering
0x1C = 0x02   lock=0, signal_detect=1   <- carrier present, link unestablishable
0x02 = 0x00   outputs disabled          <- explains all 4 channels static LOW
0x01 = 0x00   back-channel enable cleared (default 0x04)
0x03 = 0x00   (default 0xF0)
0x04 = 0x00   (default 0xFE)
0x07 = 0x00   (default 0x18)
0x44 = 0x00   EQ zeroed
```

Byte-for-byte the original signature, confirming this is the same failure and not
a reset.

**Probable trigger: plugging the local ESP onto the 302's bus while the link was
up.** That is precisely the collision finding 5 warns about — *"With an ESP also
attached there, you get `err 4` arbitration failures. Reach the 302 through the
link, keep its local ESP unplugged."* Finding 14's `err 4` is hard proof a third
master (the Vybrid, at 17 Hz) is already driving this segment; adding a fourth
participant mid-transaction is a plausible way to corrupt a write into the
config space.

**Not proven** — one occurrence, and the mechanism by which contention would zero
~8 registers rather than one is not established. But the correlation is tight
(~60 s), the hazard is pre-documented, and the cost of respecting it is zero.

**Operational rule, reinforced: do not hot-plug the local 302 ESP while the
FPD-Link is up.** Either bring the link down first, or accept a cluster power
cycle. For the finding-23 measurement specifically, the local ESP is not needed
at all — the DSLogic is passive.

**Paired control, same session — supports the hypothesis but does not prove it:**

| condition | outcome |
|---|---|
| 302-local ESP plugged onto the bus (17:11:33) | outputs alive ~1 min, **dead by ~90 s** |
| 302-local ESP unplugged, cold start 17:22 | **still alive at 17:25:24 (~3.5 min)**, through a 100 ms raw capture and repeated surveys |

Survival is >2x the previous time-to-failure, with the suspected agent removed
and nothing else changed. That is one trial each way, so treat it as **suggestive,
not established** — but combined with finding 5's pre-existing warning it is
enough to justify the operational rule above at zero cost.

---

### 16. OVERSTATED — it does not kill the timing hypothesis. Read this first.
**Correction 2026-08-15.** The evidence below is sound; the *conclusion* went
too far.

The 302's patgen in **external timing** mode takes its pixel clock, DE, HS and VS
**from the recovered link** — i.e. from whatever the 925 is sending. So it
delivers our pixels at **our timing**. Finding 8 already says this ("does *not*
isolate a timing fault — it reuses whatever timing the 925 is sending"); finding
16 then contradicted it. Finding 8 was right.

What the test actually establishes: **the compositor discards pixels delivered at
our current timing.** That is consistent with either "the compositor gates
unconditionally" *or* "our timing is wrong" — it does not separate them. The only
test that would separate them is the 302's **internal**-timing patgen, which
finding 11 proves is unusable on this part because it drops LOCK.

So **the timing hypothesis is NOT dead.** Eleven 925-side timings were swept
without success, which is evidence, but not proof that no timing works.

The right instrument now exists: put the DSLogic on the 302's **parallel output**
(PCLK pin 5, plus DE/HS/VS) and *measure* the timing actually delivered to the
compositor, rather than inferring it. See next steps.

#### (overstated) ESTABLISHED: the compositor discards valid pixels
**2026-08-15, after a full power cycle.** The test findings 11 and 13 both failed
to be. Bracketed by evidence on both sides of the observation, which is what the
earlier attempts lacked.

Setup: cold start, verified `302 0x1C = 03` by raw read, pass-through cleared
(`925 0x03 = 0xD2`) so the local ESP owns the bus, then the 302's **external
timing** patgen armed (`0x65 = 0x00` — the clock is never touched).

| phase | evidence |
|---|---|
| before | `armverify.py`: **held=30 broken=0** over 30 s |
| during | state left armed; observation made against a live, verified config |
| after | `0x1C=03` lock=1, `0x02=F0` out_en=1, `0x64=11` enabled |

**Result: the MID still showed the nav loading animation. Nothing on screen.**

Every previously identified confound is excluded:
- LOCK high throughout → not finding 11 (outputs force-gated by lock low)
- `out_en` high throughout → not finding 14 (third master clearing `0x02`)
- external timing → no clock manipulation, so no self-inflicted lock loss
- patgen enable verified before *and* after → not silently cleared mid-window

**Conclusion: valid pixels are present at the 302's parallel outputs and the
graphics IC does not put them on the glass. The timing hypothesis is dead — no
925-side timing sweep can help, because the failure survives generating the
pixels after the link entirely.**

**Remaining caveat, stated precisely:** "the outputs are physically driving" is
still inferred from register bits rather than measured. Every *register-level*
confound is now excluded, so the only surviving gap is whether the bits reflect
physical reality. Scoping pin 5 closes it. That is a single confirmation, not an
open question.

### 17. (superseded by 19) The graphics IC polls undocumented register 0x18 at 17 Hz
**2026-08-15.** Captured with a DSLogic Plus on the 302's local I2C (finding 18).
45 s capture while cycling the MID through every menu:

```
total transactions: 750 over 45 s  (16.7 Hz)
addresses seen:     ['0x2c']       (the 302, nothing else)
chronological runs: 1
  x750   0x2C  READ  reg 0x18 -> 0x01
```

**One run. Zero variation.** The graphics IC reads register `0x18` of the 302
~17 times per second, receives `0x01` every time, and stays on "loading".

Why this was invisible until now:
- **`0x18` is undocumented.** The DS90UB302Q register table jumps from `0x17`
  (Slave Alias 7) straight to `0x1C` (General Status). `0x18`–`0x1B` are absent.
- **`ub302_patgen.ino`'s `d` dump does not include `0x18`**, so every register
  dump this session was blind to it.
- It is a **read poll, not a write** — invisible to any polling/diff approach.
  It only surfaced by watching the bus.

Current values by direct read: `0x18 = 0x01`, `0x19 = 0x01`, `0x1A = 0x00`,
`0x1B = 0x00`.

**0x18 is a MAILBOX, not a status register — the graphics IC writes it itself.**
A 90 s capture spanning **two** cluster power cycles caught the boot sequence
twice, byte-for-byte identical:

```
0x2C  WRITE reg 0x2C = 0x0E        <- also explains the 0x8B -> 0x0E change
0x2C  WRITE reg 0x18 = 0x01        <- sets the flag ITSELF
0x2C  READ  reg 0x18 -> 0x01       <- then polls it ~17 Hz, forever
```

It writes `0x01` and then spins waiting for that value to change. That is a
**request/acknowledge mailbox**: the graphics IC is waiting for a *peer* to write
`0x18`. It is not reading hardware status.

**The peer is the head unit**, because the DS90UB302Q's registers are writable
from the remote serializer over the FPD-Link back channel — and we own that side.
So the handshake is reachable two ways: through the link from the 925, or
directly from the local ESP on the 302's bus.

**This is the most promising lead in the project**, and it is now a concrete
experiment rather than a guess: write a value other than `0x01` into `0x18` and
watch the MID. The 17 Hz poll means any reaction appears within ~60 ms.

Note the loading state persists with `0x18 = 0x01`, so `0x01` means "not ready".
The value it wants is unknown — `0x00` and small integers are the obvious first
candidates.

**Also note: the handshake is on I2C, not CAN.** The long-standing hypothesis in
this file that the MID waits on a CAN message from the head unit
(see "Where it's blocked") is not supported by any evidence, and this finding
supplies a concrete alternative.

Artifacts to ignore in that capture: transactions to `0x00` (general call) and
`0x7F` (reserved) appearing between the two boots are misdecodes from floating
bus lines during the power transition.

### 18. Logic analyser bring-up (DSLogic Plus) — working
**2026-08-15.** DreamSourceLab DSLogic Plus, USB `2a0e:0020`, driven through
`sigrok-cli` and wrapped by the `civic-la` MCP server
(`scripts/mcp_servers/civic_la_mcp.py`).

Wiring: **302 pin 3 (SCL) → CH0, pin 2 (SDA) → CH1, GND → GND.** No added
pull-ups (the board has 4.7k). Bus is 3.3 V — an ESP8266 drives it directly.

Three things that each silently produce an empty capture:
1. **Firmware.** libsigrok cannot redistribute the DSLogic blobs; without them
   the device enumerates on USB but `--scan` finds nothing. Install with:
   `PREFIX=$HOME/.local sh sigrok-util/firmware/dreamsourcelab-dslogic/sigrok-fwextract-dreamsourcelab-dslogic`
   (downloads from a pinned DSView commit into `~/.local/share/sigrok-firmware`,
   no sudo needed).
2. **udev.** `60-libsigrok.rules` tags the device and
   `61-libsigrok-plugdev.rules` grants `MODE=660 GROUP=plugdev`. If sigrok was
   installed *after* the device was plugged in, the rule never ran — symptom is
   `LIBUSB_ERROR_ACCESS`. **Replug the device.**
3. **Sample rate must be an exact supported value** — 10k/20k/50k/100k/200k/500k
   /1M/2M/5M/10M/20M/25M/50M/100M/200M/400M. Anything else (e.g. `4m`) fails with
   `Failed to set device option 'samplerate': invalid argument` and yields **zero
   output while still exiting 0**. Always sanity-check a capture against known
   traffic before trusting an empty result. 2 MHz is ample for this I2C bus.

`la_check()` tests all of the above in one call and names the specific failure.

---

### 19. CORRECTION to 17: 0x18 is a reset watchdog, NOT a video handshake
**2026-08-15.** Wrote `0x18 = 0x00` from the local ESP with the bus under
capture. Result, chronologically:

```
x7   READ  reg 0x18 -> 0x01     steady poll
x1   WRITE reg 0x18 = 0x00      <- our write
x2   READ  reg 0x18 -> 0x00     <- IC sees it; our write DID take
x1   WRITE reg 0x2C = 0x0E      <- IC responds with its exact BOOT pair
x1   WRITE reg 0x18 = 0x01
x68  READ  reg 0x18 -> 0x01     poll resumes
```

The IC reacted in ~120 ms (2 poll periods) by re-running its power-up
initialisation. So:

- `0x18` **is writable**, and the IC **is** watching it.
- `0x00` is the 302's power-on default. The IC writes `0x01` to mark "I have
  initialised this part", then polls to detect the 302 resetting underneath it.
- Reading `0x00` means "it reset — re-initialise". That is a **supervision
  watchdog**, not a gate on video.

**Consequence: there is no video-enable handshake on this I2C bus.** In every
capture the graphics IC touches exactly two registers, `0x2C` and `0x18`, and
neither is video-related. It never writes `0x02` (output enable) — so output
enable is governed by the **OEN pin**, not by register. Whatever makes the
compositor show "loading" is decided somewhere other than this bus.

**The MID did not change or even flicker** while the IC re-initialised the 302.
That is a useful null: the graphics IC can be made to re-run its deserializer
init, mid-flight, with zero effect on what is displayed. So the display state is
**decoupled from the 302's I2C state entirely** — further reinforcing that the
gate is not on this bus.

Do not pursue `0x18` further as a display trigger. Its residual value is as a
**liveness probe**: writing `0x00` is a reliable, reversible way to prove the
graphics IC is running and responsive.

### 20. B-CAN is J1939-style addressed, and the cluster REQUESTS something nobody answers
**2026-08-15.** Captured B-CAN across a cluster reboot (using the fact that
`ClusterBus._capture` is a continuously-filled `deque(maxlen=4000)`, so a boot can
be pulled retroactively with `sniff(clear_first=False)` — ~34 s of history).

**Every 29-bit ID decomposes cleanly as J1939:** 3-bit priority, EDP/DP, then
PF / PS / SA.

```
ID          prio  PF    PS    SA    interpretation
0x12F85050   4    0xF8  0x50  0x50  PDU2 broadcast   (steady state)
0x0EF98B50   3    0xF9  0x8B  0x50  PDU2 broadcast   (steady state)
0x1610FF50   5    0x10  0xFF  0x50  PDU1 -> global   (1 Hz, dlc 0)
0x1E12FF50   7    0x12  0xFF  0x50  PDU1 -> global   (BOOT: 12 frames, 2 ms apart)
0x12EAFF50   4    0xEA  0xFF  0x50  PDU1 -> global   (BOOT: once, "F8 10")
0x1E22FF50   7    0x22  0xFF  0x50  PDU1 -> global   (BOOT: once, "50 00")
```

- **SA is `0x50` on every single frame** — the cluster. Nothing else is on this
  bus, which is why finding 10 saw a flat capture. The head unit would have a
  different SA, and that is the search key.
- Steady-state traffic is all `PF >= 0xF0` = PDU2 broadcast.
- **Boot-only traffic is PDU1 addressed to `0xFF` (global).**

**The lead: `0x12EAFF50` is `PF = 0xEA` = the J1939 Request PGN (59904).** At boot
the cluster broadcasts a request and receives no reply. Payload `F8 10` is the
requested PGN: little-endian (J1939 convention) = `0x10F8`; big-endian =
`0xF810`, i.e. `PF=0xF8, PS=0x10`. **`PS=0x10` never appears in any capture**,
though `PF=0xF8` is used constantly — so the big-endian reading says the cluster
is asking for a message that nobody sends. DLC is 2, not J1939's 3, so Honda's
variant differs and the endianness is unconfirmed. Both readings are testable.

`0x1E22FF50` payload `50 00` starts with the cluster's own address — the shape of
an address claim / presence announcement.

**Caveat:** Honda B-CAN is not standard J1939. The structural match is strong and
consistent across 32 IDs, but the PGN semantics are inferred, not confirmed.
Treat `0xEA` = Request as a strong hypothesis to test, not established fact.

**Confirmed boot-only.** 25 s of steady state contains no `0x12EAFF50`,
`0x1E12FF50` or `0x1E22FF50`. The cluster asks once at power-up and never again,
so any reply must already be streaming before it boots.

**NEGATIVE RESULT — zero-payload reply does not satisfy it (2026-08-15).**
Broadcast PGN `0xF810` continuously at 100 ms from eight candidate source
addresses (`0x10,0x20,0x30,0x40,0x60,0x70,0x80,0xE0`, IDs `0x12F810<SA>`,
8 zero bytes) across a cluster power cycle. B-CAN `tx_errors: 0`, so the cluster
ACKed every frame and definitely received them.

**The cluster still issued `0x12EAFF50 "F8 10"` at boot, unchanged.** No new
`…50` frame appeared and no existing payload changed in response.

What this rules out: the **zero-payload** version, across those eight source
addresses. What it does *not* rule out:
- the payload carrying required content (most likely — a presence/status reply
  is unlikely to be all zeros)
- the PGN reading being wrong after all
- a required response *form* other than a free-running periodic broadcast
- the request being unrelated to the MID's loading state

Do not repeat this exact test. Any follow-up should change the **payload**, since
the address sweep is already covered and the PGN is structurally well-founded.

The experimental frames are in `bcan_frames.BCAN_FRAMES`, clearly marked. Remove
them before treating that list as identified frames.

### 21. DECODED: the inter-board link carries the cluster state block
**2026-08-15.** DSLogic on the 16-pin connector, triggered on the chip select.
**Two independent links**, and the pairing is not the obvious one:

| link | pins | channels | protocol |
|---|---|---|---|
| **A** | 6 (clk, 3.3 V), 7 (data), 8 (CS) | CH0/CH1/CH2 | **SPI mode 0** (CPOL=0, CPHA=0) |
| **B** | 9 (SCL), 10 (SDA), 5 V | CH3/CH4 | **I2C, address 0x51** |

**Do not assume CH2's chip select gates the 5 V clock — it does not.** CH0/CH1
are active *inside* the CS window (from 0.815 ms); CH3/CH4 only start at
11.3 ms, *after* CS releases at 8.987 ms. Decoding SPI with `clk=9` returns
nothing, which is what happens if you pair them by voltage instead of by timing.

CS timing: **active 9 ms, period 30 ms** (~33 Hz). (The 21 ms in
`doc/16_pin_connector.txt` is the idle gap, not the period.)

**Link A (SPI), ~380 bytes per frame:**
```
10 02 01 8D 01 60 FF FF E8 C4 04 FF 04 80 00 00 00 00 00 01 C4 01 00 20 ...
```

**Link B (I2C 0x51), ~290 bytes per frame:**
```
10 02 81 65 00 E1 00 00 00 00 00 00 FF FF FF FF FF FF FF FF 00 00 00 43 ...
```

Both begin `10 02` — a shared framing header. Consecutive I2C frames differ in
one byte (`E1` -> `E2`, and `70` -> `73`), i.e. a **sequence counter** on an
otherwise static state block.

**This is the cluster state, forwarded from the MB91F577 to the Vybrid.** Proof:
the SPI block contains byte sequences that also appear on B-CAN —
`23 70` (B-CAN `0x12F85250` = `00 00 23 70`), `02 16` (`0x12F96250` =
`02 16 00 ...`), and `43`. The main-board MCU is relaying the same state it
publishes on B-CAN across the inter-board link.

**Why this matters: the flag that decides what the MID shows is almost certainly
a byte in these blocks.** That converts the search from "what is the compositor
waiting for?" into a differential analysis on a bus we can now read.

**Differential method VALIDATED on this link — 2026-08-15.** Captured the SPI
block at 800 rpm and 3000 rpm, two repeats each to separate real changes from
churn (`scratchpad/spiblock.py`):

```
1620 bytes per capture
   6 positions vary WITHIN a state   (sequence counter + noise)
   4 positions track RPM             (one field, appearing in each of 2 frames)

   [19][20]   800 rpm -> 01 C4 = 452
              3000 rpm -> 06 9E = 1694        1694/452 = 3.748 vs 3000/800 = 3.75
```

Exactly proportional, so **bytes [19:20] are the tachometer field** — scale
~0.565 units/rpm, i.e. ~4500 at 8000 rpm, consistent with a microstepped stepper
gauge position rather than raw rpm.

**Signal-to-noise on this link is excellent**: one stimulus moved 4 of 1620 bytes
and nothing else. So locating the display-mode flag by diffing MID states should
work cleanly. Procedure that worked, reuse it:
1. Capture twice in state A (establishes which bytes are counters/noise).
2. Change one thing. Capture twice in state B.
3. Report positions that differ A-vs-B in *both* repeats and are stable within
   each state. Anything else is churn.

### 22. THE CLUSTER IS ALREADY IN VIDEO MODE — there is no missing handshake
**2026-08-15.** Diffed the SPI state block between MID screens, two captures per
state to exclude churn. **Frame stride is 810 bytes**; each capture holds 2
frames, so every real field appears twice.

Three-way diff across default / nav / phone (2 captures each):

| frame offset | default | nav | phone | meaning |
|---|---|---|---|---|
| **163** | `00` | `43` | `41` | **video source select** |
| 182, 183 | `24` | `28` | `30` | = index x 4 (36 / 40 / 48), duplicated |
| **216** | `09` | `0A` | `0C` | **screen index** |

Only 4 fields moved out of 810. Signal-to-noise on this link is excellent.

**(RETRACTED by finding 25 — measured `[182]=[183]=00` with `[216]=0x1A`.)**
`[182]/[183]` is exactly `[216] x 4`, which cross-confirms both and implies the
Vybrid indexes a 4-byte-per-entry table. Screen index skips 11, so at least one
more screen exists beyond the three tested.

**`[163]` decodes as a bitfield:** bit 6 (`0x40`) = "external video requested",
low bits = which source. `0x43` = nav, `0x41` = phone, `0x00` = internal.

Known field map (big-endian 16-bit unless noted):

| offset | field | how confirmed |
|---|---|---|
| `[19:20]` | tachometer / needle position | proportional across 800 <-> 3000 rpm (452 -> 1694, ratio 3.748 vs 3.75) |
| `[163]` | video source select | `00` default, `43` nav, `41` phone |
| `[182]`,`[183]` | ~~screen index x 4~~ **UNRELIABLE, see finding 25** | measured `00` while `[216]=0x1A` — the stated relationship fails |
| `[189:190]` | range to empty | `0x0216` = 534, matched the value on the glass |
| `[216]` | ~~screen index~~ **free-running COUNTER, see finding 25** | reversal control: `1A -> 1B -> 1D`, never returns |

**The consequence is the important part.** Selecting nav sets mode `0x43`, and in
that state the MID shows the loading animation. So the main board **has already
commanded the video source**, and the Vybrid has already switched to it. Nothing
is withholding a "show video" permission.

**Confirmed twice over by the phone screen:** it selects a *different* source
(`0x41`) and shows the *same* loading animation. Two independent sources are
requested and neither produces a picture, so this is not a nav-specific quirk or
a per-source handshake.

**Therefore there is no missing handshake — not on CAN, not on the 302's I2C, and
not on the inter-board link.** The cluster is asking for video and getting
nothing it will accept. Findings 19 and 20 chased a handshake that does not
exist; this closes that line of investigation.

**Everything now points back at the VIU.** Per finding 21's hardware review the
path is natively compatible (24-bit parallel, 25 MHz, WVGA all in spec), and per
the VIU error codes (`LINE_TOO_LONG`, `TOO_MANY_LINES`, ...) the capture unit
**validates incoming geometry and rejects anything that does not match what the
firmware configured**. That is the remaining failure mechanism, and the expected
geometry is a number in the S25FL512S firmware.

**Next steps are now unambiguous:** dump the flash (both devices, watch for
interleaving) and read the VIU configuration out of it. Stop looking for a
trigger to send.

### 23. MEASURED: the video timing actually delivered to the VIU
**2026-08-15.** DSLogic on the 302's parallel outputs (PCLK 5, DE 6, VS 7, HS 8 —
probe pinout under "Cluster ICs"). 20 ms window, 4 channels @ 100 MHz.

| channel | signal | measured |
|---|---|---|
| CH0 | PCLK | **23.04 MHz**, 52.8% duty |
| CH1 | HS | **27.45 kHz**, 98.8% high (active low) |
| CH2 | VS | ~1 pulse / 20 ms (active low) |
| CH3 | DE | 27.2 kHz, 94.4% high (active high) |

**The eleven-timing sweep's null result IS interpretable** — it really was
delivering ~23 MHz, close to the ~25 MHz it assumed, not a catastrophically wrong
clock. The totals sweep (next steps 2) is therefore a sound instrument.

> **CORRECTION, same session — this finding first claimed "PGCDC is NOT in the
> pixel-clock path". That was WRONG.** The reasoning was that PCLK ~23 MHz ruled
> out `divN = 8` dividing the 25 MHz oscillator to 3.125 MHz. True, but it never
> tested AN-2198's actual model, in which PGCDC divides a **200 MHz** internal
> source — and 200/8 = **25 MHz**, the same nominal. Both hypotheses predicted
> the observed number, so the measurement did not separate them. See the PGCDC
> subsection below for the test that did. Recorded rather than silently edited,
> because this is the same over-reach pattern that findings 13 and 16 were caught
> by: a measurement that is consistent with a conclusion is not the same as one
> that discriminates it.

**The delivered geometry is confirmed as sweep entry 1** (840x485 total,
800x480 active, hsw=10), by four independent cross-checks that all agree:

| check | measured | predicted for entry 1 |
|---|---|---|
| hTotal = PCLK / HS rate | 839.3 | **840** |
| HS low fraction x hTotal | 10.1 px | **hsw = 10** |
| DE high fraction | 94.4% | (800x480)/(840x485) = **94.25%** |
| DE pulses / HS pulses | 0.9909 | 480/485 = **0.9897** |

So we are demonstrably sending what we believed we were sending. This closes the
caveat findings 13 and 16 both flagged — *"the outputs are physically driving" is
inferred from register bits, not measured.* **It is now measured.**

**NEW DISCREPANCY: PCLK is 23.05 MHz, not 25 MHz — ~7.8% low.** Two independent
measurements agree: direct edge count gives 23.04, and HS rate x 840 gives 23.06.
The HS figure is trustworthy because a 27 kHz signal sampled at 100 MHz is
oversampled ~3600x, so this is not a quantisation artifact. Frame rate is
therefore **56.6 Hz, not 61.4 Hz**. Whether the `0x14 = 0x06` "25 MHz" oscillator
is simply loose, or something else divides, is unresolved. Probably not fatal to
a VIU geometry check — line length in PCLKs is still 840 either way — but it is a
real error that was never spotted, and it matters if the VIU also validates rate.

#### vTotal = 485, measured directly — 2026-08-15, after a power cycle
Raw capture of HS+VS, CH1/CH2 @ 20 MHz for 100 ms, analysed with
**`scripts/video_timing.py`** (kept in the repo — run it on the unzipped `.sr`
directory: `python3 scripts/video_timing.py <dir>`; needs numpy).
Edge *counting* cannot answer this — VS has ~5 cycles in the window against HS's
~2700, so quantisation swamps a rate ratio. Counting **HS pulses between
consecutive VS edges** gives an exact integer per frame instead:

```
VS   12948 ->  368901  (17.7977 ms)   HS pulses = 485
VS  368901 ->  724848  (17.7974 ms)   HS pulses = 485
VS  724848 -> 1080799  (17.7975 ms)   HS pulses = 485
VS 1080799 -> 1436752  (17.7977 ms)   HS pulses = 485
VS 1436752 -> 1792695  (17.7972 ms)   HS pulses = 485
```

**Five frames, zero variance.** Supporting figures: HS period 36.696 us
(27.251 kHz), VS period 17.7975 ms (56.188 Hz), HS pulse width 0.4389 us.

Three independent cross-checks agree:

| check | value |
|---|---|
| fHS / fVS | 27251 / 56.1878 = **485.0** |
| fHS x hTotal (=840) | **22.891 MHz** vs 22.899 measured on CH0 — **0.03%** |
| HS pulse x PCLK | 0.4389 us x 22.891 MHz = 10.05 px = **hsw 10** |

**The delivered video is now fully characterised and exactly matches sweep entry
1** — 840x485 total, 800x480 active, hsw=10 — **on every parameter except the
pixel clock.** Nothing about what we send is in doubt any more.

**All key numbers reproduced across a full cluster power cycle** (PCLK 23.04 ->
22.90 MHz, hTotal 840 both times, DE duty 94.4% both times), so none of this is a
one-off artifact.

**On the ~8% low pixel clock:** the DS90UB925Q datasheet specifies **no tolerance**
for the internal oscillator — `0x14[2:1] = 11` is documented only as "25 MHz
Oscillator", with no min/max anywhere in the electrical tables. So 22.89 MHz
**cannot be called out of spec**; it is unremarkable for an untrimmed internal RC
oscillator. **It also does not block us**: the VIU's checks are on line *length*
and line *count*, and the 925's indirect timing registers set totals in **pixels**,
which is clock-independent. Treat the clock as a recorded curiosity, not a
blocker. It would only matter if the VIU also validates frame *rate* — unknown,
and not suggested by any of the `fsl-viu.c` error codes.

#### PGCDC IS in the pixel-clock path — settled by a discriminating test
**2026-08-15.** Changed the divider and re-measured, which is the test the
frequency measurement alone could not do:

| divN | PCLK measured |
|---|---|
| 8 | **22.885 MHz** |
| 6 | **30.443 MHz** |

Ratio **1.3302** against the predicted 8/6 = **1.3333** — agreement to **0.2%**.
PCLK scales as 1/divN, so **PGCDC sets the pixel clock**, exactly as AN-2198
describes for the 92x parts. **Finding 6's open question is settled** — in the
opposite direction to this finding's first claim.

```
PCLK = PG_BASE_HZ / divN,   PG_BASE_HZ ~= 182.9 MHz
```

The base is the nominal **200 MHz** internal oscillator running the same ~8.5%
low that made PCLK look like 22.9 instead of 25 — **one root cause, not two**.
The `0x14` oscillator selection (25/33 MHz) does **not** set the pattern
generator's pixel clock.

**This is a capability, not a curiosity.** PCLK is now freely settable,
independently of geometry:

| divN | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|
| PCLK MHz | 36.6 | 30.5 | 26.1 | 22.9 | 20.3 | 18.3 | 16.6 | 15.2 |

`divN` 5..12 keeps PCLK inside the 302's 15-45 MHz window. `divN` is now a
**per-entry field** in `ub925_sweep.ino` so each geometry gets a divider landing
it near 60 Hz; `D <n>` overrides it globally and `D 0` restores per-entry values.

**Caveat on that test:** at divN=6, CH1/CH2/CH3 (HS/VS/DE) read 47.9/45.4/36.0
kHz — only DE matched the expected 36.2 kHz line rate. VS showing ~45 kHz at
99.8% duty is narrow glitching, most likely **crosstalk** onto pin 7 from the
adjacent fast-switching pins 6 and 8 at the higher clock. Not investigated. The
PCLK result stands regardless — it comes from CH0 alone.

**Still outstanding:** `la_measure_clock` above 100 MHz remains untested — see
the caveat below.

**TOOL CAVEAT: `la_measure_clock` at 200m and 400m returned zero edges** on a
channel that read 23 MHz at 100m moments earlier. This was *not* the rate
failing — a control re-run of the 100m survey also returned zero, because the
302 had died in between (finding 15, below). **The high-rate path is therefore
untested, not broken.** Retest it before assuming either way.

### 24. NEGATIVE: 24 total geometries swept at 800x480 active — all rejected
**2026-08-15.** The totals sweep built after finding 23 was run in full.

| | |
|---|---|
| entries | **26** (24 distinct total geometries) |
| active size | **800x480 throughout** — the axis the old table wrongly varied |
| hTotal range | 840 .. 1120 |
| vTotal range | 484 .. 530 |
| PCLK range | 22.86 .. 36.58 MHz (divN 8..5) |
| sync polarity | negative on 24, **positive on 2** (never varied before) |
| dwell | 8 s per entry |

**Result: the MID showed the nav loading animation on every entry. Nothing
changed, not even a flicker.**

**Every entry got a fair test.** `925 link=1  302 lock=1 sigdet=1` verified on
entries 14, 15, 16, 25 and 26 — including both divN=5 entries (36.58 MHz, the
highest clock and most likely to drop lock) and both positive-sync entries. No
entry was rejected merely because the link failed.

**Procedural note for whoever reads the log:** the sweep was interrupted at entry
14 on the first pass and resumed from 15, because a full pass at 8 s dwell takes
~3.5 min and was reported complete early. Entries 15-26 were run separately.
Both halves were observed. **When running this sweep, confirm the entry index
with `s` before concluding a pass is done.**

#### What this does and does not establish

**It does not disprove the geometry hypothesis.** 26 samples out of a plausible
grid of ~150 is a sparse search, and the VIU checks hTotal and vTotal
*simultaneously*, so Groups B and C only paid off if their fixed axis was right.

**But the hypothesis is now substantially weaker, and it is worth being explicit
about how thin its evidence always was.** It rests entirely on the *names* of
error codes in `doc/fsl-viu.c` (`ERR_LINE_TOO_LONG`, `ERR_TOO_MANG_LINES`, ...).
That the VIU *can* report a geometry error does not establish that a geometry
mismatch is what is happening here. No evidence has ever been collected showing
the VIU is rejecting anything — or, more fundamentally, **that the VIU is running
at all.**

**The gap that matters: nothing has ever confirmed the Vybrid's VIU is enabled.**
Finding 22 showed the *main board* sets the video-source field (`[163]` = `0x43`
nav / `0x41` phone). That is the MB91F577 **requesting** video. It is not
evidence that the Vybrid acted on the request and started its capture unit.
Every experiment since has assumed it did.

#### Re-opened: the BT.656 refutation is narrower than it reads
The "REFUTED hypothesis" note under "Cluster ICs" dismisses 8-bit BT.656
embedded-sync mode because the fact sheet says 24-bit parallel, the datasheet
shows `VIU_D[23:0]`, and the board routes 24 lines. **All of that is about what
the hardware supports and how it is wired. None of it is about how the firmware
configures the VIU.** A VIU with 24 traces routed to it can still be programmed
for embedded-sync capture. Treat input *mode* as live again, not closed.

#### The blocking instrument problem
Every judgement in this project's video work is a human looking at the glass.
That caps the searchable space at tens of entries, when the remaining space is
hundreds. **Before another sweep, get a machine-readable signal** — see next
steps.

### 25. NEGATIVE: the inter-board link carries NO video-presence signal
**2026-08-15.** Ran next step 3. DSLogic on both the 16-pin connector
(CH0-CH4 = pins 6,7,8,9,10 per finding 21) **and simultaneously on the 302's
video outputs** (CH12-15 = PCLK/HS/VS/DE), 20 MHz, 200 ms per capture.

**Stimulus, and why it was verified rather than assumed.** Video was removed with
`302 0x02 = 0x70` — `out_en=0` with **bit 6 override still set**, so the OEN pin
cannot re-enable the outputs (datasheet p.40: bit 7 = LVCMOS Output Enable, bit 6
= overrides the OEN/OSS_SEL pins). **Writing `0x00` would have been wrong** — it
releases control to the OEN pin, whose state is unknown, and could have left
video running while appearing to disable it.

The video probes confirmed the stimulus physically each time:

| | PCLK | HS | VS | DE |
|---|---|---|---|---|
| `0x02 = 0xF0` | 22.9 MHz | 27.24 kHz | 60 Hz | 26.94 kHz |
| `0x02 = 0x70` | **static LOW** | **static HIGH** | **static HIGH** | **static HIGH** |

**Result: no byte on either link tracks video presence.**

- **Link A (SPI, 810-byte frames)** — 810 offsets compared, 3 vary within a
  state (offsets 5, 25, 403 = counters/noise). No offset tracks video.
- **Link B (I2C `0x51`, 310-byte frames)** — 310 offsets compared, 2 churn. No
  offset tracks video.

#### The link is WRITE-ONLY — there is no return path
`i2c=address-read` and `i2c=data-read` both return **zero** transactions: six
`Address write: 51` per capture and nothing else. Combined with finding 21's
main -> sub direction for the SPI link, **the Vybrid reports nothing back to the
MB91F577 over pins 6-10.**

**Consequence: this link cannot supply an automated score**, so the plan to
remove the human from the video loop via differential scoring is dead on these
pins. **Pin 4 is still unprobed** ("0 V, idle-low signal, or further ground",
finding 21) and is the only remaining candidate for a return line.

**What this does NOT establish.** It does not show the VIU is disabled. A VIU
that is running perfectly would also produce no traffic here if the Vybrid simply
never reports capture status upstream — which, on a write-only link, it cannot.
**The negative is about the link, not about the VIU.** The question "is the VIU
enabled?" remains open and now has no cheap instrument.

#### TRAP THAT ALMOST PRODUCED A FALSE POSITIVE — read before diffing anything
The first pass reported **offset 216 changing `0x1A` (video on) -> `0x1B` (video
off)**, consistent across both repeats and stable within each state — passing
finding 21's stated criteria exactly. **It was an artifact.**

All four captures were taken as A,A,B,B — every A before every B. **Any value
that simply changes once over time satisfies "differs between states, stable
within each state".** A reversal control (restore video, capture again) settled
it:

```
video ON   -> 1A     video OFF  -> 1B     video ON again -> 1D
```

It does not return. **`[216]` is a free-running counter**, not a state field.

**Amend finding 21's procedure: capture A, B, then A again.** Two captures per
state is not enough — the repeats must be interleaved or the reversal confirmed,
or slow counters masquerade as stimulus-tracked fields.

#### This casts doubt on part of finding 22's field map
Measured now, with nav selected: `[163] = 0x43` (constant — **finding 22's core
claim is corroborated**), but `[182] = [183] = 0x00` while `[216] = 0x1A`.

Finding 22 states `[182],[183] = [216] x 4`. **That relationship does not hold
here.** And since `[216]` is now shown to be a counter, and finding 22's three
captures (default, nav, phone) were necessarily taken **in time order**, its
`[216]` values of 9/10/12 are equally consistent with a counter climbing as with
a screen index.

**Treat `[216]` and `[182]/[183]` in finding 22's field map as UNRELIABLE** until
re-tested with a reversal control (select nav, then default, then nav again).
`[163]` and `[19:20]` (tachometer, verified proportional across an RPM change)
are unaffected — proportionality is not something a counter mimics.

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

**Read the `302` prefix carefully.** Unprefixed lines are 925 registers,
`302 …` lines go through the link to the deserializer, and `0x64`/`0x65` appear
on *both* sides meaning *different things*. Writing the 925's `0x65` value to
the 302 is what broke the control channel on 2026-08-15 — see finding 8.

---

## Tools written

| File | Purpose |
|---|---|
| `ub302_patgen.ino` | ESP8266, direct local I2C to the 302. Pattern generator, indirect timing, register access. **Note: its README claims no serializer needed — that is wrong, see finding 2.** |
| `ub925_link.ino` | ESP8266 on the serializer. `C` = full cold-start bring-up. Reaches the 302 through the link (`S`, `o`, `y`, `Y`). Strap decode, link/backchannel status, patgen. |
| `ub925_sweep.ino` | **REBUILT 2026-08-15.** Cold start + sweeps **26 entries / 24 distinct total geometries**, all at 800x480 active (finding 24). `divN` is now a **per-entry** field: `PCLK = 182.9 MHz / divN` (finding 23), so each geometry gets a clock landing it near 60 Hz. `D <n>` overrides, `D 0` restores per-entry. `T <ms>` sets dwell. |
| `scripts/video_timing.py` | Extracts PCLK / hTotal / **vTotal** / hsw from a raw `.sr` capture of PCLK+HS+VS+DE, by counting HS pulses between VS edges (exact integer, immune to rate-ratio quantisation). Produced finding 23. Needs numpy. |
| `scripts/interboard_diff.py` | Diffs the inter-board SPI + I2C state blocks between two stimulus states, reporting only offsets stable within each state and differing across both repeats. Produced finding 25. **Read finding 25's trap note before trusting a hit — add a reversal control.** |
| `PCB_REWORK.md` | Serializer board rework instructions. |

All ESP8266 sketches: `Wire.begin(SDA, SCL)` + `setClock()`. **Never**
`Wire.begin(100000)` — the single-argument form is the slave-mode constructor.

---

## Where it's blocked

Everything electrical is confirmed green:

```
925 link      : 1        302 lock    : 1
302 outputs   : 0xF0     925 patgen  : 0x11
```

**Current diagnosis (2026-08-15, after findings 23, 24 and 25). The cause is NOT
identified. Read this before adopting any hypothesis from older sections.**

What is now established rather than inferred:

- **The main board requests video.** `[163] = 0x43` (nav) / `0x41` (phone),
  constant and re-confirmed in finding 25. Nothing is withholding permission.
- **We deliver valid video, measured at the 302's pins** (finding 23):
  22.89 MHz, 840x485 total, 800x480 active, hsw 10, 56.19 Hz. Not inferred from
  register bits — measured, and reproduced across a power cycle.
- **The VIU interface is a 1:1 native match** for the 302's output
  (`VIU_PCLK / VIU_DE / VIU_HSYNC / VIU_VSYNC / VIU_DATA0..23`), and every
  parameter is in spec: 24-bit parallel, well under the 64 MHz VIU ceiling,
  800x480 against a WVGA maximum.

**So valid, in-spec video is physically present at the compositor's input while
the compositor is asking for video, and nothing appears.**

**The leading hypothesis — VIU geometry validation — has been tested and did not
pay out.** Finding 24 swept **24 distinct total geometries** at 800x480 active,
both sync polarities, PCLK 22.9-36.6 MHz, every entry with link and lock
verified. All rejected. That does not disprove it (the space is ~150 and both
axes must match at once), but note how thin its support always was: it rests
**entirely on the names of error codes** in `doc/fsl-viu.c`. No evidence has ever
been collected that the VIU is rejecting anything.

**The untested assumption underneath everything: is the VIU even enabled?**
Finding 22 showed the *main board* requesting video. That the Vybrid acted on the
request and started its capture unit has been assumed by every experiment since,
and finding 25 showed there is **no way to observe it from outside** — both
inter-board links are write-only, so the Vybrid reports nothing back.

**Live hypotheses, none eliminated:**

1. **The VIU is not enabled**, or is waiting on something internal. Geometry
   would then be entirely the wrong axis.
2. **Wrong input mode** — e.g. BT.656 embedded sync rather than 24-bit RGB with
   separate syncs. The "REFUTED" note under "Cluster ICs" only established what
   the hardware *supports* and how the board is *wired*, **not how the firmware
   configures the VIU**. Re-opened.
3. **Geometry after all**, with the right totals outside the 24 tried.
4. **Something downstream of capture** — DCU layer/blend config, or the loading
   layer never being torn down because the Vybrid waits on an unrelated event.

All four are questions about **firmware**, which is why the flash dump is now the
next action rather than more black-box search.

**Eliminated — do not re-open:**

- **A CAN handshake.** Findings 9, 10, 20, 22. The cluster gateways F-CAN to
  B-CAN and is fully responsive, its boot-time `0xF810` request is real but is
  not a video gate, and it commands video mode regardless.
- **An I2C handshake with the 302.** Finding 19: register `0x18` is a
  deserializer reset watchdog, not a display trigger.
- **A missing inter-board flag.** Finding 22, reinforced by finding 25.
- **A feedback signal on the 16-pin link.** Finding 25: both links are
  write-only, main -> sub. Only pin 4 remains unprobed.
- **"The compositor gates unconditionally."** Finding 16 claimed this and
  **overstated it** — the 302's external-timing patgen inherits the 925's
  timing, so it never tested a different geometry.
- **"Our outputs might not physically be driving."** Finding 23 measured them.

---
## Next steps, in order

**Read this first.** The cluster **is already requesting video and rejecting what
we send** — there is no missing handshake on CAN, on the 302's I2C, or on the
inter-board link (findings 19, 20, 22, 25). Do not restart a search for a trigger
to send.

**But do not inherit the VIU-geometry hypothesis either.** It was the leading
theory, 24 geometries were swept against it, and nothing hit (finding 24). The
cause is **not identified** — see "Where it's blocked" for the four live
hypotheses. Everything cheap and black-box is exhausted; the remaining questions
are all about firmware.

### Open, highest value first

**Reordered 2026-08-15.** Measuring the delivered pixel clock was promoted above
the flash dump, because it is a **prerequisite for both paths**: if the clock is
wrong, reading the target geometry out of the firmware still leaves us unable to
produce it. See item 1 and the probe pinout under "Cluster ICs".

1. **Measure the real video timing at the 302's parallel output. — DONE, see
   finding 23.** Fully measured and reproduced across a power cycle:
   **PCLK 22.89 MHz, hTotal 840, vTotal 485, hsw 10, 800x480 active, 56.19 Hz** —
   i.e. exactly sweep entry 1. **PGCDC IS in the clock path** (finding 6 settled;
   `PCLK = 182.9 MHz / divN`, so PCLK is freely settable 15.2-36.6 MHz), and the
   outputs are now *measured* to be physically driving, which closes the caveat
   findings 13 and 16 both left open. Only loose end: `la_measure_clock` above
   100 MHz is untested (not known broken).

   *Original entry, retained for the pinout reference:* the pin numbers are now
   known (PCLK 5, DE 6, VS 7, HS 8 —
   contiguous; full probe pinout, threshold caveat, soldering hazards and
   sample-rate staging are in the "302 parallel-output probe points" subsection
   above). Confirms what we are *actually* sending rather than what we believe we
   are sending, and settles finding 6's open question about whether PGCDC sits in
   the clock path. `la_measure_clock` is built and validated for it.

   **Why this came first (historical — the concern was resolved):** the old
   eleven-timing sweep's header *assumed* pixel clock == the `0x14` oscillator
   and said to verify by scoping pin 5, which had never been done. Had PGCDC
   divided the 25 MHz oscillator by 8, real PCLK would have been ~3.125 MHz —
   below the 302's 15-45 MHz window — and every entry would have failed for
   reasons unrelated to geometry. **Measurement showed PCLK ~22.9 MHz, so that
   did not happen** (though PGCDC *is* in the path, dividing ~182.9 MHz instead —
   see finding 23). That header has since been rewritten with the measured
   relationship.

2. **Targeted totals sweep — DONE 2026-08-15, CLEAN NEGATIVE. See finding 24.**
   All 26 entries ran with link and lock verified; the MID showed the loading
   animation throughout. Do **not** simply extend this table and re-run it — the
   remaining space is ~150 entries and the instrument is a human watching the
   glass. Get a feedback signal first (item 3). Table description follows.
   `ub925_sweep.ino` now carries **26 entries covering 24 distinct total
   geometries, all at 800x480 active**. The old table had **three** at the
   correct active size (840x485, 900x500, 1056x525); its other seven of eleven
   entries changed *active* resolution away from 800x480 (640x480, 720x480,
   480x272, 400x240, 800x600, 1024x600, 1280x480), which cannot produce a picture
   on an 800x480 panel and so tested nothing about the VIU's geometry check.

   Structure — a prior-ranked search, not a grid:
   - **CTRL** — 840x485, the geometry measured in finding 23 and known rejected.
     Present so a sweep with no positives still proves the rig was working.
   - **Group A (9)** — real-world published 800x480 timings. Highest prior.
   - **Group B (6)** — hTotal swept 840..1120, vTotal held at 525.
   - **Group C (8)** — vTotal swept 485..530, hTotal held at 1056.
   - **Group D (2)** — positive sync polarity on the two likeliest geometries.
     Every entry in the old table was negative sync, so polarity was never varied.

   **The VIU checks both axes, so hTotal and vTotal must be right
   simultaneously** — Groups B and C only pay off if the value each holds fixed
   happens to be correct. A full grid over the plausible ranges is ~150 entries;
   this is the ~26 worth trying first. Validated in-file: every entry has a
   non-negative front porch, fits the register field widths, and lands PCLK in
   15-45 MHz at 54-64 Hz.

   To run: flash, `C` (cold start), `T 8000` (dwell — the 6 s default may be
   tight for the VIU to lock and the Vybrid to composite), then `w`. ~3.5 min for
   a full pass. Watch the glass; there is no machine-readable success signal.

   A null result also means something different now: pre-finding-22, "no picture"
   was ambiguous between a missing handshake and wrong timing. Finding 22 closed
   the handshake branch, so a null is now attributable to the video itself.

3. **~~Get a machine-readable signal from the inter-board link~~ — DONE
   2026-08-15, NEGATIVE. See finding 25.** No byte on either link tracks video
   presence, and both links are **write-only** (main -> sub), so the Vybrid
   reports nothing back on pins 6-10. There is no automated score here, and the
   VIU question is *not* answered — the negative is about the link, not the VIU.
   Tooling kept: `scripts/interboard_diff.py`. **Only remaining candidate on this
   connector: pin 4**, still unprobed. Original plan below for reference.

   *(superseded)* **Establish whether the Vybrid's VIU is even running — and get a
   machine-readable signal.**
   Everything since finding 22 has assumed the Vybrid acted on the main board's
   video-source request and started its capture unit. **That has never been
   tested.** If the VIU is not enabled, geometry is the wrong axis entirely and
   further sweeping is wasted.

   Proposed test, non-destructive, using tooling that already exists:
   - Re-probe the 16-pin inter-board connector (finding 21 pinout: SPI on 6/7/8,
     I2C 0x51 on 9/10).
   - Capture the state block **with valid video present** (patgen on, lock
     confirmed) and **with it absent** (`302 0x02 = 0x00`, or patgen off), two
     repeats each, per finding 21's validated differential procedure.
   - Diff. Finding 21 showed excellent signal-to-noise on this link — one
     stimulus moved 4 bytes of 1620.

   **If a byte moves**, the Vybrid observes video presence: the VIU is alive, the
   geometry search is the right branch, *and that byte becomes the automated
   score* for a much larger sweep — removing the human from the loop, exactly as
   the F-CAN feedback channel did for warning lamps.

   **If nothing moves across repeated trials**, the VIU is probably not enabled
   and the answer is in the firmware, not in the timing space.

   Also worth checking while probing: whether Link B (I2C `0x51`) carries **reads**
   as well as writes. Finding 21 established main -> sub for the SPI link; a read
   channel would be the Vybrid reporting status back, which is where a
   "video detected" flag would live.

4. **Dump BOTH S25FL512S flashes. — NOW THE TOP PRIORITY (2026-08-15).**
   Every cheap black-box avenue is exhausted: CAN, the 302's I2C, the inter-board
   link, and 24 total geometries. All four surviving hypotheses in "Where it's
   blocked" are questions about firmware.

   **Look for four things, in this order — not just geometry:**
   1. **Is the VIU initialised at all?** Writes to VIU control registers. If it
      is never enabled, geometry was always the wrong axis (finding 24).
   2. **What input MODE is configured** — 24-bit RGB with separate syncs, or
      BT.656 embedded sync. Re-opened; the old refutation only covered hardware
      capability and board wiring, not firmware configuration.
   3. **The expected geometry** — total line length and lines per field. This
      was the original goal; it is now one of four, not the whole job.
   4. **The DCU layer/blend path** — what tears down the loading layer, and
      whether it is gated on capture status or on something unrelated.

   Procedure and the interleaving trap are in "Cluster ICs" above:
   `RDID` first, dump both, sanity-check each image alone, de-interleave if
   neither is sane. SOIC-16 on the underside.

   **CORRECTION 2026-08-15 — do NOT dump these in-circuit.** An earlier version
   of this line suggested a clip in-circuit. That is unsound *for these specific
   parts*, because they are the Vybrid's **boot** devices:
   - Board powered → the Vybrid drives CS/CLK/IO the instant it leaves reset,
     contending with the programmer. Its RESET_B is on a 364-pin MAPBGA and is
     not accessible, so the contention cannot be prevented.
   - Board unpowered, flash fed from the programmer → current back-feeds the
     Vybrid's QuadSPI pins through its ESD diodes and partially energises its I/O
     rail, giving reads that are *mostly* right. **That is the worst outcome
     available**, because the corruption would be misattributed to the
     interleaving trap documented above.

   So the dump requires desoldering. **The cluster must survive — there is no
   spare.** Use low-melt alloy (ChipQuik) rather than an iron alone; a lifted pad
   on a fine-pitch SOIC-16 is unrecoverable here.

   Programmer: **Raspberry Pi Zero + `flashrom` over `spidev`.** `flashrom` has
   the S25FL512S in its chip database, so 4-byte addressing is handled — 512 Mbit
   exceeds the 3-byte address space, and a 3-byte dumper silently reads the first
   16 MB four times and looks plausible. An ESP8266 is a poor fit: no storage, so
   64 MB has to stream over serial (~1.6 h/chip at 115200, and no flow control at
   higher rates without a bespoke CRC'd block protocol). A Pi Pico works as a
   fallback via `pico-serprog` + `flashrom`'s `serprog` protocol.

5. **Get the Vybrid VF5xx/VF6xx reference manual** (`VFXXXRM` — *not* the
   `VYBRIDFSERIESEC` datasheet, which is electrical only, and is already in
   `doc/`). Three chapters matter:
   - **VIU** — the geometry registers the capture unit validates against, and
     the full error semantics behind `ERR_LINE_TOO_LONG` etc.
   - **QuadSPI** — confirms the dual-flash interleave mode and granularity.
   - **DCU** — layer config and the blend/enable path.

6. **Source a donor Display Audio head unit.** Still the ground truth: it would
   show the exact video geometry the cluster expects, on a scope, in one
   measurement — plus the real `0xF810` B-CAN payload as a bonus.

### Done — do not repeat

- ~~Recover the wedged 302~~ — power cycle + `C` (finding 8).
- ~~302-patgen experiments~~ — internal timing is unusable (finding 11, drops
  LOCK); external timing was run correctly (finding 16). **Findings 13 and 16
  overstated their conclusions and are marked retracted/overstated — cite them
  only with those caveats.**
- ~~Read the graphics IC part number~~ — NXP Vybrid VF522R3 (see "Cluster ICs").
- ~~Capture the graphics IC's I2C to the 302~~ — done; it is a reset watchdog on
  register `0x18`, not a video gate (finding 19).
- ~~Probe the 16-pin inter-board connector~~ — done; decoded, field-mapped, and
  it produced finding 22 (findings 21 and 22).
- ~~Answer whether the Vybrid ingests parallel video~~ — yes, VIU with
  `VIU_D[23:0]`, natively matched to the 302 (see "Cluster ICs").

### Dead ends — recorded so they are not re-tried

- **Searching for a CAN or I2C handshake.** Finding 22: the cluster already
  commands video mode. The `0xF810` B-CAN request (finding 20) and the 302's
  `0x18` mailbox (finding 19) are both real, both understood, and neither gates
  video.
- **Broad 925 timing sweeps over active resolution.** The active size is right.
- **Extending the totals sweep and re-running it by eye.** Finding 24 covered 24
  geometries with no hit; finding 25 established there is **no automated score**
  available, so a human must watch every entry. The remaining space is ~150.
  **Do not grind it** — resolve the firmware questions first, then sweep a
  target rather than a space.
- **Looking for a Vybrid status report on the 16-pin link.** Finding 25: both
  links are write-only. Only pin 4 is unprobed.
- **Passive B-CAN logging on this bench.** Finding 10: every ID here is static.

## CAN checksums — FIXED 2026-08-15

`encode()` built the counter/checksum byte with the **previous** call's
checksum, then computed the new one, so the transmitted checksum lagged a frame.
The per-frame `checksum_offset` of 7 or 5 was empirical compensation for that
lag.

Measured against the reference Honda algorithm, before and after:

| | valid frames |
|---|---|
| old code | **45 / 104** |
| now | **104 / 104** |

The old numbers break down exactly as predicted: `offset = 7` frames valid for
three counter values out of four and failing at the 3→0 wrap, `offset = 5`
frames (CRUISE 0x324, RADAR_HUD 0x39F, SEATBELT 0x305, HIGHBEAM 0x35E) never
valid at all.

What changed in `cluster_frames.py`:
- The 13 near-identical frame classes now share a `ClusterFrame` base, so the
  ordering is defined once: advance counter → write counter with an empty
  checksum nibble → checksum → merge. Subclasses override `pack()` for signals.
- `checksum_offset` is gone. The offset is a uniform 8, per the reference
  algorithm. `calc_checksum` now also adds 3 for extended IDs — that branch was
  stubbed out as `if extended_frame: pass`. **Untested on hardware**, no
  standard-ID frame exercises it.
- `Frame_SEATBELT_STATUS` no longer writes a bare checksum into byte6 without
  the counter nibble.
- `encode()` returns exactly `dlc` bytes rather than always 8.

`test_checksum.py` validates every frame across two full counter cycles against
an independently transcribed reference. Run it with plain `python3`, no deps.

TX cadence is now handled by the scheduler in `scripts/mcp_servers/can_engine.py`
(10 ms powertrain, 100 ms HUD/status), measured accurate to 0.1 ms. The old
`main.py` Pi path still has no cadence — its loop rate is set by the SSD1306
refresh — and was left alone.

---

## Bench tooling — added 2026-08-15

Two MCP servers, registered in `.mcp.json`. See
`scripts/mcp_servers/README.md`.

- **`civic-can`** — both CANables. Scheduled F-CAN broadcast, per-frame
  enable/disable and retiming for attributing a lamp to one frame, `frame_peek`,
  raw send, and `sniff` for grouping received traffic by ID.
- **`civic-esp`** — the ESP on `/dev/ttyUSB0`. Detects which firmware is flashed
  and maps commands accordingly, because `ub925_link` and `ub925_sweep` use
  conflicting letters (`l` is link status on one and the timing table on the
  other) and the wrong letter fails silently.

**CORRECTED 2026-08-15 — this line was stale and cost time.** It previously read
"the ESP currently runs `ub925_sweep.ino`". As of 2026-08-15 the only ESP
attached is on **`/dev/ttyUSB0` running `ub302_patgen`** — i.e. the **302-local**
board, not the serializer. The 925-side ESP is **not plugged in at all**.

That matters for two reasons, both of which caused wrong inferences this session:
- **`ub302_patgen` does not cold-start the link on boot**, whereas `ub925_sweep`
  does. Plugging this ESP in does *not* bring the link up. The link was live
  during finding 23 only because the 925 retained its configuration from an
  earlier session — 925 registers persist until *its* board loses power.
- **Which port holds which firmware is not stable.** `ttyUSB1` and `ttyUSB2` both
  existed earlier in the day and were unplugged; the survivor re-enumerated as
  `ttyUSB0`. **Always confirm with `esp_firmware`/`esp_open` rather than trusting
  a port number or this file.** `civic-esp` detects the firmware for exactly this
  reason — use it.

Confirmed live on 2026-08-15 through the new tooling:

```
925: 0x0C=03 link=1 pclk=0 | 0x14=06 0x64=11 0x65=04
302: 0x1C=03 lock=1 sigdet=1 | 0x02=F0
timing entry 1/11, divN=8, pattern=1
```

### The adapters are wired opposite to their ttyACM numbers

Determined by sweeping bitrates and watching where traffic appeared:

| Bus | USB serial | ttyACM (at the time) | Rate | IDs |
|---|---|---|---|---|
| F-CAN | `208838614D4D` | ttyACM2 | 500 k | standard 11-bit |
| B-CAN | `207D387C4D4D` | ttyACM1 | 125 k | extended 29-bit |

`can_engine.py` now resolves adapters through `/dev/serial/by-id` by USB serial,
so replugging cannot reintroduce the swap.

### F-CAN milestone: reached

`scripts/fcan_broadcast.py --rpm 2500 --speed 60` — 13,413 frames, **zero TX
errors**, so every frame is being ACKed. George confirmed on the glass: gauges
read 2500 rpm and 60 kph, cluster otherwise clean.

**Remaining lamps: airbag information, and autohold flashing.** Not yet
attributed to a frame.

### The checksum algorithm is confirmed against real hardware

`calc_checksum` was run over every frame the cluster itself broadcasts:
**874/874 match**. This is no longer a simulation against a transcribed
reference — the offset-8 algorithm is confirmed against genuine Honda traffic.

The cluster broadcasts 15 IDs on F-CAN, none colliding with the 13 we transmit:

```
0x221  40ms   0x296  40ms   0x309 100ms   0x326 100ms   0x371 100ms
0x372 100ms   0x374 100ms   0x378 100ms   0x37B 100ms   0x396 100ms
0x3A1 200ms   0x405 300ms   0x428 300ms   0x510 500ms   0x516 500ms
```

### A machine-readable feedback channel exists

Four of the cluster's own broadcast IDs change their payload depending on what
we send — comparing a silent bus against our 13 frames running, with the
counter/checksum byte masked:

| ID | silent | broadcasting |
|---|---|---|
| `0x309` | `00 00 00 00 00 00 00` | `17 9D 3C 3C 17 84 00` |
| `0x378` | `00 00 00 00 FF E0 00` | `00 00 00 00 42 C0 00` |
| `0x516` | `00 23 70 F8 68 00 00` | `00 23 70 20 68 00 00` |
| `0x374` | 4 payloads, `00 00 80 00 xx` | 2 payloads, `00 00 00 00 xx` |

`0x309` byte2 and byte3 both read `0x3C` = 60 = the speed we sent, so the
cluster is demonstrably consuming our data.

**This matters because it removes the human from the loop.** Warning-lamp
attribution no longer necessarily requires someone looking at the cluster — a
bit sweep can be scored automatically by watching whether these four IDs move.

### UDS / diagnostics: negative result

Tried and found nothing. Recorded so it is not re-attempted blindly:

- 11-bit sweep of the whole `0x700`–`0x7FF` range on F-CAN — silent
- `0x7DF` functional (TesterPresent, OBD mode 01, UDS `19 02`, KWP `18 02`) on
  **both** buses — silent
- 29-bit `0x18DB33F1` functional on **both** buses — silent

Consistent with Honda routing diagnostics through a gateway that is not on the
bench. `scripts/uds_scan.py` holds the scanner.

**Trap worth remembering:** an early fast scan appeared to find responders at
`0x738`/`0x739`. They were slcan frame misparses caused by serial buffer
pressure, not ECUs — the payloads (`C0 00 …`) were not valid ISO-TP headers, and
they answered every request ID indiscriminately. A control run transmitting on
`0x100` reproduced nothing. **Scan slowly and always run a no-transmit control.**

### B-CAN

`scripts/rpi_can_control/bcan_frames.py` is scaffolding — no frame meanings
reversed yet, but the bus is now characterised. 28 IDs, all extended, all
ending in `0x50` (almost certainly a node address), periods of
100/200/300/500/1000 ms, and **completely static payloads** — not one ID varied
across a capture, so these carry no rolling counter.

The Honda counter/checksum scheme **does not apply on B-CAN**: 2/793 captured
frames matched, below chance, against 874/874 on F-CAN. Use `RawBCanFrame`;
`BCanFrame` is kept only in case a frame turns up that does use the F-CAN
scheme, and stays unverified.
