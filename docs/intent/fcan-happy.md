# Intent: a fully happy CAN environment

**Confirmed:** 2026-08-15
**Status:** milestone essentially reached — cluster clean except two lamps
(airbag information, autohold flashing). See PROJECT_STATUS.md for the detail.

Captured before any code was written, via a one-question-at-a-time interview.
This records what was actually wanted, so the next session does not re-derive it
or quietly drift from it.

---

## The confirmed statement

- **Outcome:** F-CAN drives the cluster with correct checksums and zero warning
  lamps, driven from the desktop via MCP servers — two CANables (F-CAN 500k,
  B-CAN 125k) and the ESP over its COM port. B-CAN gets working scaffolding but
  sends nothing yet.
- **User:** George, at the bench, iterating hands-on. Not an end-user artefact.
- **Why now:** the hardware is on the desk and reachable, and the checksum bug
  meant the frames already reversed were not landing as valid — so "no warnings"
  was never achievable as the code stood.
- **Success:** George looks at the cluster with F-CAN running and sees no warning
  lamps. Separately, every frame's checksum validates against the reference
  Honda algorithm across all counter values, including the 3→0 wrap.
- **Constraint:** George is the only sensor. Changes go in small, individually
  attributable steps so a regression is localisable without a human round-trip
  per byte.
- **Out of scope:** B-CAN frame content and reverse engineering (scaffold only);
  UDS/DTC probing of the cluster's extended frames; video on the MID; the
  Pi/PiCAN deployment path.

**Agreed order:** checksum fix → CANable MCP → F-CAN happy → ESP MCP →
B-CAN scaffold.

---

## What the interview surfaced that the original ask did not say

1. **"Fully happy CAN" is the goal in its own right**, not instrumentation for
   the video hunt. Video may fall out of it, but it is not the acceptance test.
   The opening hypothesis had this backwards.
2. **Two CANables because the cluster has two buses**, not for sniff-plus-transmit
   on one.
3. **B-CAN is a blank sheet.** Nothing reversed. The cluster emits many extended
   (29-bit) frames; fuzzing them produced no reaction.
4. **Verification is George's eyes.** No machine-readable signal, which is why
   the CAN tooling is built for per-frame attribution rather than throughput.
5. **UDS is the deferred idea worth keeping.** Extended IDs on Honda commonly
   carry ISO-TP diagnostics, which would not answer arbitrary payloads — only
   well-formed service requests, with replies on a different ID. That would
   explain the fuzzing silence, and would turn "is it happy" from a photograph
   into a queryable DTC list. Explicitly deferred until after F-CAN is clean.
6. **The ESP MCP was kept in scope** on George's call — the firmware already
   does the hard part, so wrapping it is small.

---

## Outcome

Reached. Gauges read correctly (2500 rpm, 60 kph), zero TX errors across 13,413
frames, cluster otherwise clean. Two lamps remain: **airbag information** and
**autohold flashing**, not yet attributed to a frame.

The checksum work is confirmed against real hardware, not just simulation —
874/874 frames the cluster itself broadcasts validate against `calc_checksum`.

### The constraint changed

The interview recorded "George is the only sensor," and the tooling was built
around that. It is now only partly true: four of the cluster's own broadcast
IDs (`0x309`, `0x378`, `0x516`, `0x374`) change payload in response to what we
send. A bit sweep can be scored automatically by watching those, instead of
costing a human observation per step. Worth exploiting before falling back to
eyeballing.

### Deferred idea that did not pan out

UDS was tried, as agreed, once F-CAN was clean. Nothing answers on either bus —
11-bit `0x700`–`0x7FF` swept, plus `0x7DF` and 29-bit `0x18DB33F1` functional
addresses on both. Consistent with Honda routing diagnostics via a gateway that
is not on the bench. Do not re-attempt blindly; see the misparse trap noted in
PROJECT_STATUS.

### Still unverified against hardware

- Frame periods (10 ms powertrain, 100 ms HUD/status) come from PROJECT_STATUS,
  not from a capture of a real car. They work, but are not known to be right.
- `calc_checksum`'s extended-ID `+3` branch — still unexercised, and the B-CAN
  capture argues those frames do not use the scheme at all.
