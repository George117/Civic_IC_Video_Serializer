import can
import time
from cluster_frames import *
from pican_driver import *


class CANInterface:
    def __init__(self, channel, bitrate=500000):
        """
        Initializes a CAN interface.

        :param channel: The CAN interface (e.g., 'can0' or 'can1').
        :param bitrate: The CAN bus bitrate (default: 500000).
        """
        self.channel = channel
        self.bitrate = bitrate
        self.bus = None
        self.start_bus()

    def start_bus(self):
        """Starts the CAN bus interface."""
        try:
            self.bus = can.interface.Bus(channel=self.channel, interface='socketcan')
            print(f"CAN interface {self.channel} initialized.")
        except Exception as e:
            print(f"Failed to initialize {self.channel}: {e}")

    def send_frame(self, arbitration_id, frame_dlc, data):
        """
        Sends a CAN frame.

        :param arbitration_id: CAN ID (standard format: 11-bit).
        :param frame_dlc: Frame lenght.
        :param data: List of bytes (max 8 for standard CAN).
        """
        try:
            msg = can.Message(arbitration_id=arbitration_id, dlc=frame_dlc, data=data, is_extended_id=False)
            self.bus.send(msg)
        except can.CanError as e:
            print(f"Error sending on {self.channel}: {e}")

    def receive_frame(self, timeout=1.0):
        """
        Receives a CAN frame (blocking with timeout).

        :param timeout: Time in seconds to wait for a message (default: 1s).
        :return: Received CAN message or None if timeout occurs.
        """
        try:
            msg = self.bus.recv(timeout)
            if msg:
                print(f"Received on {self.channel}: ID={hex(msg.arbitration_id)}, Data={list(msg.data)}")
                return msg
            else:
                print(f"No message received on {self.channel} within {timeout} sec.")
        except can.CanError as e:
            print(f"Error receiving on {self.channel}: {e}")
        return None

    def close(self):
        """Closes the CAN bus interface."""
        if self.bus:
            self.bus.shutdown()
            print(f"CAN interface {self.channel} closed.")




# Example usage
if __name__ == "__main__":
    can0 = CANInterface("can0", 500000)
    can1 = CANInterface("can1", 125000)

    led1_state = "OFF"
    led2_state = "OFF"
    led3_state = "OFF"

    display = PiCAN_Display()
    switches = PiCAN_Switches()
    leds = PiCAN_LEDs()

    display.write_text("Civic IC demo", 0, 0)

    rpm = 0 # rpm
    speed = 0 # kph

    counter_speed = 0
    counter_rpm = 0

    rpm_data = Frame_RPM_DATA()
    speed_data = Frame_ENGINE_DATA()

    # needed only to make the cluster happy -> no WLs
    acc_hud = Frame_ACC_HUD()
    epb_status = Frame_EPB_STATUS()
    lkas_hud = Frame_LKAS_HUD()
    cruise = Frame_CRUISE()
    radar_hud = Frame_RADAR_HUD()
    seatbelt_status = Frame_SEATBELT_STATUS()
    steer_motor_torque = Frame_STEER_MOTOR_TORQUE()
    vsa_status = Frame_VSA_STATUS()
    brake_command = Frame_BRAKE_COMMAND()
    high_beam_control = Frame_HIGHBEAM_CONTROL()
    powetrain_data = Frame_POWERTRAIN_DATA()

    try:
        while True:

            pressed_switch = switches.read_switch()
            if pressed_switch == switches.SW1:
                rpm += 100
                leds.write_led(leds.LED1, 1)
                led1_state = "ON"
            else:
                leds.write_led(leds.LED1, 0)
                led1_state = "OFF"

            if pressed_switch == switches.SW2:
                rpm -= 100
                leds.write_led(leds.LED2, 1)
                led2_state = "ON"
            else:
                leds.write_led(leds.LED2, 0)
                led2_state = "OFF"

            if pressed_switch == switches.SW3:
                speed += 10
                leds.write_led(leds.LED3, 1)
                led3_state = "ON"
            else:
                leds.write_led(leds.LED3, 0)
                led3_state = "OFF"

            if rpm > 8000:
                rpm = 7999
            if rpm < 1:
                rpm = 0

            if speed > 300:
                speed = 0

            rpm_data.rpm = rpm
            speed_data.vehicle_speed = speed

            display.write_text(f"Spd: {speed} RPM: {rpm}", 0, 9)

            can0.send_frame(rpm_data.id, rpm_data.dlc, rpm_data.encode())
            can0.send_frame(speed_data.id, speed_data.dlc, speed_data.encode())
            can0.send_frame(acc_hud.id, acc_hud.dlc, acc_hud.encode())
            can0.send_frame(epb_status.id, epb_status.dlc, epb_status.encode())
            can0.send_frame(lkas_hud.id, lkas_hud.dlc, lkas_hud.encode())
            can0.send_frame(cruise.id, cruise.dlc, cruise.encode())
            can0.send_frame(radar_hud.id, radar_hud.dlc, radar_hud.encode())
            can0.send_frame(seatbelt_status.id, seatbelt_status.dlc, seatbelt_status.encode())
            can0.send_frame(steer_motor_torque.id, steer_motor_torque.dlc, steer_motor_torque.encode())
            can0.send_frame(vsa_status.id, vsa_status.dlc, vsa_status.encode())
            can0.send_frame(brake_command.id, brake_command.dlc, brake_command.encode())
            can0.send_frame(high_beam_control.id, high_beam_control.dlc, high_beam_control.encode())
            can0.send_frame(powetrain_data.id, powetrain_data.dlc, powetrain_data.encode())

    except KeyboardInterrupt:
        print("\nCleanup")
        # Cleanup
        display.cleanup()
        switches.cleanup()
        leds.cleanup()
        can0.close()
        can1.close()




