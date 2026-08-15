import time
import RPi.GPIO as GPIO
from board import SCL, SDA
import busio
from PIL import Image, ImageDraw, ImageFont

# Import the SSD1306 module.
import adafruit_ssd1306


class PiCAN_LEDs:
    def __init__(self):
        self.gpio_sts1 = 4
        self.gpio_sts2 = 17
        self.gpio_sts3 = 18

        self.LED1 = 1
        self.LED2 = 2
        self.LED3 = 3

        GPIO.setmode(GPIO.BCM)  # Use Broadcom pin numbering
        GPIO.setwarnings(False)  # Disable GPIO warnings

        GPIO.setup(self.gpio_sts1, GPIO.OUT)
        GPIO.setup(self.gpio_sts2, GPIO.OUT)
        GPIO.setup(self.gpio_sts3, GPIO.OUT)

        GPIO.output(self.gpio_sts1, 0)
        GPIO.output(self.gpio_sts1, 0)
        GPIO.output(self.gpio_sts1, 0)

    def write_led(self, led, state):
        if led == self.LED1:
            GPIO.output(self.gpio_sts1, state)

        if led == self.LED2:
            GPIO.output(self.gpio_sts2, state)

        if led == self.LED3:
            GPIO.output(self.gpio_sts3, state)

    def cleanup(self):
        GPIO.cleanup()


class PiCAN_Switches:
    def __init__(self):
        self.SW1 = 1
        self.SW2 = 2
        self.SW3 = 3

        self.gpio_sw1 = 23
        self.gpio_sw2 = 22
        self.gpio_sw3 = 27

        GPIO.setmode(GPIO.BCM)  # Use Broadcom pin numbering
        GPIO.setwarnings(False)  # Disable GPIO warnings

        GPIO.setup(self.gpio_sw1, GPIO.IN)
        GPIO.setup(self.gpio_sw2, GPIO.IN)
        GPIO.setup(self.gpio_sw3, GPIO.IN)

    def read_switch(self):
        """
        Reads the state of the switches and returns the corresponding identifier.

        Returns:
            int: Switch identifier (SW1, SW2, SW3) if pressed, else 0.
        """
        if GPIO.input (self.gpio_sw1) == GPIO.LOW:
            time.sleep(0.01)
            if GPIO.input(self.gpio_sw1) == GPIO.LOW:
                return self.SW1

        if GPIO.input (self.gpio_sw2) == GPIO.LOW:
            time.sleep(0.01)
            if GPIO.input(self.gpio_sw2) == GPIO.LOW:
                return self.SW2

        if GPIO.input (self.gpio_sw3) == GPIO.LOW:
            time.sleep(0.01)
            if GPIO.input(self.gpio_sw3) == GPIO.LOW:
                return self.SW3

        return 0

    def cleanup(self):
        GPIO.cleanup()



class PiCAN_Display:
    def __init__(self):
        # Init I2C
        try:
            self.i2c = busio.I2C(SCL, SDA)
        except RuntimeError as e:
            print(f"Error initializing I2C: {e}")
            return

        self.display = adafruit_ssd1306.SSD1306_I2C(128, 32, self.i2c)
        self.display.fill(0)
        self.display.show()

        self.width = self.display.width
        self.height = self.display.height

        self.image = Image.new("1", (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

        self.font = ImageFont.load_default()

        #self.draw.text((0, 0), "Display initialized!", font=self.font, fill=255)
        self.display.image(self.image)
        self.display.show()

    def write_text(self, text: str, x: int, y: int):
        """
        Writes text to the display at the specified coordinates.

        Args:
           text (str): The text to be displayed.
           x (int): The x-coordinate of the start pixel [0:128].
           y (int): The y-coordinate of the start pixel.
        """
        self.draw.rectangle((x, y, self.width, self.height), outline=0, fill=0)  # Clear existing text
        self.draw.text((x, y), text, font=self.font, fill=255)
        self.display.image(self.image)
        self.display.show()

    def clear_display(self):
        self.display.fill(0)
        self.display.show()

    def cleanup(self):
        self.clear_display()
        pass


def test_display():
    print("Display test")
    # init display
    display = PiCAN_Display()

    time.sleep(1)

    # write some data on x line
    display.write_text(f"Lucky number {69}", 0, 0)

    display.write_text(f"{69}", 0, 10)
    time.sleep(1)

    # add some data on y line
    display.write_text(f"{96}", 0, 10)
    time.sleep(1)

    # clear display
    display.clear_display()


def test_switches():
    print("Switches test")
    switches = PiCAN_Switches()

    try:
        while True:
            pressed_switch = switches.read_switch()
            if pressed_switch != 0:
                print(f"Switch {pressed_switch} pressed")

    except KeyboardInterrupt:
        print("\nSwitch test terminated.")
        switches.cleanup()  # Clean up GPIO before exiting


def test_leds():
    print("LED test")

    # state
    on = 1
    off = 0

    led_counter = 0

    leds = PiCAN_LEDs()

    try:
        while True:
            leds.write_led(led_counter, on)
            time.sleep(1)

            leds.write_led(led_counter, off)
            time.sleep(1)

            led_counter += 1
            if led_counter > 3:
                led_counter = 1

    except KeyboardInterrupt:
        print("\nLED test terminated.")
        leds.cleanup()  # Clean up GPIO before exiting


def test_pican_hat():
    print("PiCAN Test Started...")

    display = PiCAN_Display()
    switches = PiCAN_Switches()
    leds = PiCAN_LEDs()

    display.write_text(f"PiCAN Test Started...", 0, 0)

    sw1 = led1 = 1
    sw2 = led2 = 2
    sw3 = led3 = 3

    on = 1
    off = 0

    led1_state = "OFF"
    led2_state = "OFF"
    led3_state = "OFF"

    try:
        while True:
            pressed_switch = switches.read_switch()

            if pressed_switch == sw1:
                leds.write_led(led1, on)
                led1_state = "ON"
            else:
                leds.write_led(led1, off)
                led1_state = "OFF"

            if pressed_switch == sw2:
                leds.write_led(led2, on)
                led2_state = "ON"

            else:
                leds.write_led(led2, off)
                led2_state = "OFF"

            if pressed_switch == sw3:
                leds.write_led(led3, on)
                led3_state = "ON"
            else:
                leds.write_led(led3, off)
                led3_state = "OFF"

            display.write_text(f"1: {led1_state} 2: {led2_state} 3: {led3_state}", 0, 9)

    except KeyboardInterrupt:
        print("\nPiCAN HAT test terminated.")
        display.cleanup()
        switches.cleanup()
        leds.cleanup()


if __name__ == "__main__":
    #test_display()
    #test_leds()
    #test_switches()
    test_pican_hat()
