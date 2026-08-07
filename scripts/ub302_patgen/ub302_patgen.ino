/*
 * ub302_patgen.ino - DS90UB302Q internal test pattern generator
 *
 * Direct local I2C to the deserializer inside the cluster.
 * No serializer, no FPD-Link, no PCLK required.
 *
 * Wiring (ESP8266 / NodeMCU):
 *   D1 (GPIO5) -> SCL on the 302
 *   D2 (GPIO4) -> SDA on the 302
 *   GND        -> cluster GND        <-- must share ground
 *   Do NOT add pull-ups; the cluster board already has them.
 *
 * Register data from:
 *   DS90UB302Q datasheet (SNLS410)
 *   AN-2198 / SNLA132G  (pattern generator direct + indirect map)
 *
 * Type 'h' in the serial monitor (115200) for commands.
 */

#include <Wire.h>

#define SDA_PIN         4      // D2
#define SCL_PIN         5      // D1
#define I2C_HZ          100000

// IDx strapped to 0 -> 7-bit address 0x2C (datasheet Table 7, entry 1)
#define DES_ADDR        0x2C

// ---- direct registers (DS90UB302Q) ----
#define REG_DEVICE_ID   0x00   // [7:1] = 7-bit address, expect 0x58
#define REG_RESET       0x01   // [1] full reset, [0] reset except regs, [2] BC enable
#define REG_CONFIG0     0x02   // [7] output enable, [6] OEN override, [5] OSC clk, [4] OSS_SEL
#define REG_GEN_STATUS  0x1C   // [1] signal detect, [0] lock
#define REG_GPIO0_CFG   0x1D   // [7:4] rev ID, expect 0xA
#define REG_LINK_ERR    0x41
#define REG_EQ          0x44
#define REG_PGCTL       0x64   // [7:4] pattern, [0] enable
#define REG_PGCFG       0x65   // [4] 18-bit, [3] ext clk, [2] timing sel, [1] invert, [0] scroll
#define REG_PGIA        0x66   // indirect address
#define REG_PGID        0x67   // indirect data

// ---- indirect registers (AN-2198 Table 3-4) ----
#define PG_PGRS         0x00   // custom colour red
#define PG_PGGS         0x01   // custom colour green
#define PG_PGBS         0x02   // custom colour blue
#define PG_PGCDC        0x03   // clock divider N (2..63)
#define PG_PGTFS1       0x04   // total H width [7:0]
#define PG_PGTFS2       0x05   // [7:4] total V [3:0], [3:0] total H [11:8]
#define PG_PGTFS3       0x06   // total V [11:4]
#define PG_PGAFS1       0x07   // active H width [7:0]
#define PG_PGAFS2       0x08   // [7:4] active V [3:0], [3:0] active H [11:8]
#define PG_PGAFS3       0x09   // active V [11:4]
#define PG_PGHSW        0x0A   // H sync width, pixels
#define PG_PGVSW        0x0B   // V sync width, lines
#define PG_PGHBP        0x0C   // H back porch, pixels
#define PG_PGVBP        0x0D   // V back porch, lines
#define PG_PGSC         0x0E   // [3] VS dis [2] HS dis [1] VS pol [0] HS pol

// PGCTL[7:4] pattern codes
#define PAT_WHITE       0x1
#define PAT_BLACK       0x2
#define PAT_RED         0x3
#define PAT_GREEN       0x4
#define PAT_BLUE        0x5
#define PAT_HRAMP_W     0x6
#define PAT_VRAMP_W     0xA
#define PAT_CUSTOM      0xE

static uint8_t lastPattern = PAT_WHITE;
static bool    watchdogOn  = false;
static uint8_t wdPGCTL = 0, wdPGCFG = 0, wdCONFIG0 = 0;

// ---------------------------------------------------------------- I2C
static bool wr(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(DES_ADDR);
  Wire.write(reg);
  Wire.write(val);
  uint8_t e = Wire.endTransmission();
  if (e) { Serial.printf("  ! write 0x%02X = 0x%02X failed (err %u)\n", reg, val, e); return false; }
  return true;
}

static bool rd(uint8_t reg, uint8_t *val) {
  Wire.beginTransmission(DES_ADDR);
  Wire.write(reg);
  uint8_t e = Wire.endTransmission(false);      // repeated start
  if (e) { Serial.printf("  ! read 0x%02X addr phase failed (err %u)\n", reg, e); return false; }
  if (Wire.requestFrom((uint8_t)DES_ADDR, (uint8_t)1) != 1) {
    Serial.printf("  ! read 0x%02X no data\n", reg); return false;
  }
  *val = Wire.read();
  return true;
}

static uint8_t rd8(uint8_t reg) { uint8_t v = 0xFF; rd(reg, &v); return v; }

// verified write: write, read back, complain on mismatch
static bool wrv(uint8_t reg, uint8_t val) {
  if (!wr(reg, val)) return false;
  uint8_t rb;
  if (!rd(reg, &rb)) return false;
  if (rb != val) {
    Serial.printf("  ! 0x%02X readback 0x%02X, wrote 0x%02X\n", reg, rb, val);
    return false;
  }
  return true;
}

static bool wrIndirect(uint8_t iaddr, uint8_t val) {
  return wr(REG_PGIA, iaddr) && wr(REG_PGID, val);
}

static uint8_t rdIndirect(uint8_t iaddr) {
  wr(REG_PGIA, iaddr);
  return rd8(REG_PGID);
}

// ---------------------------------------------------------------- checks
static void probe() {
  Serial.println(F("\n-- probe --"));
  Wire.beginTransmission(DES_ADDR);
  uint8_t e = Wire.endTransmission();
  if (e) {
    Serial.printf("No ACK at 0x%02X (err %u). Check SDA/SCL/GND.\n", DES_ADDR, e);
    Serial.println(F("Scanning 0x08..0x77 ..."));
    for (uint8_t a = 0x08; a < 0x78; a++) {
      Wire.beginTransmission(a);
      if (Wire.endTransmission() == 0) Serial.printf("  found 0x%02X\n", a);
    }
    return;
  }
  Serial.printf("ACK at 0x%02X\n", DES_ADDR);

  uint8_t id = rd8(REG_DEVICE_ID);
  Serial.printf("0x00 DEVICE_ID = 0x%02X  (expect 0x58 -> 7-bit 0x%02X) %s\n",
                id, id >> 1, (id == 0x58) ? "OK" : "<-- unexpected");

  uint8_t rev = rd8(REG_GPIO0_CFG);
  Serial.printf("0x1D REV_ID    = 0x%02X  (bits 7:4 expect 0xA) %s\n",
                rev, ((rev >> 4) == 0x0A) ? "OK" : "<-- unexpected");
}

static void status() {
  uint8_t s  = rd8(REG_GEN_STATUS);
  uint8_t c0 = rd8(REG_CONFIG0);
  uint8_t pc = rd8(REG_PGCTL);
  uint8_t pf = rd8(REG_PGCFG);

  Serial.println(F("\n-- status --"));
  Serial.printf("0x1C GEN_STATUS = 0x%02X   lock=%u  signal_detect=%u  i2s_lock=%u\n",
                s, s & 1, (s >> 1) & 1, (s >> 3) & 1);
  Serial.printf("0x02 CONFIG0    = 0x%02X   out_en=%u  oen_override=%u  osc_clk=%u  oss_sel=%u\n",
                c0, (c0 >> 7) & 1, (c0 >> 6) & 1, (c0 >> 5) & 1, (c0 >> 4) & 1);
  Serial.printf("0x64 PGCTL      = 0x%02X   pattern=%u  enabled=%u\n",
                pc, pc >> 4, pc & 1);
  Serial.printf("0x65 PGCFG      = 0x%02X   18bit=%u  extclk=%u  int_timing=%u  invert=%u  scroll=%u\n",
                pf, (pf >> 4) & 1, (pf >> 3) & 1, (pf >> 2) & 1, (pf >> 1) & 1, pf & 1);

  Serial.println(F("-- internal timing (indirect) --"));
  uint8_t cdc = rdIndirect(PG_PGCDC);
  uint8_t t1 = rdIndirect(PG_PGTFS1), t2 = rdIndirect(PG_PGTFS2), t3 = rdIndirect(PG_PGTFS3);
  uint8_t a1 = rdIndirect(PG_PGAFS1), a2 = rdIndirect(PG_PGAFS2), a3 = rdIndirect(PG_PGAFS3);
  uint16_t th = ((uint16_t)(t2 & 0x0F) << 8) | t1;
  uint16_t tv = ((uint16_t)t3 << 4) | (t2 >> 4);
  uint16_t ah = ((uint16_t)(a2 & 0x0F) << 8) | a1;
  uint16_t av = ((uint16_t)a3 << 4) | (a2 >> 4);
  Serial.printf("  divider N = %u\n", cdc & 0x3F);
  Serial.printf("  total  %u x %u\n", th, tv);
  Serial.printf("  active %u x %u\n", ah, av);
  Serial.printf("  hsw=%u vsw=%u hbp=%u vbp=%u sync_cfg=0x%02X\n",
                rdIndirect(PG_PGHSW), rdIndirect(PG_PGVSW),
                rdIndirect(PG_PGHBP), rdIndirect(PG_PGVBP), rdIndirect(PG_PGSC));
}

static void dumpAll() {
  Serial.println(F("\n-- direct register dump --"));
  const uint8_t regs[] = {0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,
                          0x1C,0x1D,0x1E,0x1F,0x24,0x25,0x2A,0x2B,0x2C,
                          0x41,0x44,0x56,0x64,0x65};
  for (uint8_t i = 0; i < sizeof(regs); i++)
    Serial.printf("  0x%02X = 0x%02X\n", regs[i], rd8(regs[i]));
}

// ---------------------------------------------------------------- outputs
// Default CONFIG0 is 0x00: outputs TRI-STATED and controlled by the OEN pin.
// 0xE0 = output enable + override the OEN pin + put the internal OSC on PCLK
// when the link is not locked (which is our case: no serializer attached).
static void outputsOn() {
  Serial.println(F("\n-- forcing LVCMOS outputs on (0x02 = 0xE0) --"));
  wrv(REG_CONFIG0, 0xE0);
}

static void outputsOff() {
  Serial.println(F("\n-- releasing outputs to OEN pin (0x02 = 0x00) --"));
  wrv(REG_CONFIG0, 0x00);
}

// ---------------------------------------------------------------- patgen
static void patgenOff() {
  wrv(REG_PGCTL, 0x00);
}

// Uses the built-in internal timing defaults: 800x480 @ ~61.4 Hz, divider 8.
static void patgenDefault(uint8_t pattern) {
  Serial.printf("\n-- patgen: internal timing defaults, pattern %u --\n", pattern);
  patgenOff();                                   // indirect regs need patgen disabled
  wrv(REG_PGCFG, 0x04);                          // 24-bit, internal clock, internal timing
  wrv(REG_PGCTL, (uint8_t)((pattern << 4) | 0x01));
  lastPattern = pattern;
  status();
}

// External timing: uses PCLK/DE/HS/VS arriving over the link. Only useful
// once a serializer is actually connected and locked.
static void patgenExternalTiming(uint8_t pattern) {
  Serial.printf("\n-- patgen: EXTERNAL timing, pattern %u --\n", pattern);
  patgenOff();
  wrv(REG_PGCFG, 0x00);
  wrv(REG_PGCTL, (uint8_t)((pattern << 4) | 0x01));
  lastPattern = pattern;
}

/*
 * Custom internal timing. Bit packing verified against the worked example
 * in AN-2198 section 4.3 (1176x525 total, 800x480 active -> 0x98/0xD4/0x20,
 * 0x20/0x03/0x1E).
 *
 * divN: internal oscillator / divN = pixel clock.
 * Note AN-2198 documents a 200 MHz internal oscillator for the 92x/94x parts;
 * the 302 is not in that table, so treat divN as empirical.
 */
static void patgenCustom(uint16_t hTotal, uint16_t vTotal,
                         uint16_t hActive, uint16_t vActive,
                         uint8_t hsw, uint8_t vsw,
                         uint8_t hbp, uint8_t vbp,
                         uint8_t divN, bool negSync, uint8_t pattern) {
  Serial.println(F("\n-- patgen: custom internal timing --"));
  Serial.printf("   total %ux%u  active %ux%u  hsw=%u vsw=%u hbp=%u vbp=%u N=%u\n",
                hTotal, vTotal, hActive, vActive, hsw, vsw, hbp, vbp, divN);

  patgenOff();                                   // required before touching indirect

  wrIndirect(PG_PGCDC,  divN & 0x3F);
  wrIndirect(PG_PGTFS1, hTotal & 0xFF);
  wrIndirect(PG_PGTFS2, (uint8_t)(((vTotal & 0x0F) << 4) | ((hTotal >> 8) & 0x0F)));
  wrIndirect(PG_PGTFS3, (uint8_t)((vTotal >> 4) & 0xFF));
  wrIndirect(PG_PGAFS1, hActive & 0xFF);
  wrIndirect(PG_PGAFS2, (uint8_t)(((vActive & 0x0F) << 4) | ((hActive >> 8) & 0x0F)));
  wrIndirect(PG_PGAFS3, (uint8_t)((vActive >> 4) & 0xFF));
  wrIndirect(PG_PGHSW,  hsw);
  wrIndirect(PG_PGVSW,  vsw);
  wrIndirect(PG_PGHBP,  hbp);
  wrIndirect(PG_PGVBP,  vbp);
  wrIndirect(PG_PGSC,   negSync ? 0x03 : 0x00);  // bits [1:0] invert VS/HS

  wrv(REG_PGCFG, 0x04);
  wrv(REG_PGCTL, (uint8_t)((pattern << 4) | 0x01));
  lastPattern = pattern;
  status();
}

// ---------------------------------------------------------------- watchdog
// Detects another I2C master (cluster MCU / head unit over the back channel)
// resetting the part behind our back.
static void watchdogSnapshot() {
  wdPGCTL = rd8(REG_PGCTL);
  wdPGCFG = rd8(REG_PGCFG);
  wdCONFIG0 = rd8(REG_CONFIG0);
}

static void watchdogPoll() {
  uint8_t a = rd8(REG_PGCTL), b = rd8(REG_PGCFG), c = rd8(REG_CONFIG0);
  if (a != wdPGCTL || b != wdPGCFG || c != wdCONFIG0) {
    Serial.printf("[wd] registers changed: PGCTL %02X->%02X  PGCFG %02X->%02X  CFG0 %02X->%02X\n",
                  wdPGCTL, a, wdPGCFG, b, wdCONFIG0, c);
    Serial.println(F("[wd] something else is writing to this device."));
    wdPGCTL = a; wdPGCFG = b; wdCONFIG0 = c;
  }
}

// ---------------------------------------------------------------- CLI
static void help() {
  Serial.println(F(
    "\ncommands:\n"
    "  h            this help\n"
    "  p            probe / verify identity\n"
    "  s            status (lock, outputs, patgen, timing)\n"
    "  d            dump direct registers\n"
    "  o            outputs ON  (0x02 = 0xE0)\n"
    "  O            outputs OFF (0x02 = 0x00, back to OEN pin)\n"
    "  g            GO: outputs on + patgen white, internal defaults\n"
    "  1..5         pattern white/black/red/green/blue (internal timing)\n"
    "  e            patgen with EXTERNAL timing (needs a locked link)\n"
    "  c            custom timing example: 800x480, total 1056x525, N=8\n"
    "  z            patgen off\n"
    "  R            soft reset (0x01 bit 0, keeps registers)\n"
    "  W            toggle change-watchdog\n"
    "  r <reg>      read direct register, hex\n"
    "  w <reg> <v>  write direct register, hex\n"
    "  I <ia>       read indirect register, hex\n"
    "  i <ia> <v>   write indirect register, hex\n"));
}

static void handleLine(String s) {
  s.trim();
  if (!s.length()) return;
  char c = s[0];
  String rest = s.substring(1); rest.trim();

  switch (c) {
    case 'h': help(); break;
    case 'p': probe(); break;
    case 's': status(); break;
    case 'd': dumpAll(); break;
    case 'o': outputsOn(); break;
    case 'O': outputsOff(); break;
    case 'z': Serial.println(F("\npatgen off")); patgenOff(); break;
    case 'e': patgenExternalTiming(PAT_WHITE); break;
    case 'g': probe(); outputsOn(); patgenDefault(PAT_WHITE); watchdogSnapshot(); break;
    case '1': patgenDefault(PAT_WHITE); break;
    case '2': patgenDefault(PAT_BLACK); break;
    case '3': patgenDefault(PAT_RED);   break;
    case '4': patgenDefault(PAT_GREEN); break;
    case '5': patgenDefault(PAT_BLUE);  break;
    case 'c': patgenCustom(1056, 525, 800, 480, 10, 2, 40, 20, 8, true, PAT_WHITE); break;
    case 'R':
      Serial.println(F("\nsoft reset (0x01 bit 0)"));
      wr(REG_RESET, 0x05);            // keep BC enable bit 2, pulse reset bit 0
      delay(50);
      probe();
      break;
    case 'W':
      watchdogOn = !watchdogOn;
      if (watchdogOn) watchdogSnapshot();
      Serial.printf("\nwatchdog %s\n", watchdogOn ? "ON" : "OFF");
      break;
    case 'r': { long a = strtol(rest.c_str(), 0, 16);
                Serial.printf("0x%02lX = 0x%02X\n", a, rd8((uint8_t)a)); break; }
    case 'w': { int sp = rest.indexOf(' ');
                if (sp < 0) { Serial.println(F("usage: w <reg> <val>")); break; }
                long a = strtol(rest.substring(0, sp).c_str(), 0, 16);
                long v = strtol(rest.substring(sp + 1).c_str(), 0, 16);
                Serial.printf("write 0x%02lX = 0x%02lX\n", a, v);
                wrv((uint8_t)a, (uint8_t)v); break; }
    case 'I': { long a = strtol(rest.c_str(), 0, 16);
                Serial.printf("indirect 0x%02lX = 0x%02X\n", a, rdIndirect((uint8_t)a)); break; }
    case 'i': { int sp = rest.indexOf(' ');
                if (sp < 0) { Serial.println(F("usage: i <iaddr> <val>")); break; }
                long a = strtol(rest.substring(0, sp).c_str(), 0, 16);
                long v = strtol(rest.substring(sp + 1).c_str(), 0, 16);
                Serial.printf("indirect write 0x%02lX = 0x%02lX (patgen must be off)\n", a, v);
                wrIndirect((uint8_t)a, (uint8_t)v); break; }
    default: Serial.println(F("? try 'h'"));
  }
}

// ---------------------------------------------------------------- main
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println(F("\n\nDS90UB302Q pattern generator tool"));

  Wire.begin(SDA_PIN, SCL_PIN);       // NOT Wire.begin(100000) - that is slave mode
  Wire.setClock(I2C_HZ);
  Wire.setClockStretchLimit(40000);   // the 302 can stretch during BCC activity

  delay(200);
  probe();
  help();
  Serial.println(F("\nPress 'g' to bring up a white test pattern."));
}

void loop() {
  static String buf;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') { handleLine(buf); buf = ""; }
    else if (buf.length() < 40)   { buf += ch; }
  }

  static uint32_t t = 0;
  if (watchdogOn && millis() - t > 1000) { t = millis(); watchdogPoll(); }
}
