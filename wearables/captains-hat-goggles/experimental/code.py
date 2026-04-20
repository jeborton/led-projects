"""
Top Hat
"""
# pylint: disable=global-statement

import time
import array
import math
import audiobusio
import board
import neopixel

from adafruit_ble import BLERadio
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.nordic import UARTService
from adafruit_bluefruit_connect.packet import Packet
from adafruit_bluefruit_connect.color_packet import ColorPacket
from adafruit_bluefruit_connect.button_packet import ButtonPacket
print ("Here we go!")

ble = BLERadio()
ble.name = "JEB Tophat"
uart_service = UARTService()
advertisement = ProvideServicesAdvertisement(uart_service)

# User input vars
mode = 0  # 0=rainbow, 1=larsen_scanner, 2=audio, 3=solid
user_color = (127, 0, 0)
j = 0  # color for rainbow effect

# Audio meter vars
NUM_PIXELS = 100
NEOPIXEL_PIN = board.D1
# Use if you want to use the NeoPixels on the Circuit Playground Bluefruit.
# NEOPIXEL_PIN = board.NEOPIXEL

# Restrict value to be between floor and ceiling.
def constrain(value, floor, ceiling):
    return max(floor, min(value, ceiling))

# Scale input_value between output_min and output_max, exponentially.
def log_scale(input_value, input_min, input_max, output_min, output_max):
    normalized_input_value = (input_value - input_min) / \
                             (input_max - input_min)
    return output_min + \
        math.pow(normalized_input_value, SCALE_EXPONENT) \
        * (output_max - output_min)

# Remove DC bias before computing RMS.
def normalized_rms(values):
    minbuf = int(mean(values))
    samples_sum = sum(
        float(sample - minbuf) * (sample - minbuf)
        for sample in values
    )

    return math.sqrt(samples_sum / len(values))

def mean(values):
    return sum(values) / len(values)

def volume_color(volume):
    return 200, volume * (255 // NUM_PIXELS), 0

# Set up NeoPixels and turn them all off.
pixels = neopixel.NeoPixel(NEOPIXEL_PIN, NUM_PIXELS, brightness=0.15, auto_write=False)
pixels.fill(0)
pixels.show()


def wheel(wheel_pos):
    # Input a value 0 to 255 to get a color value.
    # The colours are a transition r - g - b - back to r.
    if wheel_pos < 0 or wheel_pos > 255:
        r = g = b = 0
    elif wheel_pos < 85:
        r = int(wheel_pos * 3)
        g = int(255 - wheel_pos*3)
        b = 0
    elif wheel_pos < 170:
        wheel_pos -= 85
        r = int(255 - wheel_pos*3)
        g = 0
        b = int(wheel_pos*3)
    else:
        wheel_pos -= 170
        r = 0
        g = int(wheel_pos*3)
        b = int(255 - wheel_pos*3)
    return (r, g, b)

def rainbow_corset(j, delay):
    chunk_size = 25

    for start in range(0, NUM_PIXELS, chunk_size):
        end = min(start + chunk_size, NUM_PIXELS)
        for i in range(start, end):
            pixel_index = ((i - start) * 256 // chunk_size) + j
            pixels[i] = wheel(pixel_index & 255)
    pixels.show()
    time.sleep(delay)


pos = 0  # position
direction = 1  # direction of "eye"

def larsen_set(index, color):
    if index < 0:
        return
    else:
        pixels[index] = color

def larsen(delay):
    global pos
    global direction
    color_dark = (int(user_color[0]/8), int(user_color[1]/8),
                  int(user_color[2]/8))
    color_med = (int(user_color[0]/2), int(user_color[1]/2),
                 int(user_color[2]/2))

    larsen_set(pos - 3, color_dark)
    larsen_set(pos - 2, color_dark)
    larsen_set(pos - 1, color_med)
    larsen_set(pos, user_color)
    larsen_set(pos + 1, color_med)
    larsen_set(pos + 2, color_med)

    if (pos + 3) < NUM_PIXELS:
        # Dark red, do not exceed number of pixels
        larsen_set(pos + 2, color_dark)

    pixels.write()
    time.sleep(delay)

    # Erase all and draw a new one next time
    for j in range(-2, 2):
        larsen_set(pos + j, (0, 0, 0))
        if (pos + 3) < NUM_PIXELS:
            larsen_set(pos + 2, (0, 0, 0))
    #fade skirt with position

    brightness = pos / NUM_PIXELS  # value between 0.0 and 1.0

    # Bounce off ends of strip
    pos += direction
    if pos < 0:
        pos = 1
        direction = -direction
    elif pos >= (NUM_PIXELS - 2):
        pos = NUM_PIXELS - 3
        direction = -direction

def solid(new_color):
    pixels.fill(new_color)
    pixels.show()

def map_value(value, in_min, in_max, out_min, out_max):
    out_range = out_max - out_min
    in_range = in_max - in_min
    return out_min + out_range * ((value - in_min) / in_range)

pulse_state = {"pos": 0, "direction": 1}
dark_pulse_state = {"pos": 0, "direction": 1}

def blend_colors(color1, color2, ratio):
    """Blend two RGB colors by ratio (0.0 = all color1, 1.0 = all color2)."""
    return tuple(
        int(color1[i] * (1 - ratio) + color2[i] * ratio)
        for i in range(3)
    )

def invert_color(color):
    """Return the inverted RGB color."""
    return tuple(255 - c for c in color)

def staff_pulse(pixels, user_color):
    """
    Staff pulse:
      - user_color is background
      - pulse is inverted color of user_color
      - 5-pixel pulse with 20% fade steps
    """
    global pulse_state
    num_pixels = len(pixels)

    pulse_color = invert_color(user_color)

    # Fill with background
    for i in range(num_pixels):
        pixels[i] = user_color

    # Draw pulse head + tail
    for tail_step in range(5):
        index = pulse_state["pos"] - (tail_step * pulse_state["direction"])
        if 0 <= index < num_pixels:
            blend_ratio = tail_step * 0.2
            color = blend_colors(pulse_color, user_color, blend_ratio)
            pixels[index] = color

    # Update position
    pulse_state["pos"] += pulse_state["direction"]
    if pulse_state["pos"] >= num_pixels - 1 or pulse_state["pos"] <= 0:
        pulse_state["direction"] *= -1

    pixels.show()
def dark_pulse(pixels, user_color):
    """
    Dark pulse:
      - user_color is the pulse color
      - background is black
      - 5-pixel pulse with 20% fade steps
    """
    global dark_pulse_state
    num_pixels = len(pixels)

    background = (0, 0, 0)

    # Fill with background
    for i in range(num_pixels):
        pixels[i] = background

    # Draw pulse head + tail
    for tail_step in range(5):
        index = dark_pulse_state["pos"] - (tail_step * dark_pulse_state["direction"])
        if 0 <= index < num_pixels:
            blend_ratio = tail_step * 0.2
            color = blend_colors(user_color, background, blend_ratio)
            pixels[index] = color

    # Update position
    dark_pulse_state["pos"] += dark_pulse_state["direction"]
    if dark_pulse_state["pos"] >= num_pixels - 1 or dark_pulse_state["pos"] <= 0:
        dark_pulse_state["direction"] *= -1

    pixels.show()

def scale_color(color, scale):
    """Scale an RGB color by a factor between 0.0 and 1.0."""
    return tuple(int(c * scale) for c in color)

def solid(pixels, user_color, speed=0.1):
    """
    Fill the strip with user_color, breathing between 10% and 100% brightness.
    speed: 0.01–0.3, where 0.3 is slowest and 0.01 is fastest.
    """
    # Map speed input to duration (1s to 4s), inverting the control
    min_input, max_input = 0.025, 0.25
    min_duration, max_duration = 1.0, 4.0
    norm = (speed - min_input) / (max_input - min_input)
    duration = min_duration + norm * (max_duration - min_duration)

    # Time within this cycle
    t = (time.monotonic() % duration) / duration  # 0.0 → 1.0
    breath_ratio = (math.sin(t * math.pi * 2) + 1) / 2 * 0.9 + 0.1

    scaled_color = scale_color(user_color, breath_ratio)
    for i in range(len(pixels)):
        pixels[i] = scaled_color
    pixels.show()
speed = 6.0
wait = 0 #0.097

def change_speed(mod, old_speed):
    new_speed = constrain(old_speed + mod, 1.0, 10.0)
    return(new_speed, map_value(new_speed, 10.0, 0.0, 0.025, 0.25))

def change_ceiling(mod, old_ceiling):
    new_ceiling = constrain(old_ceiling + mod * 100, 100, 2000)
    print(new_ceiling)
    return(new_ceiling)

def animate(pause, j):
    # Determine animation based on mode
    #print("Pause: ", pause)
    if mode == 0:
        rainbow_corset(j, 0)
    elif mode == 1:
        staff_pulse(pixels, user_color)
        time.sleep(pause)
    elif mode == 2:
        solid(pixels, user_color, pause)
        #solid(user_color)
    elif mode ==3:
        dark_pulse(pixels, user_color)
        time.sleep(pause)
        #larsen(pause)
    return

while True:
    ble.start_advertising(advertisement)
    while not ble.connected:
        # Animate while disconnected
        animate(wait, j)
        j = j + 1
        if j > 255:
            j = 0

    # While BLE is connected
    while ble.connected:
        if uart_service.in_waiting:
            try:
                packet = Packet.from_stream(uart_service)
            # Ignore malformed packets.
            except ValueError:
                continue

            # Received ColorPacket
            if isinstance(packet, ColorPacket):
                user_color = packet.color

            # Received ButtonPacket
            elif isinstance(packet, ButtonPacket):
                if packet.pressed:
                    if packet.button == ButtonPacket.UP:
                        speed, wait = change_speed(1, speed)
                    elif packet.button == ButtonPacket.DOWN:
                        speed, wait = change_speed(-1, speed)
                    #elif packet.button == ButtonPacket.RIGHT:
                        #input_ceiling = change_ceiling(1, input_ceiling)
                    #elif packet.button == ButtonPacket.LEFT:
                        #input_ceiling = change_ceiling(-1, input_ceiling)
                    elif packet.button == ButtonPacket.BUTTON_1:
                        mode = 0
                    elif packet.button == ButtonPacket.BUTTON_2:
                        mode = 1
                    elif packet.button == ButtonPacket.BUTTON_3:
                        mode = 2
                        pos = 0
                        direction = 1
                    elif packet.button == ButtonPacket.BUTTON_4:
                        mode = 3

        # Animate while connected
        animate(wait, j)
        j = j + int(speed)
        if j > 255:
            j = 0
