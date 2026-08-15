"""Honda Civic Gen 10 cluster frame definitions (F-CAN, 500 kbps).

Every frame carries a 2-bit rolling counter and a 4-bit checksum packed into
the top and bottom nibbles of its last byte. The cluster rejects a frame whose
checksum does not match, which is what keeps warning lamps lit.
"""


def calc_checksum(data, frame_id, dlc):
    """Honda 4-bit frame checksum.

    Sums the nibbles of the arbitration ID and of every data byte, subtracts
    from 8, and keeps the low nibble. The final byte contributes only its
    counter nibble -- the checksum nibble is masked out, because the receiver
    has to compute this over a frame that already contains it.

    :param data: data list, at least dlc long
    :param frame_id: arbitration ID
    :param dlc: frame length
    :return: checksum nibble
    """
    chks = 0
    extended_frame = frame_id > 0x7FF

    while frame_id:
        chks += (frame_id & 0xF)
        frame_id >>= 4

    for i in range(0, dlc):
        x = data[i]

        if i == (dlc - 1):
            x >>= 4
        chks += (x & 0xF) + (x >> 4)

    chks = 8 - chks

    if extended_frame:
        chks += 3

    chks = chks & 0xF

    return chks


class ClusterFrame:
    """Base for every cluster frame.

    Subclasses set ``id`` and ``dlc`` and override ``pack()`` to lay their
    signals into the buffer. The counter and checksum are handled here so all
    frames stay in step -- the ordering below matters:

      1. advance the counter
      2. write the counter with an empty checksum nibble
      3. checksum the buffer as it will be transmitted
      4. merge the checksum into the same byte

    Computing the checksum before the counter is written -- which is what this
    file used to do -- transmits the previous frame's checksum.
    """

    id = 0
    dlc = 8

    def __init__(self):
        self.counter = 0
        self.checksum = 0
        self.data = [0] * self.dlc

    def pack(self, data):
        """Lay this frame's signals into ``data``. Override as needed.

        Must not touch byte ``dlc - 1``; that belongs to the counter and
        checksum.
        """

    def encode(self):
        data = [0] * self.dlc
        self.pack(data)

        chk_byte = self.dlc - 1

        self.counter = (self.counter + 1) & 0x3
        data[chk_byte] = self.counter << 4
        self.checksum = calc_checksum(data, self.id, self.dlc)
        data[chk_byte] = (self.counter << 4) | self.checksum

        self.data = data
        return data


class Frame_ACC_HUD(ClusterFrame):
    id = 0x30C
    dlc = 8


class Frame_EPB_STATUS(ClusterFrame):
    id = 0x1C2
    dlc = 8


class Frame_LKAS_HUD(ClusterFrame):
    id = 0x33D
    dlc = 5


class Frame_CRUISE(ClusterFrame):
    id = 0x324
    dlc = 8


class Frame_RADAR_HUD(ClusterFrame):
    id = 0x39F
    dlc = 8


class Frame_SEATBELT_STATUS(ClusterFrame):
    id = 0x305
    dlc = 7


class Frame_STEER_MOTOR_TORQUE(ClusterFrame):
    id = 0x1AB
    dlc = 3


class Frame_VSA_STATUS(ClusterFrame):
    id = 0x1A4
    dlc = 8


class Frame_BRAKE_COMMAND(ClusterFrame):
    id = 0x1FA
    dlc = 8


class Frame_HIGHBEAM_CONTROL(ClusterFrame):
    id = 0x35E
    dlc = 8


class Frame_POWERTRAIN_DATA(ClusterFrame):
    id = 0x17C
    dlc = 8


class Frame_RPM_DATA(ClusterFrame):
    id = 0x1DC
    dlc = 8

    def __init__(self):
        super().__init__()
        self.rpm = 0

    def pack(self, data):
        data[1] = (self.rpm >> 8) & 0xFF
        data[2] = self.rpm & 0xFF


class Frame_ENGINE_DATA(ClusterFrame):
    id = 0x158
    dlc = 8

    def __init__(self):
        super().__init__()
        self.vehicle_speed = 0

    def pack(self, data):
        speed = int((self.vehicle_speed - (self.vehicle_speed * 0.045)) * 100)  # 4.5% correction

        data[0] = (speed & 0xFF00) >> 8
        data[1] = speed & 0xFF

        data[4] = (speed & 0xFF00) >> 8
        data[5] = speed & 0xFF


# Everything the cluster wants to see on F-CAN to sit without warning lamps.
CLUSTER_FRAMES = [
    Frame_RPM_DATA,
    Frame_ENGINE_DATA,
    Frame_ACC_HUD,
    Frame_EPB_STATUS,
    Frame_LKAS_HUD,
    Frame_CRUISE,
    Frame_RADAR_HUD,
    Frame_SEATBELT_STATUS,
    Frame_STEER_MOTOR_TORQUE,
    Frame_VSA_STATUS,
    Frame_BRAKE_COMMAND,
    Frame_HIGHBEAM_CONTROL,
    Frame_POWERTRAIN_DATA,
]


if __name__ == '__main__':

    rpm_data = Frame_RPM_DATA()
    rpm_data.rpm = 8000

    speed_data = Frame_ENGINE_DATA()
    speed_data.vehicle_speed = 100

    print(rpm_data.encode())
    print(speed_data.encode())
