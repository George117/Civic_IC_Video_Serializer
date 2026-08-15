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
| Video on the MID | **Blocked** — compositor IC between the 302 and the panel |

The video link problem is **solved**. The remaining blocker is a graphics IC
with external DRAM sitting between the deserializer and the panel, which
composites and gates what reaches the glass. It shows "loading" and is waiting
on something — most likely a CAN handshake from the head unit.

**2026-08-15 — two results settle the video question.**

**Finding 16: the graphics IC discards valid pixels.** Proven with the 302's own
patgen in external-timing mode, LOCK / output-enable / patgen-enable all verified
before *and* after the observation. **The timing hypothesis is dead — stop
sweeping video timings.** (Two earlier runs of this test were confounded; see
findings 11 and 13. Cite only 16.)

**Finding 14: the graphics IC is an active I2C master on the 302's local bus.**
It clears the 302's output-enable and patgen-enable registers on its own,
event-driven, correlated with cycling the MID menus. Its traffic is the most
direct lead on the handshake, and it is on a bus we already probe.

The enabling capability behind both is a local ESP on the 302's I2C (finding 12),
which removes the power-cycle loop and can read the part when the link is down.

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

### 14. PARTLY SUPERSEDED by finding 17 — read the correction first
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

### 14. CONFIRMED: a third I2C master on the 302's local bus
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

### 17. THE HANDSHAKE: the graphics IC polls undocumented register 0x18 at 17 Hz
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

**This is the most promising lead in the project.** The compositor is asking the
deserializer one question, continuously, and the answer is not changing. The
obvious experiment is to change what it reads and watch the MID — the poll rate
means any reaction appears within ~60 ms.

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

---

### 16. ESTABLISHED: the compositor discards valid pixels
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

**2026-08-15 update.** Findings 9 and 10 tighten this. The cluster demonstrably
consumes our F-CAN and republishes it on B-CAN, so the CAN side is alive and
responsive — yet nothing on B-CAN so much as ticks while the MID sits at
"loading". So the compositor is not waiting on anything it *asks* for over B-CAN.
That is consistent with the handshake hypothesis but narrows it: the trigger is
a frame the head unit **sends unprompted**, which we have to originate.

**DECIDED 2026-08-15 — finding 16.** The 302's external-timing patgen was armed
with LOCK, output-enable and patgen-enable all verified *before and after* the
observation (held=30/30). The MID still showed the loading animation. Valid
pixels reach the graphics IC and it does not put them on the glass.

**Stop sweeping video timings.** The failure survives generating pixels after the
link, so no timing can fix it. Two earlier attempts at this test were confounded
(findings 11 and 13) — the conclusion only stands because the third attempt
bracketed the observation with evidence.

The whole problem is now: **what is the graphics IC waiting for?** The strongest
lead is finding 14 — it is an active I2C master on the 302's local bus and its
writes are event-driven, correlated with MID menu changes. That is better than
the CAN angle because it is observable on a bus we already have a probe on.

---

## Next steps, in order

0. ~~**Recover the 302.**~~ **DONE 2026-08-15** — power cycle + `C` restored it,
   verified by raw reads (`302 0x1C`=`03`, `0x02`=`F0`). If it ever recurs: same
   procedure, and verify with raw reads rather than the decoded flags, since
   `0xFF` prints as a false `lock=1 sigdet=1`. See finding 8. (`DESID=0x58` is
   correct and expected — it is the documented Device ID, not a fault.)
1. ~~**Retry the 302-patgen experiment.**~~ **DONE 2026-08-15 — answered.**
   Internal timing was confounded (finding 11, LOCK=0); external timing gave the
   clean negative (finding 13). The compositor discards valid pixels. Do not
   re-run either variant.
2. **Capture the graphics IC's I2C traffic with a logic analyser on the 302's
   SDA/SCL (pins 2/3).** Now the single highest-value action. Finding 14 proves
   it writes to the 302, event-driven around MID menu changes, but polling only
   samples the *result* — a capture gives the actual transactions: which
   registers, what values, in what order, and how they relate to the loading
   state. That is the compositor's own conversation with the deserializer, and
   it is the most direct window we have on what it is waiting for.
   Trigger idea: arm the capture, then change MID menus, since that is the
   stimulus already known to provoke writes.
2b. ~~Check whether the compositor writes to the 302 over local I2C.~~
   **DONE — confirmed, finding 14.** Several
   registers read non-default with no explanation: `0x05` I2C Control = `0x1E`
   (datasheet `0x2E`), `0x44` Equalization = `0x30` (default `0x60`), `0x2C`
   SSCG = `0x8B`. We never wrote them and the cluster had been power-cycled. If
   the graphics IC configures the 302, **it is a third master on that bus and its
   traffic is a direct window into the handshake.** Cheap test with the local ESP
   (finding 12): `d` dump, cycle the MID through its menus, `d` again, diff — the
   same stimulus/diff method that produced findings 9 and 10 on B-CAN. Baseline
   dump 2026-08-15:
   `00=58 01=04 02=F0 03=F0 04=FE 05=1E 06=00 07=18 1C=03 1D=A0 1E=00 1F=00
   24=08 25=00 2A=00 2B=00 2C=8B 41=03 44=30 56=08 64=11 65=00`
   Caveat: could equally be strap-derived or power-on defaults the truncated
   datasheet table misreports. Confirm before building on it.
3. **Read the part number off the graphics IC.** Photograph the markings. If it's
   a Socionext MB86R, Renesas R-Car, or similar documented part, the problem
   becomes tractable. Highest value action overall.
4. **Scope 302 pin 5 (PCLK)** with the 302's external-timing patgen running.
   Now a narrow confirmation rather than an open search: finding 13 infers the
   outputs are driving from register bits, and this measures it. Also gives the
   real pixel clock, resolving whether PGCDC is in the clock path. Pin 32 (LOCK)
   no longer needs probing — finding 12 reads it over local I2C.
   (The sweep script's Hz figures assume PCLK = the `0x14` oscillator; AN-2198
   documents a 200 MHz internal oscillator for the 92x parts but the 925/302
   pairing isn't in that table.)
5. **Source a donor Display Audio head unit.** Unblocks everything:
   scope its FPD-Link output for exact expected timing; log B-CAN while cycling
   the MID to find the trigger frames; see whether "loading" resolves with the
   real unit present.
6. **Failing that, passively log B-CAN (125 kbps) from a running Gen 10** while
   someone cycles the MID through its screens, and diff. Note finding 10: this
   only works against a car whose MID actually changes state. Logging this bench
   rig produces a flat capture — every B-CAN ID here is static.

---

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

**The ESP currently runs `ub925_sweep.ino`**, not `ub925_link.ino`.

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
