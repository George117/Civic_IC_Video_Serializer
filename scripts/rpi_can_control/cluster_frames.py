def calc_checksum(data, frame_id, dlc ,offset):
    """
    Calculate checksum of a frame
    :param data: data list
    :param frame_id:
    :param dlc:
    :param offset:
    :return: checksum
    """
    chks = 0
    extended_frame = False

    if frame_id > 0x7FF:
        extended_frame = True

    while frame_id:
        chks += (frame_id & 0xF)
        frame_id >>= 4

    for i in range(0, dlc):
        x = data[i]

        if i == (dlc-1):
            x>>=4
        chks += (x & 0xF) + (x>>4)

    chks = offset - chks

    if extended_frame:
        pass

    chks = chks & 0xF

    return chks


class Frame_ACC_HUD:
    def __init__(self):
        self.id = 0x30C
        self.dlc = 8
        self.checksum_offset = 7
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]
        return self.data


class Frame_EPB_STATUS:
    def __init__(self):
        self.id = 0x1C2
        self.dlc = 8
        self.checksum_offset = 7
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]
        return self.data


class Frame_LKAS_HUD:#check it
    def __init__(self):
        self.id = 0x33D
        self.dlc = 5
        self.checksum_offset = 7
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte4 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data


class Frame_CRUISE:
    def __init__(self):
        self.id = 0x324
        self.dlc = 8
        self.checksum_offset = 5
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data


class Frame_RADAR_HUD:
    def __init__(self):
        self.id = 0x39F
        self.dlc = 8
        self.checksum_offset = 5
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data


class Frame_SEATBELT_STATUS:
    def __init__(self):
        self.id = 0x305
        self.dlc = 7
        self.checksum_offset = 5
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte6 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, self.checksum, byte7]

        return self.data


class Frame_STEER_MOTOR_TORQUE:
    def __init__(self):
        self.id = 0x1AB
        self.dlc = 3
        self.checksum_offset = 7
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte2 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data


class Frame_VSA_STATUS:
    def __init__(self):
        self.id = 0x1A4
        self.dlc = 8
        self.checksum_offset = 7
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data


class Frame_BRAKE_COMMAND:
    def __init__(self):
        self.id = 0x1FA
        self.dlc = 8
        self.checksum_offset = 7
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data

class Frame_HIGHBEAM_CONTROL:
    def __init__(self):
        self.id = 0x35E
        self.dlc = 8
        self.checksum_offset = 5
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data


class Frame_POWERTRAIN_DATA:
    def __init__(self):
        self.id = 0x17C
        self.dlc = 8
        self.checksum_offset = 7
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data

class Frame_RPM_DATA:
    def __init__(self):
        self.id = 0x1DC
        self.dlc = 8
        self.checksum_offset = 7
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

        # signals
        self.rpm = 0

    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        byte1 = self.rpm >> 8
        byte2 = self.rpm & 0xFF


        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)


        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data


class Frame_ENGINE_DATA:
    def __init__(self):
        self.id = 0x158
        self.dlc = 8
        self.checksum_offset = 7
        self.counter = 0
        self.checksum = 0
        self.data = [0, 0, 0, 0, 0, 0, 0, 0]

        # signals
        self.vehicle_speed = 0


    def encode(self):
        byte0 = byte1 = byte2 = byte3 = byte4 = byte5 = byte6 = byte7 = 0

        vehicle_speed = int((self.vehicle_speed - (self.vehicle_speed * 0.045)) * 100) # 4.5% correction

        byte0 = (vehicle_speed & 0xFF00) >> 8
        byte1 = vehicle_speed & 0xFF

        byte4 = (vehicle_speed & 0xFF00) >> 8
        byte5 = vehicle_speed & 0xFF

        self.counter = self.counter + 1

        if self.counter > 3:
            self.counter = 0

        byte7 = (self.counter << 4) | self.checksum

        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]
        self.checksum = calc_checksum(self.data, self.id, self.dlc, self.checksum_offset)
        self.data = [byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7]

        return self.data


if __name__ == '__main__':

    rpm_data = Frame_RPM_DATA()
    rpm_data.rpm = 8000

    speed_data = Frame_ENGINE_DATA()
    speed_data.vehicle_speed = 100

    print(rpm_data.encode())
    print(speed_data.encode())

    print("Hello World")