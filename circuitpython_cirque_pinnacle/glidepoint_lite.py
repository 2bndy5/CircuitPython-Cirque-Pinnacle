# see license and copyright information in glidepoint.py of this directory
# pylint: disable=missing-class-docstring,missing-function-docstring,missing-module-docstring
__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/2bndy5/CircuitPython_Cirque_Pinnacle.git"
import time
from micropython import const
try:
    from ubus_device import SPIDevice, I2CDevice
except ImportError:
    from adafruit_bus_device.spi_device import SPIDevice
    from adafruit_bus_device.i2c_device import I2CDevice

RELATIVE = const(0)
ABSOLUTE = const(2)

class PinnacleTouch:
    def __init__(self, dr_pin=None):
        self.dr_pin = dr_pin
        if dr_pin is not None:
            self.dr_pin.switch_to_input()
        firmware_id, firmware_ver = self._rap_read_bytes(0, 2)
        if firmware_id != 7 or firmware_ver != 58:
            raise RuntimeError("Cirque Pinnacle ASIC not responding")
        self._mode = 0
        self.sample_rate = 100
        self._rap_write(10, 30)
        self._rap_write_bytes(3, [0, 1, 2])
        self.clear_status_flags()

    @property
    def feed_enable(self):
        return bool(self._rap_read(4) & 1)

    @feed_enable.setter
    def feed_enable(self, is_on):
        is_enabled = self._rap_read(4)
        if is_enabled & 1 != is_on:
            is_enabled = (is_enabled & 254) | is_on
            self._rap_write(4, is_enabled)

    @property
    def data_mode(self):
        return self._mode

    @data_mode.setter
    def data_mode(self, mode):
        self._mode = bool(mode) * 2
        self._rap_write(4, 1 | self._mode)

    @property
    def hard_configured(self):
        return bool(self._rap_read(31))

    def relative_mode_config(self, rotate90=False, taps=True,
                             secondary_tap=True, glide_extend=True,
                             intellimouse=False):
        config2 = (rotate90 << 7) | ((not glide_extend) << 4)
        config2 |= ((not secondary_tap) << 2) | ((not taps) << 1)
        self._rap_write(5, config2 | bool(intellimouse))

    def absolute_mode_config(self, z_idle_count=30,
                             invert_x=False, invert_y=False):
        self._rap_write(10, max(0, min(z_idle_count, 255)))
        config1 = self._rap_read(4) & 63 | (invert_y << 7)
        self._rap_write(4, config1 | (invert_x << 6))

    def report(self, only_new=True):
        return_vals = None
        data_ready = False
        if only_new:
            if self.dr_pin is None:
                data_ready = self._rap_read(2) & 4
            else:
                data_ready = self.dr_pin.value
        if (only_new and data_ready) or not only_new:
            if self.data_mode:
                return_vals = list(self._rap_read_bytes(18, 6))
                return_vals[0] &= 63
                return_vals[2] |= (return_vals[4] & 15) << 8
                return_vals[3] |= (return_vals[4] & 240) << 4
                return_vals[5] &= 63
                del return_vals[4], return_vals[1]
            else:
                return_vals = self._rap_read_bytes(18, 4)
                return_vals[0] &= 7
            self.clear_status_flags()
        return return_vals

    def clear_status_flags(self):
        self._rap_write(2, 0)
        time.sleep(0.00005)

    @property
    def allow_sleep(self):
        return bool(self._rap_read(3) & 4)

    @allow_sleep.setter
    def allow_sleep(self, is_enabled):
        self._rap_write(3, (self._rap_read(3) & 251) | (bool(is_enabled) << 2))

    @property
    def shutdown(self):
        return bool(self._rap_read(3) & 2)

    @shutdown.setter
    def shutdown(self, is_off):
        self._rap_write(3, (self._rap_read(3) & 253) | (bool(is_off) << 1))

    @property
    def sample_rate(self):
        return self._rap_read(9)

    @sample_rate.setter
    def sample_rate(self, val):
        if val in (200, 300):
            self._rap_write(6, 10)
            reload_timer = 6 if val == 300 else 9
            self._era_write(414, reload_timer)
            self._era_write(415, reload_timer)
            val = 0
        else:
            self._rap_write(6, 0)
            self._era_write(414, 19)
            self._era_write(415, 19)
            val = val if val in (100, 80, 60, 40, 20, 10) else 100
        self._rap_write(9, val)

    def _rap_read(self, reg):
        raise NotImplementedError()

    def _rap_read_bytes(self, reg, numb_bytes):
        raise NotImplementedError()

    def _rap_write(self, reg, value):
        raise NotImplementedError()

    def _rap_write_bytes(self, reg, values):
        raise NotImplementedError()

    def _era_read(self, reg):
        prev_feed_state = self.feed_enable
        self.feed_enable = False
        self._rap_write_bytes(28, [reg >> 8, reg & 255])
        self._rap_write(30, 1)
        while self._rap_read(30):
            pass
        buf = self._rap_read(27)
        self.clear_status_flags()
        self.feed_enable = prev_feed_state
        return buf

    def _era_read_bytes(self, reg, numb_bytes):
        buf = b''
        prev_feed_state = self.feed_enable
        self.feed_enable = False
        self._rap_write_bytes(28, [reg >> 8, reg & 255])
        for _ in range(numb_bytes):
            self._rap_write(30, 5)
            while self._rap_read(30):
                pass
            buf += bytes([self._rap_read(27)])
            self.clear_status_flags()
        self.feed_enable = prev_feed_state
        return buf

    def _era_write(self, reg, value):
        prev_feed_state = self.feed_enable
        self.feed_enable = False
        self._rap_write(27, value)
        self._rap_write_bytes(28, [reg >> 8, reg & 255])
        self._rap_write(30, 2)
        while self._rap_read(30):
            pass
        self.clear_status_flags()
        self.feed_enable = prev_feed_state

# pylint: disable=no-member
class PinnacleTouchI2C(PinnacleTouch):
    def __init__(self, i2c, address=0x2A, dr_pin=None):
        self._i2c = I2CDevice(i2c, address)
        super().__init__(dr_pin=dr_pin)

    def _rap_read(self, reg):
        return self._rap_read_bytes(reg, 1)

    def _rap_read_bytes(self, reg, numb_bytes):
        buf = bytes([reg | 160])
        with self._i2c as i2c:
            i2c.write(buf)
            buf = bytearray(numb_bytes)
            i2c.readinto(buf)
        return buf

    def _rap_write(self, reg, value):
        self._rap_write_bytes(reg, [value])

    def _rap_write_bytes(self, reg, values):
        buf = b""
        for index, byte in enumerate(values):
            buf += bytes([(reg + index) | 128, byte & 255])
        with self._i2c as i2c:
            i2c.write(buf)

class PinnacleTouchSPI(PinnacleTouch):
    def __init__(self, spi, ss_pin, spi_frequency=12000000, dr_pin=None):
        self._spi = SPIDevice(spi, chip_select=ss_pin, phase=1,
                              baudrate=spi_frequency)
        super().__init__(dr_pin=dr_pin)

    def _rap_read(self, reg):
        buf_out = bytes([reg | 160]) + b"\xFB" * 3
        buf_in = bytearray(len(buf_out))
        with self._spi as spi:
            spi.write_readinto(buf_out, buf_in)
        return buf_in[3]

    def _rap_read_bytes(self, reg, numb_bytes):
        buf_out = bytes([reg | 160]) + b"\xFC" * (1 + numb_bytes) + b"\xFB"
        buf_in = bytearray(len(buf_out))
        with self._spi as spi:
            spi.write_readinto(buf_out, buf_in)
        return buf_in[3:]

    def _rap_write(self, reg, value):
        buf = bytes([(reg | 128), value])
        with self._spi as spi:
            spi.write(buf)

    def _rap_write_bytes(self, reg, values):
        for i, val in enumerate(values):
            self._rap_write(reg + i, val)
