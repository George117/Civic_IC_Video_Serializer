"""B-CAN (body bus, 125 kbps) frame scaffolding.

No frame meanings are reverse engineered yet. This exists so that adding the
first real B-CAN frame is a matter of filling in a class, not building the
plumbing.

Measured from the cluster on 2026-08-15 (125 kbps, 6 s capture):

  * 28 unique IDs, ALL extended (29-bit), all in the 0x0A/0x0E/0x12/0x16 F8-F9
    ranges and every one ending in 0x50 -- almost certainly a node address.
  * Periods cluster at 100, 200, 300, 500 and 1000 ms.
  * Payloads are STATIC. Not one ID varied its data across the capture, which
    means these frames carry no rolling counter.

  * The Honda counter/checksum scheme does NOT apply here. Checked against all
    793 captured frames: 2 matched, which is below chance. On F-CAN the same
    check matched 874/874. Use RawBCanFrame -- BCanFrame is kept only in case a
    frame turns up that does carry the F-CAN scheme, and remains unverified.

Fuzzing these produced no reaction. Extended IDs on Honda commonly carry ISO-TP
diagnostics, which would not answer arbitrary payloads -- only well-formed
service requests, with the reply arriving on a different ID. That is the next
thing to test, after F-CAN is clean.

Caution: calc_checksum adds 3 for extended IDs. That branch has still never
been confirmed against hardware -- the B-CAN capture above argues these frames
do not use it at all.
"""

from cluster_frames import ClusterFrame, calc_checksum  # noqa: F401


class BCanFrame(ClusterFrame):
    """A B-CAN frame that carries the Honda counter/checksum in its last byte.

    Set ``extended = True`` for a 29-bit ID. Unverified on this bus -- see the
    module docstring.
    """

    extended = False


class RawBCanFrame:
    """A fixed-payload B-CAN frame with no counter and no checksum.

    The safer starting point: it transmits exactly the bytes given, which is
    what replaying a captured frame needs.
    """

    id = 0
    dlc = 8
    extended = False

    def __init__(self, arbitration_id=None, data=None, extended=None):
        if arbitration_id is not None:
            self.id = arbitration_id
        if extended is not None:
            self.extended = extended
        self.data = list(data) if data is not None else [0] * self.dlc
        self.dlc = len(self.data)

    def encode(self):
        return list(self.data)


# Populated as frames are identified. The MCP server registers everything here
# onto the B-CAN broadcaster at import.
#
# Each entry: (frame_class_or_instance, period_ms)
#
# --- EXPERIMENTAL, NOT REVERSE ENGINEERED -----------------------------------
# These are a hypothesis test, not identified frames. Delete them once the
# experiment is done; do not treat them as known-good definitions.
#
# PROJECT_STATUS finding 20: B-CAN IDs decompose as J1939
# (priority / EDP / DP / PF / PS / SA), and every captured frame has SA = 0x50,
# the cluster. At boot -- and only at boot -- the cluster broadcasts
# 0x12EAFF50 with payload "F8 10". PF 0xEA is the J1939 Request PGN, and the
# requested PGN must be 0xF810 (PF=0xF8, PS=0x10) because 0x10F8 is not a
# well-formed PGN: PDU1 PGNs always have PS=0. PS=0x10 appears in no capture,
# so nothing on this bench answers that request.
#
# The reply's source address is unknown, so we broadcast the same PGN from
# eight candidate addresses at once -- one power cycle tests all eight, since
# the request is boot-only and a late reply is ignored.
#
# The PAYLOAD is also unknown; zeros are a placeholder. A null result therefore
# disproves only the zero-payload version of this, not the hypothesis.
_REPLY_PGN_ID = 0x12F81000  # prio 4, EDP 1, PF 0xF8, PS 0x10; low byte = SA
_CANDIDATE_SOURCE_ADDRESSES = (0x10, 0x20, 0x30, 0x40, 0x60, 0x70, 0x80, 0xE0)

BCAN_FRAMES = [
    (
        RawBCanFrame(
            arbitration_id=_REPLY_PGN_ID | _sa,
            data=[0x00] * 8,
            extended=True,
        ),
        100,
    )
    for _sa in _CANDIDATE_SOURCE_ADDRESSES
]
