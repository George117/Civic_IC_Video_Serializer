/*
 * ub925_link.ino - DS90UB925Q serializer bring-up and link verification
 *
 * Companion to ub302_patgen.ino. This one sits on the SERIALIZER side and
 * answers, in order:
 *
 *   1. Is the chip alive and at the expected address?
 *   2. Did MODE_SEL strap to the only setting compatible with a DS90UB302Q?
 *   3. Is the FPD-Link cable up?
 *   4. Did the back channel come up (deserializer ID auto-loaded)?
 *   5. Can I reach the remote 302's registers through the link?
 *   6. Can I put a picture on the cluster with no Raspberry Pi involved?
 *
 * Wiring (ESP8266 / NodeMCU) to the serializer board's I2C1 header:
 *   D1 (GPIO5) -> SCL
 *   D2 (GPIO4) -> SDA
 *   GND        -> board GND
 *   Board already has 4.7k pull-ups (R4/R5). Do not add more.
 *
 * Register data from DS90UB925Q-Q1 datasheet (SNLS407D) and AN-2198 / SNLA132G.
 *
 * Type 'h' at 115200 for commands.
 */

#include <Wire.h>

#define SDA_PIN        4       // D2
#define SCL_PIN        5       // D1
#define I2C_HZ         100000

// IDx strapped to 0 (R6 DNP, R8 = 40.2k to GND) -> 7-bit 0x0C
#define SER_ADDR       0x0C
// Deserializer, reachable through the link once pass-through is up
#define DES_ADDR       0x2C

// ---- DS90UB925Q direct registers ----
#define REG_DEVICE_ID  0x00   // [7:1] 7-bit address, expect 0x18
#define REG_RESET      0x01   // [1] full reset, [0] reset except regs
#define REG_CONFIG     0x03   // [7] BC check, [4] filter, [3] I2C pass, [1] PCLK auto, [0] TRFB
#define REG_CONFIG1    0x04   // [3] BC from reg, [2] BC val, [1] LFMODE from reg, [0] LFMODE val
#define REG_I2C_CTL    0x05
#define REG_DESID      0x06   // [7:1] deserializer ID, AUTO-LOADED on RX lock
#define REG_SLAVEID    0x07
#define REG_SLAVEALIAS 0x08
#define REG_GEN_STATUS 0x0C   // [3] BIST CRC err, [2] PCLK det, [1] DES err, [0] LINK det
#define REG_REV_ID     0x0D   // [7:4] expect 0xA
#define REG_DATAPATH   0x12
#define REG_MODE_STS   0x13   // [4] decode done, [3] LFMODE, [2] RPTR, [1] BC, [0] I2S-B
#define REG_I2C_PASS   0x17
#define REG_PGCTL      0x64
#define REG_PGCFG      0x65
#define REG_PGIA       0x66
#define REG_PGID       0x67

// ---- DS90UB302Q registers, reached through the link ----
#define DES_RESET      0x01
#define DES_CONFIG0    0x02   // [7] out en, [6] OEN override, [5] OSC clk, [4] OSS_SEL
#define DES_GEN_STATUS 0x1C   // [1] signal detect, [0] lock
#define DES_LINK_ERR   0x41
#define DES_EQ         0x44
#define DES_PGCTL      0x64
#define DES_PGCFG      0x65

// ---- AN-2198 indirect map (same on 925 and 302) ----
#define PG_PGCDC       0x03
#define PG_PGTFS1      0x04
#define PG_PGTFS2      0x05
#define PG_PGTFS3      0x06
#define PG_PGAFS1      0x07
#define PG_PGAFS2      0x08
#define PG_PGAFS3      0x09
#define PG_PGHSW       0x0A
#define PG_PGVSW       0x0B
#define PG_PGHBP       0x0C
#define PG_PGVBP       0x0D
#define PG_PGSC        0x0E

#define PAT_WHITE      0x1
#define PAT_BLACK      0x2
#define PAT_RED        0x3
#define PAT_GREEN      0x4
#define PAT_BLUE       0x5
#define PAT_VRAMP      0xA

static bool     linkWatch = false;
static uint8_t  lastStatus = 0xFF, lastDesId = 0xFF;

// ---------------------------------------------------------------- I2C
static bool wrTo(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg); Wire.write(val);
  uint8_t e = Wire.endTransmission();
  if (e) { Serial.printf("  ! write %02X:%02X = %02X failed (err %u)\n", addr, reg, val, e); return false; }
  return true;
}

static bool rdTo(uint8_t addr, uint8_t reg, uint8_t *val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false)) return false;
  if (Wire.requestFrom(addr, (uint8_t)1) != 1) return false;
  *val = Wire.read();
  return true;
}

static bool wr(uint8_t reg, uint8_t val) { return wrTo(SER_ADDR, reg, val); }
static uint8_t rd8(uint8_t reg) { uint8_t v = 0xFF; rdTo(SER_ADDR, reg, &v); return v; }

static bool wrv(uint8_t reg, uint8_t val) {
  if (!wr(reg, val)) return false;
  uint8_t rb = rd8(reg);
  if (rb != val) { Serial.printf("  ! 0x%02X readback %02X, wrote %02X\n", reg, rb, val); return false; }
  return true;
}

static bool wrInd(uint8_t ia, uint8_t v) { return wr(REG_PGIA, ia) && wr(REG_PGID, v); }
static uint8_t rdInd(uint8_t ia) { wr(REG_PGIA, ia); return rd8(REG_PGID); }

static void passAll(bool on);   // forward decl, used by coldStart()

// --- remote access to the 302 through the forward control channel ---
// Requires 0x03[3] I2C Pass-Through enabled on the serializer.
static uint8_t desRd(uint8_t reg) { uint8_t v = 0xFF; rdTo(DES_ADDR, reg, &v); return v; }

static bool desWr(uint8_t reg, uint8_t val) {
  if (!wrTo(DES_ADDR, reg, val)) return false;
  uint8_t rb = desRd(reg);
  if (rb != val) {
    Serial.printf("  ! 302 0x%02X readback %02X, wrote %02X\n", reg, rb, val);
    return false;
  }
  Serial.printf("  302 0x%02X = 0x%02X OK\n", reg, val);
  return true;
}

// ---------------------------------------------------------------- checks
// 1. identity
static bool checkIdentity() {
  Serial.println(F("\n[1] identity"));
  Wire.beginTransmission(SER_ADDR);
  if (Wire.endTransmission()) {
    Serial.printf("  FAIL: no ACK at 0x%02X\n", SER_ADDR);
    Serial.println(F("  scanning..."));
    for (uint8_t a = 0x08; a < 0x78; a++) {
      Wire.beginTransmission(a);
      if (!Wire.endTransmission()) Serial.printf("    found 0x%02X\n", a);
    }
    Serial.println(F("  -> check IDx strap (R6 DNP, R8 = 40.2k to GND), SDA/SCL, GND"));
    return false;
  }
  uint8_t id  = rd8(REG_DEVICE_ID);
  uint8_t rev = rd8(REG_REV_ID);
  Serial.printf("  0x00 DEVICE_ID = 0x%02X (7-bit 0x%02X)  %s\n",
                id, id >> 1, (id >> 1) == SER_ADDR ? "OK" : "<-- unexpected");
  Serial.printf("  0x0D REV_ID    = 0x%02X (bits 7:4 expect 0xA)  %s\n",
                rev, (rev >> 4) == 0x0A ? "OK" : "<-- unexpected");
  return true;
}

// 2. MODE_SEL strap - the one that must be right for a 302
static bool checkMode() {
  uint8_t m = rd8(REG_MODE_STS);
  Serial.println(F("\n[2] MODE_SEL strap (0x13 Mode Status)"));
  Serial.printf("  0x13 = 0x%02X   want 0x10\n", m);

  bool done = (m >> 4) & 1, lf = (m >> 3) & 1, rp = (m >> 2) & 1;
  bool bc   = (m >> 1) & 1, i2sb = m & 1;

  Serial.printf("    decode complete : %u  %s\n", done, done ? "OK" : "<-- strap not decoded");
  Serial.printf("    LFMODE          : %u  %s\n", lf,
                lf ? "<-- FATAL: 5-15MHz only, 302 needs 15-45MHz" : "OK");
  Serial.printf("    Repeater        : %u  %s\n", rp,
                rp ? "<-- FATAL: 302 is not in a repeater topology" : "OK");
  Serial.printf("    Backward Compat : %u  %s\n", bc,
                bc ? "<-- FATAL: FPD-Link II, 302 is FPD-Link III" : "OK");
  Serial.printf("    I2S Channel B   : %u  %s\n", i2sb,
                i2sb ? "<-- 302 has only 3 I2S signals" : "OK");

  if (m == 0x10) { Serial.println(F("  PASS")); return true; }
  Serial.println(F("  FAIL -> remove MD_SEL1, DNP R7, fit R9 = 40.2k to GND."));
  Serial.println(F("         Try 'v' for the software override (LFMODE + BC only)."));
  return false;
}

// 3. link + 4. back channel
static bool checkLink() {
  uint8_t s = rd8(REG_GEN_STATUS);
  uint8_t d = rd8(REG_DESID);
  Serial.println(F("\n[3] link status (0x0C)"));
  Serial.printf("  0x0C = 0x%02X\n", s);
  Serial.printf("    LINK detect     : %u  %s\n", s & 1, (s & 1) ? "OK" : "<-- no cable link");
  Serial.printf("    PCLK detect     : %u  %s\n", (s >> 2) & 1,
                ((s >> 2) & 1) ? "OK" : "(expected 0 with no DPI running)");
  Serial.printf("    DES error       : %u  %s\n", (s >> 1) & 1, ((s >> 1) & 1) ? "<-- backchannel CRC" : "OK");
  Serial.printf("    BIST CRC error  : %u\n", (s >> 3) & 1);

  Serial.println(F("\n[4] back channel (0x06 DESID, auto-loads on RX lock)"));
  Serial.printf("  0x06 = 0x%02X -> deserializer 7-bit 0x%02X\n", d, d >> 1);
  if (!(d & 0xFE)) {
    Serial.println(F("  FAIL: still zero. No RX lock, or backchannel not established."));
    return false;
  }
  Serial.printf("  PASS: backchannel is up%s\n",
                (d >> 1) == DES_ADDR ? " and the ID matches the 302" : " (ID differs from 0x2C)");
  return (s & 1) != 0;
}

// 5. reach the remote 302 through the link
static void checkRemote() {
  Serial.println(F("\n[5] remote access to the 302 through the link"));
  uint8_t v;
  if (!rdTo(DES_ADDR, 0x00, &v)) {
    Serial.printf("  FAIL: no response from 0x%02X via pass-through\n", DES_ADDR);
    Serial.println(F("  (needs LINK up; try 'P' to force I2C pass-through all)"));
    return;
  }
  Serial.printf("  302 0x00 = 0x%02X (7-bit 0x%02X) %s\n", v, v >> 1,
                (v >> 1) == DES_ADDR ? "OK" : "<-- unexpected");
  uint8_t st;
  if (rdTo(DES_ADDR, 0x1C, &st))
    Serial.printf("  302 0x1C = 0x%02X   lock=%u  signal_detect=%u\n", st, st & 1, (st >> 1) & 1);
  Serial.println(F("  PASS: bidirectional control channel confirmed."));
}

static void config() {
  uint8_t c = rd8(REG_CONFIG), c1 = rd8(REG_CONFIG1), dp = rd8(REG_DATAPATH);
  Serial.println(F("\n-- configuration --"));
  Serial.printf("  0x03 = 0x%02X  BC_check=%u  filter=%u  i2c_pass=%u  pclk_auto=%u  TRFB=%u (%s edge)\n",
                c, (c >> 7) & 1, (c >> 4) & 1, (c >> 3) & 1, (c >> 1) & 1, c & 1,
                (c & 1) ? "rising" : "falling");
  Serial.printf("  0x04 = 0x%02X  BC_from_reg=%u BC=%u  LFMODE_from_reg=%u LFMODE=%u\n",
                c1, (c1 >> 3) & 1, (c1 >> 2) & 1, (c1 >> 1) & 1, c1 & 1);
  Serial.printf("  0x12 = 0x%02X  0x17 = 0x%02X\n", dp, rd8(REG_I2C_PASS));
}

static void timing() {
  Serial.println(F("\n-- patgen internal timing (indirect) --"));
  uint8_t t1 = rdInd(PG_PGTFS1), t2 = rdInd(PG_PGTFS2), t3 = rdInd(PG_PGTFS3);
  uint8_t a1 = rdInd(PG_PGAFS1), a2 = rdInd(PG_PGAFS2), a3 = rdInd(PG_PGAFS3);
  Serial.printf("  divider N = %u\n", rdInd(PG_PGCDC) & 0x3F);
  Serial.printf("  total  %u x %u\n", ((uint16_t)(t2 & 0x0F) << 8) | t1, ((uint16_t)t3 << 4) | (t2 >> 4));
  Serial.printf("  active %u x %u\n", ((uint16_t)(a2 & 0x0F) << 8) | a1, ((uint16_t)a3 << 4) | (a2 >> 4));
  Serial.printf("  hsw=%u vsw=%u hbp=%u vbp=%u sync=0x%02X\n",
                rdInd(PG_PGHSW), rdInd(PG_PGVSW), rdInd(PG_PGHBP), rdInd(PG_PGVBP), rdInd(PG_PGSC));
}

// ---------------------------------------------------------------- actions
static void fullCheck() {
  Serial.println(F("\n================ FULL CHECK ================"));
  if (!checkIdentity()) { Serial.println(F("\nStopped: no device.")); return; }
  bool modeOk = checkMode();
  bool linkOk = checkLink();
  if (linkOk) checkRemote();
  config();

  Serial.println(F("\n---------------- verdict ----------------"));
  if (!modeOk)      Serial.println(F("  Fix the MODE_SEL strap first. Nothing else matters."));
  else if (!linkOk) Serial.println(F("  Strap OK, link down -> cable / connector / termination."));
  else              Serial.println(F("  Link up. Try 'g' to push a pattern with no Pi attached."));
  Serial.println(F("-----------------------------------------"));
}

// Serializer-side pattern generator. Needs no DPI input at all - it drives
// the link from the internal oscillator. If this puts a picture on the MID,
// the entire chain from serializer to panel is proven and only DPI remains.
static void patgen(uint8_t pattern) {
  Serial.printf("\n-- 925 patgen: internal timing, pattern %u --\n", pattern);
  uint8_t s = rd8(REG_GEN_STATUS);
  if (!(s & 1)) Serial.println(F("  WARNING: link is down (0x0C bit0 = 0). The 302 gates"));
  if (!(s & 1)) Serial.println(F("  its parallel outputs on LOCK - expect nothing on screen."));
  wrv(REG_PGCTL, 0x00);                  // disable before touching indirect
  wrv(REG_PGCFG, 0x04);                  // 24-bit, internal clock, internal timing
  wrv(REG_PGCTL, (uint8_t)((pattern << 4) | 0x01));
  timing();
}

static void patgenOff() { Serial.println(F("\npatgen off")); wrv(REG_PGCTL, 0x00); }

// ---------------------------------------------------------------- 302 control
// Table 2 of the 302 datasheet: valid parallel data requires an active serial
// input, Lock high, OEN high AND OSS_SEL high. 0xF0 sets output enable (bit 7),
// OEN/OSS_SEL override (bit 6), OSC clock (bit 5) and OSS_SEL (bit 4).
static void desOutputsOn() {
  Serial.println(F("\n-- 302: enabling parallel outputs (0x02 = 0xF0) --"));
  desWr(DES_CONFIG0, 0xF0);
}

static void desOutputsOff() {
  Serial.println(F("\n-- 302: releasing outputs to OEN pin (0x02 = 0x00) --"));
  desWr(DES_CONFIG0, 0x00);
}

static void desStatus() {
  Serial.println(F("\n-- 302 status (through the link) --"));
  uint8_t id = desRd(0x00), s = desRd(DES_GEN_STATUS), c = desRd(DES_CONFIG0);
  Serial.printf("  0x00 = 0x%02X (7-bit 0x%02X)\n", id, id >> 1);
  Serial.printf("  0x1C = 0x%02X   lock=%u  signal_detect=%u\n", s, s & 1, (s >> 1) & 1);
  Serial.printf("  0x02 = 0x%02X   out_en=%u  override=%u  osc_clk=%u  oss_sel=%u\n",
                c, (c >> 7) & 1, (c >> 6) & 1, (c >> 5) & 1, (c >> 4) & 1);
  Serial.printf("  0x44 = 0x%02X (EQ)   0x41 = 0x%02X (link err)\n",
                desRd(DES_EQ), desRd(DES_LINK_ERR));
  Serial.printf("  0x64 = 0x%02X (302 patgen, should be 0x00)\n", desRd(DES_PGCTL));
}

// ---------------------------------------------------------------- cold start
// Full bring-up from power-on defaults. Each step verifies before continuing.
static void coldStart() {
  Serial.println(F("\n############ COLD START BRING-UP ############"));

  // --- 1. serializer alive ---
  Serial.println(F("\n[1/6] serializer identity"));
  if (!checkIdentity()) { Serial.println(F("ABORT: no serializer.")); return; }

  // --- 2. strap ---
  Serial.println(F("\n[2/6] MODE_SEL strap"));
  uint8_t m = rd8(REG_MODE_STS);
  if (m != 0x10) {
    Serial.printf("ABORT: 0x13 = 0x%02X, want 0x10. Fix the strap (see 'm').\n", m);
    return;
  }
  Serial.println(F("  0x13 = 0x10  OK"));

  // --- 3. clock source ---
  // 0x14 resets to 0x00 = External Pixel Clock. With no DPI running there is no
  // clock, so no serial stream, so the 302 can never lock. 0x06 selects the
  // 25MHz internal oscillator -> 875 Mbps line rate, inside the 302's window.
  Serial.println(F("\n[3/6] link clock source"));
  Serial.printf("  0x14 was 0x%02X\n", rd8(0x14));
  if (!wrv(0x14, 0x06)) { Serial.println(F("ABORT: 0x14 write failed.")); return; }
  Serial.println(F("  0x14 = 0x06  (25MHz internal oscillator)"));
  delay(200);

  // --- 4. link ---
  Serial.println(F("\n[4/6] waiting for link..."));
  uint8_t s = 0, d = 0;
  for (uint8_t i = 0; i < 20; i++) {
    s = rd8(REG_GEN_STATUS); d = rd8(REG_DESID);
    if ((s & 1) && (d & 0xFE)) break;
    delay(100);
  }
  Serial.printf("  0x0C = 0x%02X  link=%u\n", s, s & 1);
  Serial.printf("  0x06 = 0x%02X  deserializer 0x%02X\n", d, d >> 1);
  if (!(s & 1) || !(d & 0xFE)) {
    Serial.println(F("ABORT: no link. Check cable, connector, cluster power."));
    return;
  }
  Serial.println(F("  link up, backchannel up"));

  // --- 5. I2C pass-through ---
  // 0x03[3] resets to 0. Without it, transactions to 0x2C are not forwarded.
  Serial.println(F("\n[5/6] I2C pass-through to the 302"));
  uint8_t c = rd8(REG_CONFIG);
  if (!wrv(REG_CONFIG, c | 0x08)) { Serial.println(F("ABORT: 0x03 write failed.")); return; }
  Serial.printf("  0x03 = 0x%02X  (pass-through on)\n", c | 0x08);
  uint8_t rid = desRd(0x00);
  if ((rid >> 1) != DES_ADDR) {
    Serial.printf("  302 not reachable (0x00 = 0x%02X). Trying Pass All...\n", rid);
    passAll(true);
    rid = desRd(0x00);
    if ((rid >> 1) != DES_ADDR) { Serial.println(F("ABORT: 302 unreachable.")); return; }
  }
  Serial.printf("  302 responds, 0x00 = 0x%02X  OK\n", rid);

  // --- 6. 302 outputs + serializer pattern ---
  Serial.println(F("\n[6/6] enabling video"));
  desWr(DES_PGCTL, 0x00);              // make sure the 302's own patgen is off
  desOutputsOn();                      // 0x02 = 0xF0, see Table 2
  wrv(REG_PGCTL, 0x00);
  wrv(REG_PGCFG, 0x04);                // 24-bit, internal clock, internal timing
  wrv(REG_PGCTL, (PAT_WHITE << 4) | 0x01);
  delay(300);

  uint8_t ds = desRd(DES_GEN_STATUS);
  Serial.println(F("\n---------------- result ----------------"));
  Serial.printf("  925 link      : %u\n", rd8(REG_GEN_STATUS) & 1);
  Serial.printf("  302 lock      : %u\n", ds & 1);
  Serial.printf("  302 outputs   : 0x%02X\n", desRd(DES_CONFIG0));
  Serial.printf("  925 patgen    : 0x%02X\n", rd8(REG_PGCTL));
  if ((ds & 1) && (desRd(DES_CONFIG0) & 0x80))
    Serial.println(F("\n  Chain is up. You should have WHITE on the MID.\n"
                     "  If not: backlight, or the 302's RGB goes through a mux."));
  else
    Serial.println(F("\n  Something is not asserted - check the lines above."));
  Serial.println(F("----------------------------------------"));
}

static void overrideStrap() {
  Serial.println(F("\n-- software strap override: 0x04 = 0x8A --"));
  Serial.println(F("   LFMODE -> 15-85MHz, Backward Compat -> off."));
  Serial.println(F("   Repeater is NOT overridable; that needs the resistor fix."));
  wrv(REG_CONFIG1, 0x8A);
  Serial.println(F("   LFMODE change needs a reset - issuing soft reset..."));
  wr(REG_RESET, 0x01);
  delay(50);
  checkMode();
  checkLink();
}

static void toggleTRFB() {
  uint8_t c = rd8(REG_CONFIG);
  uint8_t n = c ^ 0x01;
  Serial.printf("\nTRFB %u -> %u (%s edge)\n", c & 1, n & 1, (n & 1) ? "rising" : "falling");
  wrv(REG_CONFIG, n);
}

static void passAll(bool on) {
  uint8_t v = rd8(REG_I2C_PASS);
  v = on ? (v | 0x80) : (v & 0x7F);
  Serial.printf("\nI2C pass-through all = %u (0x17 = 0x%02X)\n", on, v);
  wrv(REG_I2C_PASS, v);
}

static void dump() {
  const uint8_t r[] = {0x00,0x01,0x03,0x04,0x05,0x06,0x07,0x08,0x0A,0x0C,0x0D,
                       0x12,0x13,0x14,0x16,0x17,0x18,0x19,0x1B,0x64,0x65};
  Serial.println(F("\n-- register dump --"));
  for (uint8_t i = 0; i < sizeof(r); i++) Serial.printf("  0x%02X = 0x%02X\n", r[i], rd8(r[i]));
}

static void watchPoll() {
  uint8_t s = rd8(REG_GEN_STATUS), d = rd8(REG_DESID);
  if (s != lastStatus || d != lastDesId) {
    Serial.printf("[%lu] 0x0C=%02X link=%u pclk=%u deserr=%u | DESID=%02X\n",
                  millis(), s, s & 1, (s >> 2) & 1, (s >> 1) & 1, d);
    lastStatus = s; lastDesId = d;
  }
}

// ---------------------------------------------------------------- CLI
static void help() {
  Serial.println(F(
    "\ncommands:\n"
    "  h            help\n"
    "  C            COLD START - full bring-up from power-on defaults\n"
    "  a            full check (read-only)\n"
    "  i            identity only\n"
    "  m            MODE_SEL strap check (0x13)\n"
    "  l            link + backchannel status\n"
    "  x            remote read of the 302 through the link\n"
    "  k            configuration registers\n"
    "  d            register dump\n"
    "  L            toggle link watch (polls, prints on change)\n"
    "  g            patgen white  (no Pi needed)\n"
    "  1..5         patgen white/black/red/green/blue\n"
    "  6            patgen vertical ramp\n"
    "  z            patgen off\n"
    "  t            toggle TRFB pixel-clock edge (0x03 bit 0)\n"
    "  v            software strap override (0x04 = 0x8A) + reset\n"
    "  P / p        I2C pass-through all on / off\n"
    "  --- 302, through the link (needs pass-through) ---\n"
    "  S            302 status\n"
    "  o / O        302 outputs on (0x02=0xF0) / off\n"
    "  y <reg>      read 302 register (hex)\n"
    "  Y <reg> <v>  write 302 register (hex)\n"
    "  R            soft reset (0x01 bit 0)\n"
    "  r <reg>      read register (hex)\n"
    "  w <reg> <v>  write register (hex)\n"
    "  I <ia>       read indirect (hex)\n"
    "  W <ia> <v>   write indirect (hex, patgen must be off)\n"));
}

static void handle(String s) {
  s.trim(); if (!s.length()) return;
  char c = s[0]; String a = s.substring(1); a.trim();
  switch (c) {
    case 'h': help(); break;
    case 'a': fullCheck(); break;
    case 'i': checkIdentity(); break;
    case 'm': checkMode(); break;
    case 'l': checkLink(); break;
    case 'x': checkRemote(); break;
    case 'k': config(); break;
    case 'd': dump(); break;
    case 'L': linkWatch = !linkWatch; lastStatus = 0xFF;
              Serial.printf("\nlink watch %s\n", linkWatch ? "ON" : "OFF"); break;
    case 'g': patgen(PAT_WHITE); break;
    case '1': patgen(PAT_WHITE); break;
    case '2': patgen(PAT_BLACK); break;
    case '3': patgen(PAT_RED);   break;
    case '4': patgen(PAT_GREEN); break;
    case '5': patgen(PAT_BLUE);  break;
    case '6': patgen(PAT_VRAMP); break;
    case 'z': patgenOff(); break;
    case 't': toggleTRFB(); break;
    case 'v': overrideStrap(); break;
    case 'P': passAll(true);  break;
    case 'p': passAll(false); break;
    case 'C': coldStart(); break;
    case 'S': desStatus(); break;
    case 'o': desOutputsOn();  break;
    case 'O': desOutputsOff(); break;
    case 'y': { long x = strtol(a.c_str(), 0, 16);
                Serial.printf("302 0x%02lX = 0x%02X\n", x, desRd((uint8_t)x)); break; }
    case 'Y': { int sp = a.indexOf(' '); if (sp < 0) { Serial.println(F("Y <reg> <val>")); break; }
                desWr((uint8_t)strtol(a.substring(0,sp).c_str(),0,16),
                      (uint8_t)strtol(a.substring(sp+1).c_str(),0,16)); break; }
    case 'R': Serial.println(F("\nsoft reset")); wr(REG_RESET, 0x01); delay(50); checkIdentity(); break;
    case 'r': { long x = strtol(a.c_str(), 0, 16);
                Serial.printf("0x%02lX = 0x%02X\n", x, rd8((uint8_t)x)); break; }
    case 'w': { int sp = a.indexOf(' '); if (sp < 0) { Serial.println(F("w <reg> <val>")); break; }
                wrv((uint8_t)strtol(a.substring(0,sp).c_str(),0,16),
                    (uint8_t)strtol(a.substring(sp+1).c_str(),0,16)); break; }
    case 'I': { long x = strtol(a.c_str(), 0, 16);
                Serial.printf("indirect 0x%02lX = 0x%02X\n", x, rdInd((uint8_t)x)); break; }
    case 'W': { int sp = a.indexOf(' '); if (sp < 0) { Serial.println(F("W <ia> <val>")); break; }
                wrInd((uint8_t)strtol(a.substring(0,sp).c_str(),0,16),
                      (uint8_t)strtol(a.substring(sp+1).c_str(),0,16)); break; }
    default: Serial.println(F("? try 'h'"));
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println(F("\n\nDS90UB925Q link verification tool"));
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(I2C_HZ);
  Wire.setClockStretchLimit(40000);
  delay(200);
  fullCheck();
  help();
}

void loop() {
  static String buf;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') { handle(buf); buf = ""; }
    else if (buf.length() < 40)   { buf += ch; }
  }
  static uint32_t t = 0;
  if (linkWatch && millis() - t > 250) { t = millis(); watchPoll(); }
}
