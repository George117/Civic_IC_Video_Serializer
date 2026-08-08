/*
 * ub925_sweep.ino - timing sweep for the Civic Gen 10 MID compositor
 *
 * The DS90UB302Q's parallel output feeds a graphics IC with external DRAM,
 * not the panel directly. That IC composites and may only accept video it
 * recognises. This sketch brings the FPD-Link chain up from cold and then
 * walks a table of plausible input timings, so you can watch the cluster and
 * see whether any of them makes the "loading" screen resolve.
 *
 * Wiring (ESP8266 / NodeMCU) -> serializer board I2C1 header:
 *   D1 (GPIO5) -> SCL,  D2 (GPIO4) -> SDA,  GND -> GND
 * Leave the 302-side ESP UNPLUGGED. The 302 is reached through the link.
 *
 * Press 'C' for cold start, then 'w' to begin the sweep.
 *
 * CLOCK CAVEAT - read this before trusting the Hz figures below.
 * Register 0x14 selects the serializer's clock in the absence of an external
 * PCLK: 25MHz or 33MHz. The pattern generator additionally has a divider
 * (PGCDC, indirect 0x03) whose source AN-2198 documents as a 200MHz internal
 * oscillator on the 92x parts - the 302/925 pairing is not in that table.
 * The refresh figures here assume pixel clock == the 0x14 oscillator.
 * VERIFY by scoping PCLK on 302 pin 5 and using 'k' to record what you measure.
 */

#include <Wire.h>

#define SDA_PIN        4
#define SCL_PIN        5
#define I2C_HZ         100000
#define SER_ADDR       0x0C
#define DES_ADDR       0x2C

// ---- 925 direct ----
#define REG_DEVICE_ID  0x00
#define REG_RESET      0x01
#define REG_CONFIG     0x03
#define REG_DESID      0x06
#define REG_GEN_STATUS 0x0C
#define REG_REV_ID     0x0D
#define REG_MODE_STS   0x13
#define REG_OSC_SRC    0x14
#define REG_I2C_PASS   0x17
#define REG_PGCTL      0x64
#define REG_PGCFG      0x65
#define REG_PGIA       0x66
#define REG_PGID       0x67

// ---- 302, through the link ----
#define DES_CONFIG0    0x02
#define DES_GEN_STATUS 0x1C
#define DES_PGCTL      0x64

// ---- AN-2198 indirect ----
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

// 0x14 oscillator selection
#define OSC_EXT        0x00   // external pixel clock
#define OSC_33M        0x02   // bits 2:1 = 01
#define OSC_25M        0x06   // bits 2:1 = 11

struct Timing {
  const char *name;
  uint16_t hTotal, vTotal, hActive, vActive;
  uint8_t  hsw, vsw, hbp, vbp;
  uint8_t  osc;          // OSC_25M or OSC_33M
  uint8_t  syncNeg;      // 1 = negative HS/VS polarity
};

// Plausible automotive cluster input timings that land inside the 302's
// 15-45MHz PCLK window with one of the two available oscillators.
static const Timing TIMINGS[] PROGMEM = {
  // name                    hT    vT   hA   vA  hsw vsw hbp vbp  osc      neg
  {"800x480 minimal (dflt)",  840,  485, 800, 480, 10,  2, 10,  2, OSC_25M, 1},
  {"800x480 WVGA std",       1056,  525, 800, 480,128,  4, 88, 33, OSC_33M, 1},
  {"800x480 mid blanking",    900,  500, 800, 480, 48,  3, 40, 13, OSC_25M, 1},
  {"800x480 pos sync",       1056,  525, 800, 480,128,  4, 88, 33, OSC_33M, 0},
  {"640x480 VGA",             800,  525, 640, 480, 96,  2, 48, 33, OSC_25M, 1},
  {"720x480",                 858,  525, 720, 480, 62,  6, 60, 30, OSC_25M, 1},
  {"480x272 wide blank",      800,  520, 480, 272, 41, 10,  2,  2, OSC_25M, 1},
  {"400x240 wide blank",      800,  520, 400, 240, 48,  3, 40, 13, OSC_25M, 1},
  {"800x600 SVGA",           1056,  628, 800, 600,128,  4, 88, 23, OSC_33M, 1},
  {"1024x600",               1344,  635,1024, 600,136,  6,160, 29, OSC_33M, 1},
  {"1280x480",               1500,  520,1280, 480, 80,  4, 96, 20, OSC_33M, 1},
};
static const uint8_t N_TIMINGS = sizeof(TIMINGS) / sizeof(TIMINGS[0]);

static uint8_t  curIdx     = 0;
static uint8_t  curPattern = 0x1;      // white
static bool     sweeping   = false;
static uint32_t dwellMs    = 6000;
static uint32_t lastStep   = 0;
static uint8_t  divN       = 8;

// ---------------------------------------------------------------- I2C
static bool wrTo(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr); Wire.write(reg); Wire.write(val);
  uint8_t e = Wire.endTransmission();
  if (e) { Serial.printf("  ! wr %02X:%02X failed (err %u)\n", addr, reg, e); return false; }
  return true;
}
static bool rdTo(uint8_t addr, uint8_t reg, uint8_t *v) {
  Wire.beginTransmission(addr); Wire.write(reg);
  if (Wire.endTransmission(false)) return false;
  if (Wire.requestFrom(addr, (uint8_t)1) != 1) return false;
  *v = Wire.read(); return true;
}
static bool wr(uint8_t r, uint8_t v) { return wrTo(SER_ADDR, r, v); }
static uint8_t rd8(uint8_t r) { uint8_t v = 0xFF; rdTo(SER_ADDR, r, &v); return v; }
static bool wrv(uint8_t r, uint8_t v) {
  if (!wr(r, v)) return false;
  uint8_t b = rd8(r);
  if (b != v) { Serial.printf("  ! 0x%02X readback %02X != %02X\n", r, b, v); return false; }
  return true;
}
static bool wrInd(uint8_t ia, uint8_t v) { return wr(REG_PGIA, ia) && wr(REG_PGID, v); }
static uint8_t rdInd(uint8_t ia) { wr(REG_PGIA, ia); return rd8(REG_PGID); }
static uint8_t desRd(uint8_t r) { uint8_t v = 0xFF; rdTo(DES_ADDR, r, &v); return v; }
static bool desWr(uint8_t r, uint8_t v) { return wrTo(DES_ADDR, r, v); }

// ---------------------------------------------------------------- apply
static void applyTiming(uint8_t idx) {
  Timing t;
  memcpy_P(&t, &TIMINGS[idx], sizeof(Timing));

  uint32_t px = (t.osc == OSC_33M) ? 33000000UL : 25000000UL;
  uint32_t pix = (uint32_t)t.hTotal * t.vTotal;
  uint32_t hz  = pix ? (px / pix) : 0;

  Serial.printf("\n=== [%u/%u] %s ===\n", idx + 1, N_TIMINGS, t.name);
  Serial.printf("  total %ux%u  active %ux%u  hsw=%u vsw=%u hbp=%u vbp=%u\n",
                t.hTotal, t.vTotal, t.hActive, t.vActive, t.hsw, t.vsw, t.hbp, t.vbp);
  Serial.printf("  osc %s  sync %s  -> ~%lu Hz (assumed)\n",
                (t.osc == OSC_33M) ? "33MHz" : "25MHz",
                t.syncNeg ? "negative" : "positive", hz);

  wrv(REG_PGCTL, 0x00);                       // indirect needs patgen off
  if (rd8(REG_OSC_SRC) != t.osc) {
    wrv(REG_OSC_SRC, t.osc);
    delay(150);
  }

  wrInd(PG_PGCDC,  divN & 0x3F);
  wrInd(PG_PGTFS1, t.hTotal & 0xFF);
  wrInd(PG_PGTFS2, (uint8_t)(((t.vTotal & 0x0F) << 4) | ((t.hTotal >> 8) & 0x0F)));
  wrInd(PG_PGTFS3, (uint8_t)((t.vTotal >> 4) & 0xFF));
  wrInd(PG_PGAFS1, t.hActive & 0xFF);
  wrInd(PG_PGAFS2, (uint8_t)(((t.vActive & 0x0F) << 4) | ((t.hActive >> 8) & 0x0F)));
  wrInd(PG_PGAFS3, (uint8_t)((t.vActive >> 4) & 0xFF));
  wrInd(PG_PGHSW,  t.hsw);
  wrInd(PG_PGVSW,  t.vsw);
  wrInd(PG_PGHBP,  t.hbp);
  wrInd(PG_PGVBP,  t.vbp);
  wrInd(PG_PGSC,   t.syncNeg ? 0x03 : 0x00);

  wrv(REG_PGCFG, 0x04);                       // 24-bit, internal clock+timing
  wrv(REG_PGCTL, (uint8_t)((curPattern << 4) | 0x01));
  delay(250);

  uint8_t s = rd8(REG_GEN_STATUS), d = desRd(DES_GEN_STATUS);
  Serial.printf("  925 link=%u   302 lock=%u sigdet=%u   %s\n",
                s & 1, d & 1, (d >> 1) & 1,
                ((s & 1) && (d & 1)) ? "OK" : "<-- LINK/LOCK LOST");
  curIdx = idx;
}

static void listTimings() {
  Serial.println(F("\n-- timing table --"));
  for (uint8_t i = 0; i < N_TIMINGS; i++) {
    Timing t; memcpy_P(&t, &TIMINGS[i], sizeof(Timing));
    uint32_t px = (t.osc == OSC_33M) ? 33000000UL : 25000000UL;
    Serial.printf("  %2u %c %-24s %4ux%-4u tot %4ux%-4u %s ~%luHz\n",
                  i + 1, (i == curIdx) ? '*' : ' ', t.name,
                  t.hActive, t.vActive, t.hTotal, t.vTotal,
                  (t.osc == OSC_33M) ? "33M" : "25M",
                  px / ((uint32_t)t.hTotal * t.vTotal));
  }
}

// ---------------------------------------------------------------- cold start
static bool coldStart() {
  Serial.println(F("\n######## COLD START ########"));

  Wire.beginTransmission(SER_ADDR);
  if (Wire.endTransmission()) { Serial.println(F("ABORT: no ACK at 0x0C")); return false; }
  Serial.printf("[1] 0x00=0x%02X  0x0D=0x%02X\n", rd8(REG_DEVICE_ID), rd8(REG_REV_ID));

  uint8_t m = rd8(REG_MODE_STS);
  if (m != 0x10) { Serial.printf("ABORT: 0x13=0x%02X want 0x10 (strap)\n", m); return false; }
  Serial.println(F("[2] strap 0x10 OK"));

  if (!wrv(REG_OSC_SRC, OSC_25M)) { Serial.println(F("ABORT: 0x14 write")); return false; }
  Serial.println(F("[3] 0x14=0x06 (25MHz osc)"));

  uint8_t s = 0, d = 0;
  for (uint8_t i = 0; i < 20; i++) {
    s = rd8(REG_GEN_STATUS); d = rd8(REG_DESID);
    if ((s & 1) && (d & 0xFE)) break;
    delay(100);
  }
  if (!(s & 1) || !(d & 0xFE)) {
    Serial.printf("ABORT: no link. 0x0C=0x%02X 0x06=0x%02X\n", s, d);
    return false;
  }
  Serial.printf("[4] link up, DESID=0x%02X\n", d);

  uint8_t c = rd8(REG_CONFIG);
  wrv(REG_CONFIG, c | 0x08);
  if ((desRd(0x00) >> 1) != DES_ADDR) {
    wrv(REG_I2C_PASS, rd8(REG_I2C_PASS) | 0x80);
    if ((desRd(0x00) >> 1) != DES_ADDR) { Serial.println(F("ABORT: 302 unreachable")); return false; }
  }
  Serial.println(F("[5] pass-through OK"));

  desWr(DES_PGCTL, 0x00);
  desWr(DES_CONFIG0, 0xF0);
  Serial.printf("[6] 302 outputs 0x%02X, lock=%u\n",
                desRd(DES_CONFIG0), desRd(DES_GEN_STATUS) & 1);

  Serial.println(F("############################"));
  applyTiming(curIdx);
  return true;
}

// ---------------------------------------------------------------- misc
static void status() {
  uint8_t s = rd8(REG_GEN_STATUS), d = desRd(DES_GEN_STATUS);
  Serial.printf("\n925: 0x0C=%02X link=%u pclk=%u | 0x14=%02X 0x64=%02X 0x65=%02X\n",
                s, s & 1, (s >> 2) & 1, rd8(REG_OSC_SRC), rd8(REG_PGCTL), rd8(REG_PGCFG));
  Serial.printf("302: 0x1C=%02X lock=%u sigdet=%u | 0x02=%02X\n",
                d, d & 1, (d >> 1) & 1, desRd(DES_CONFIG0));
  Serial.printf("timing entry %u/%u, divN=%u, pattern=%u\n",
                curIdx + 1, N_TIMINGS, divN, curPattern);
}

static void help() {
  Serial.println(F(
    "\ncommands:\n"
    "  C            cold start (link + pass-through + 302 outputs + apply timing)\n"
    "  l            list timing table\n"
    "  n / b        next / previous timing\n"
    "  j <n>        jump to entry n\n"
    "  w            start/stop auto sweep\n"
    "  T <ms>       set sweep dwell time (default 6000)\n"
    "  1..6         pattern white/black/red/green/blue/vramp\n"
    "  D <n>        set PGCDC divider (2..63), then re-apply\n"
    "  o <25|33>    force oscillator, then re-apply\n"
    "  s            status\n"
    "  k            note: scope 302 pin 5 to measure real PCLK\n"
    "  r <reg>      read 925 reg | y <reg> read 302 reg\n"
    "  W <reg> <v>  write 925 reg | Y <reg> <v> write 302 reg\n"
    "  z            patgen off\n"));
}

static void handle(String in) {
  in.trim(); if (!in.length()) return;
  char c = in[0]; String a = in.substring(1); a.trim();
  switch (c) {
    case 'h': help(); break;
    case 'C': coldStart(); break;
    case 'l': listTimings(); break;
    case 'n': applyTiming((curIdx + 1) % N_TIMINGS); break;
    case 'b': applyTiming((curIdx + N_TIMINGS - 1) % N_TIMINGS); break;
    case 'j': { int n = a.toInt(); if (n >= 1 && n <= N_TIMINGS) applyTiming(n - 1);
                else Serial.printf("range 1..%u\n", N_TIMINGS); break; }
    case 'w': sweeping = !sweeping; lastStep = millis();
              Serial.printf("\nsweep %s (dwell %lums)\n", sweeping ? "ON" : "OFF", dwellMs); break;
    case 'T': { long v = a.toInt(); if (v >= 500) { dwellMs = v; Serial.printf("dwell %lums\n", dwellMs); } break; }
    case '1': case '2': case '3': case '4': case '5':
              curPattern = c - '0'; applyTiming(curIdx); break;
    case '6': curPattern = 0xA; applyTiming(curIdx); break;
    case 'D': { int v = a.toInt(); if (v >= 2 && v <= 63) { divN = v; applyTiming(curIdx); }
                else Serial.println(F("divN 2..63")); break; }
    case 'o': { int v = a.toInt();
                wrv(REG_OSC_SRC, (v == 33) ? OSC_33M : OSC_25M);
                Serial.printf("osc -> %dMHz\n", (v == 33) ? 33 : 25);
                delay(200); applyTiming(curIdx); break; }
    case 's': status(); break;
    case 'k': Serial.println(F("\nScope PCLK on DS90UB302Q pin 5 with the pattern running.\n"
                              "measured PCLK x (hTotal*vTotal) = actual refresh.\n"
                              "If it does not match the assumed figure, PGCDC is in the path\n"
                              "and you can scale it with 'D'.")); break;
    case 'z': wrv(REG_PGCTL, 0x00); Serial.println(F("patgen off")); break;
    case 'r': { long x = strtol(a.c_str(), 0, 16);
                Serial.printf("925 0x%02lX = 0x%02X\n", x, rd8((uint8_t)x)); break; }
    case 'y': { long x = strtol(a.c_str(), 0, 16);
                Serial.printf("302 0x%02lX = 0x%02X\n", x, desRd((uint8_t)x)); break; }
    case 'W': { int sp = a.indexOf(' '); if (sp < 0) break;
                wrv((uint8_t)strtol(a.substring(0,sp).c_str(),0,16),
                    (uint8_t)strtol(a.substring(sp+1).c_str(),0,16)); break; }
    case 'Y': { int sp = a.indexOf(' '); if (sp < 0) break;
                desWr((uint8_t)strtol(a.substring(0,sp).c_str(),0,16),
                      (uint8_t)strtol(a.substring(sp+1).c_str(),0,16)); break; }
    default: Serial.println(F("? try 'h'"));
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println(F("\n\nDS90UB925Q timing sweep"));
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(I2C_HZ);
  Wire.setClockStretchLimit(40000);
  delay(200);
  if (coldStart()) { listTimings(); Serial.println(F("\n'w' to sweep, 'n' to step, 'h' for help.")); }
  else help();
}

void loop() {
  static String buf;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') { handle(buf); buf = ""; }
    else if (buf.length() < 40)   { buf += ch; }
  }
  if (sweeping && millis() - lastStep > dwellMs) {
    lastStep = millis();
    applyTiming((curIdx + 1) % N_TIMINGS);
  }
}
