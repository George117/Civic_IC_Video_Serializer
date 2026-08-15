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
# Empty on purpose. Nothing on this bus is reverse engineered yet, and anything
# added here transmits fabricated traffic onto a bus we are still trying to
# characterise -- which contaminates captures. Add frames only for a specific
# experiment, and remove them when it finishes.
#
# Tried and removed 2026-08-15 (see PROJECT_STATUS finding 20 for the full
# reasoning and result): the cluster broadcasts a J1939 Request (0x12EAFF50,
# PF=0xEA) for PGN 0xF810 at boot, and nothing answers it. We replied with that
# PGN from eight candidate source addresses (0x12F810<SA>, 8 zero bytes, 100 ms)
# across a power cycle. The cluster ACKed every frame -- B-CAN tx_errors stayed
# 0 -- and still re-issued the same request at the next boot, unchanged.
#
# So: the address sweep is covered, and a zero payload is not the answer. Do not
# repeat that experiment as-is. The untested variable is the PAYLOAD.
BCAN_FRAMES = []
