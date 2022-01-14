import time

packet_size = 3072  # 0xC00, 12 x 256


class GalvoMock:
    """
    The mock sender is a fake USB device to be set in place of GalvoUsb to test for bugs and watch data in the
    controller.

    Rather than really connect it just tests the data being sent to it and can provide debug information etc.
    """

    def __init__(self, channel=None):
        self.channel = channel
        self.connected = False
        self.count = 0

    def write_command(self, query):
        assert self.connected
        assert isinstance(query, (bytearray, bytes))
        assert len(query) == 12
        self.channel(str(query))
        time.sleep(0.05)

    def read_reply(self):
        self.count += 1
        if self.count % 3 == 0:
            return b"\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF"
        if self.count % 3 == 1:
            return b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        if self.count % 3 == 2:
            import random
            return bytes([random.randint(0, 0xFF) for i in range(14)])

    def write_block(self, packet):
        assert self.connected
        assert isinstance(packet, (bytearray, bytes))
        assert len(packet) == 0xC00
        self.channel(
            "{packet}... {size}".format(packet=str(packet[:20]), size=len(packet))
        )
        time.sleep(0.2)

    def canned_read(self, *args):
        assert self.connected
        self.channel(str(args))
        return b"\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF"

    def canned_write(self, *args):
        assert self.connected
        self.channel(str(args))

    def connect(self):
        assert not self.connected
        if self.channel:
            self.channel("Connecting...")
        if self.channel:
            self.channel("Mock.")
        if self.channel:
            self.channel("Connected...")
        self.connected = True
        return self

    def disconnect(self):
        assert self.connected
        self.connected = False
        if self.channel:
            self.channel("Disconnecting")
