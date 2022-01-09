import time

from balor.GalvoUsb import GalvoUsb

EnableLaser = 0x04
ExecuteList = 0x05
SetPwmPulseWidth = 0x06
GetVersion = 0x07
GetSerialNo = 0x09
GetListStatus = 0x0A
GetPositionXY = 0x0C
GotoXY = 0x0D
LaserSignalOff = 0x0E
LaserSignalOn = 0x0F
ResetList = 0x12
RestartList = 0x13
WriteCorTable = 0x15
SetControlMode = 0x16
SetDelayMode = 0x17
SetMaxPolyDelay = 0x18
SetEndOfList = 0x19
SetFirstPulseKiller = 0x1A
SetLaserMode = 0x1B
SetTiming = 0x1C
SetStandby = 0x1D
SetPwmHalfPeriod = 0x1E
StopExecute = 0x1F
DisableLaser = 0x2
StopList = 0x20
WritePort = 0x21
WriteAnalogPort1 = 0x22
WriteAnalogPort2 = 0x23
WriteAnalogPortX = 0x24
ReadPort = 0x25
SetAxisMotionParam = 0x26
SetAxisOriginParam = 0x27
AxisGoOrigin = 0x28
MoveAxisTo = 0x29
GetAxisPos = 0x2A
GetFlyWaitCount = 0x2B
GetMarkCount = 0x2D
SetFpkParam2 = 0x2E
IPG_OpemMO = 0x33
IPG_GETStMO_AP = 0x34
ENABLEZ = 0x3A
SETZDATA = 0x3B
SetSPISimmerCurrent = 0x3C
SetFpkParam = 0x62

# These are used during the Open and Close procedures. In the interest of rocking the boat as little as possible they
# are preserved. These should be replaced.
from .BJJCZ_LMCV4_FIBER_M_blobs import init as INIT_BLOB_SEQUENCE
from .BJJCZ_LMCV4_FIBER_M_blobs import quit as QUIT_BLOB_SEQUENCE


class GalvoConnection:
    """
    This is a much more meerk40t friendly version of BJJCZ.
    """

    def __init__(self, service):
        self.service = service
        self.channel = service.channel("galvo-connect")
        self.usb = GalvoUsb(service.channel("galvo-usb"))
        self.connected = False

    def send_command(self, query_code, parameter=0x0000, parameter2=0x0000):
        """
        Send command sends a command to the galvo. See the list if predetermined USB commands.

        :param query_code: command_code be sent.
        :param parameter:
        :param parameter2:
        :return:
        """
        query = bytearray([0] * 12)
        query[0] = query_code & 0xFF
        query[1] = query_code >> 8
        query[2] = parameter & 0xFF
        query[3] = (parameter & 0xFF00) >> 8
        query[4] = parameter2 & 0xFF
        query[5] = (parameter2 & 0xFF00) >> 8
        self.usb.write_command(query)
        return self._get_reply()

    def _get_reply(self):
        """
        Get the reply of the send_command sequence.
        :return:
        """
        return self.usb.read_reply()

    def send_packet(self, packet):
        """
        Send a packet of 0xC00 size containing bulk list commands.

        :param packet:
        :return:
        """
        # Preserved, but mostly unneeded.
        self.send_command(WritePort, 0x0100)
        self.send_command(GetVersion, 0x0100)
        self.send_command(ResetList)  # only this is needed.
        self.send_command(GetPositionXY)
        if self.channel:
            self.channel(packet)
        self.usb.write_block(packet)
        self.send_command(SetEndOfList)
        self._wait_for_status_bits(query=ReadPort, wait_high=0x20)
        self.send_command(ExecuteList)

    def open(self):
        try:
            response = self.usb.connect()
        except IndexError:
            return False
        if response:
            self._send_canned_sequence(INIT_BLOB_SEQUENCE)
            # We sacrifice this time at the altar of the Unknown Race Condition.
            time.sleep(0.1)
            self.connected = True
            return True
        return False

    def close(self):
        self._send_canned_sequence(QUIT_BLOB_SEQUENCE)
        self.usb.disconnect()
        self.connected = False

    def _wait_for_status_bits(self, query, wait_high, wait_low=0):
        """
        Waits until the laser's status meets the wait high and low requirements.
        """
        count = 0
        state = None
        while state is None or (state & wait_low) or not (state & wait_high):
            state = self.send_command(query)
            count += 1
            # Might want to add a delay I guess
            time.sleep(0.06)
        return count

    def _send_canned_sequence(self, sequence):
        if self.channel:
            self.channel("Sending Canned Sequence...")
        for n, (direction, endpoint, data) in enumerate(sequence):
            if direction:  # Read
                reply = self.usb.canned_read(endpoint, len(data), 1000)
                if self.channel:
                    if bytes(reply) != bytes(data):
                        self.channel(" REFR:", " ".join(["%02X" % x for x in data]))
                        self.channel(
                            "      ",
                            " ".join(
                                ["||" if x == y else "XX" for x, y in zip(data, reply)]
                            ),
                        )
                        self.channel("  GOT:", " ".join(["%02X" % x for x in reply]))
                        self.channel("LASER:", " ".join(["%02X" % x for x in reply]))
            else:
                if self.channel:
                    self.channel(" HOST:", " ".join(["%02X" % x for x in data]))
                self.usb.canned_write(endpoint, data, 1000)
