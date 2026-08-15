"""Validate encoded frames against an independent Honda checksum implementation.

The reference below is transcribed from the widely-used Honda algorithm and is
deliberately written from scratch rather than importing calc_checksum, so a bug
in cluster_frames cannot mask itself.

A receiver validates a frame by recomputing the checksum over the bytes as they
arrived and comparing against the nibble it finds in the last byte. That is
exactly what check_frame() does here.

Run: python3 test_checksum.py     (no dependencies)
"""

from cluster_frames import CLUSTER_FRAMES, Frame_RPM_DATA, Frame_ENGINE_DATA


def reference_checksum(address, data):
    """Reference Honda checksum, independent of cluster_frames."""
    s = 0
    extended = address > 0x7FF

    while address > 0:
        s += (address & 0xF)
        address >>= 4

    for i in range(len(data)):
        x = data[i]
        if i == len(data) - 1:
            x >>= 4
        s += (x & 0xF) + (x >> 4)

    s = 8 - s
    if extended:
        s += 3

    return s & 0xF


def check_frame(frame_id, data):
    """True if the checksum carried in the frame matches its contents."""
    return reference_checksum(frame_id, data) == (data[-1] & 0xF)


def main():
    failures = []
    checked = 0

    # Every frame, every counter value. Eight iterations covers two full counter
    # cycles, so the 3->0 wrap that used to break is exercised twice.
    for cls in CLUSTER_FRAMES:
        frame = cls()
        seen_counters = []

        for _ in range(8):
            data = frame.encode()
            checked += 1

            if len(data) != frame.dlc:
                failures.append(
                    f"{cls.__name__}: encode() returned {len(data)} bytes, dlc is {frame.dlc}"
                )

            if any(b < 0 or b > 0xFF for b in data):
                failures.append(f"{cls.__name__}: byte out of range in {data}")

            counter = (data[frame.dlc - 1] >> 4) & 0x3
            seen_counters.append(counter)

            if not check_frame(frame.id, data):
                failures.append(
                    f"{cls.__name__} (0x{frame.id:03X}) counter={counter}: "
                    f"carried 0x{data[-1] & 0xF:X}, expected "
                    f"0x{reference_checksum(frame.id, data):X}  data={[hex(b) for b in data]}"
                )

        if sorted(set(seen_counters)) != [0, 1, 2, 3]:
            failures.append(f"{cls.__name__}: counter did not cycle 0-3, saw {seen_counters}")

    # Signals must survive encoding, and must not disturb the checksum.
    rpm = Frame_RPM_DATA()
    for value in (0, 1, 750, 3500, 7999, 8000):
        rpm.rpm = value
        data = rpm.encode()
        checked += 1
        if (data[1] << 8 | data[2]) != value:
            failures.append(f"RPM {value} did not round-trip: {[hex(b) for b in data]}")
        if not check_frame(rpm.id, data):
            failures.append(f"RPM {value}: bad checksum")

    speed = Frame_ENGINE_DATA()
    for value in (0, 30, 100, 255, 300):
        speed.vehicle_speed = value
        data = speed.encode()
        checked += 1
        if not check_frame(speed.id, data):
            failures.append(f"speed {value}: bad checksum")
        if data[0:2] != data[4:6]:
            failures.append(f"speed {value}: byte0-1 and byte4-5 disagree")

    print(f"checked {checked} encoded frames across {len(CLUSTER_FRAMES)} frame types")

    if failures:
        print(f"\nFAIL - {len(failures)} problem(s):")
        for f in failures:
            print(f"  {f}")
        return 1

    print("PASS - every frame validates against the reference algorithm")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
