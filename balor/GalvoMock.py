import time

import usb.core
import usb.util
from usb.backend.libusb1 import LIBUSB_ERROR_ACCESS, LIBUSB_ERROR_NOT_FOUND

packet_size = 3072  # 0xC00, 12 x 256


class GalvoMock:
    def __init__(self, channel=None):
        self.channel = channel
        self.connected = False
        self.count = 0

    def write_command(self, query):
        assert (self.connected)
        assert (isinstance(query, (bytearray, bytes)))
        assert (len(query) == 12)
        self.channel(str(query))
        time.sleep(0.05)

    def read_reply(self):
        if self.count % 1:
            return b'\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF'
        else:
            return b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

    def write_block(self, packet):
        assert (self.connected)
        assert (isinstance(packet, (bytearray, bytes)))
        assert (len(packet) == 0xC00)
        self.channel("{packet}... {size}".format(packet=str(packet[:20]), size=len(packet)))
        time.sleep(0.2)

    def canned_read(self, *args):
        assert (self.connected)
        self.channel(str(args))
        return b'\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF'

    def canned_write(self, *args):
        assert (self.connected)
        self.channel(str(args))

    def connect(self):
        assert (not self.connected)
        if self.channel:
            self.channel("Connecting...")
        if self.channel:
            self.channel("Mock.")
        if self.channel:
            self.channel("Connected...")
        self.connected = True
        return self

    def disconnect(self):
        assert (self.connected)
        self.connected = False
        if self.channel:
            self.channel("Disconnecting")
