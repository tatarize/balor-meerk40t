import time

from balor.GalvoUsb import GalvoUsb
from balor.GalvoMock import GalvoMock

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
ENABLEZ2 = 0x39
SETZDATA = 0x3B
SetSPISimmerCurrent = 0x3C
SetFpkParam = 0x62  # Probably "first pulse killer" = fpk

# These are used during the Open and Close procedures. In the interest of rocking the boat as little as possible they
# are preserved. These should be replaced.
from .BJJCZ_LMCV4_FIBER_M_blobs import init as INIT_BLOB_SEQUENCE
from .BJJCZ_LMCV4_FIBER_M_blobs import quit as QUIT_BLOB_SEQUENCE


class GalvoConnection:
    """
    This is a much more meerk40t friendly version of BJJCZ.

    The connection code reports to higher level code about the connection state and slices and organizes specific data
    structures. It should also allow accesses to the various commands permitted to the laser.
    """

    def __init__(self, service):
        self.service = service
        self.channel = service.channel("galvo-connect")
        if self.service.setting(bool, "mock", False):
            self.usb = GalvoMock(service.channel("galvo-usb"))
        else:
            self.usb = GalvoUsb(service.channel("galvo-usb"))
        self.connected = False


    def send_data(self, data):
        """
        Send sliced packets

        :param data:
        :return:
        """

        self.send_command(WritePort)
        self.send_command(ResetList)
        self._wait_for_status_bits(query=GetVersion, wait_high=0x20)
        while len(data) >= 0xC00:
            packet = data[:0xC00]
            data = data[0xC00:]
            self._send_packet(packet)
        self.send_command(SetEndOfList)
        self._wait_for_status_bits(query=ReadPort, wait_high=0x20)
        self.send_command(ExecuteList)
        # if you want this to block until the laser is done, uncomment next line
        # self._wait_for_status_bits(query=GetVersion, wait_high=0x20, wait_low=0x04)

    def _send_packet(self, packet):
        """
        Send a packet of 0xC00 size containing bulk list commands.

        :param packet:
        :return:
        """
        if self.channel:
            self.channel(packet)
        self.usb.write_block(packet)
        self._wait_for_status_bits(query=GetVersion, wait_high=0x20)

    def open(self):
        """
        Opens connection to laser.
        :return:
        """
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
        """
        Closes connection to laser
        :return:
        """
        self._send_canned_sequence(QUIT_BLOB_SEQUENCE)
        self.usb.disconnect()
        self.connected = False

    def _wait_for_status_bits(self, query, wait_high, wait_low=0):
        """
        Waits until the laser's status meets the wait high and low requirements.
        """
        count = 0
        state = None
        while True:
            state = self.send_command(query)
            state = state[6]
            count += 1
            # print ('wait %02X %02x | %02X'%(wait_high, wait_low, state), state&wait_low, state&wait_high, count)
            if state is None:
                pass  # This is an error
            # This means we are _done_, not that we need to continue...
            if not (state & wait_low) and (state & wait_high):
                return count
            # Might want to add a delay I guess
            time.sleep(0.06)

    def _send_canned_sequence(self, sequence):
        """
        Residual dinosaur code. This should be replaced with actual function calls that set the correct values.
        Only init and quit are still used.

        :param sequence:
        :return:
        """
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


    def DisableLaser(self):
        """
        No parameters.
        :return:
        """
        return self.send_command(DisableLaser)

    def EnableLaser(self):
        """
        No parameters.
        :return:
        """
        return self.send_command(EnableLaser)

    def ExecuteList(self):
        """
        No parameters.
        :return: value response
        """
        return self.send_command(ExecuteList)

    def SetPwmPulseWidth(self, s1: int, value: int):
        """
        2 Param: Stack, Value
        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(SetPwmPulseWidth, s1, value)

    def GetVersion(self):
        """
        No set parameters but 1 is always sent.
        :return: value response
        """
        return self.send_command(GetVersion, 1)

    def Unknown0x0700(self):
        """
        While the 0x07 command was only seen for GetVersion, the value 1 is always the first parameter.
        :return:  value response
        """
        return self.send_command(GetVersion, 0)

    def GetSerialNo(self):
        """
        No parameters

        Reply is presumably a serial number.

        :return: value response
        """
        return self.send_command(GetSerialNo)

    def GetListStatus(self):
        """
        No parameters
        :return:  value response
        """
        return self.send_command(GetListStatus)

    def GetPositionXY(self):
        """
        No parameters

        The reply to this is the x, y coords and should be parsed.
        :return: value response
        """
        return self.send_command(GetPositionXY)

    def GotoXY(self, x, y):
        """
        Move to X Y location

        :param x:
        :param y:
        :return: value response
        """
        return self.send_command(GotoXY, int(x), int(y))

    def LaserSignalOff(self):
        """
        No parameters
        :return: value response
        """
        return self.send_command(LaserSignalOff)

    def LaserSignalOn(self):
        """
        No parameters
        :return: value response
        """
        return self.send_command(LaserSignalOn)

    def ResetList(self):
        """
        No parameters.
        :return: value response
        """
        return self.send_command(ResetList)

    def RestartList(self):
        """
        No parameters.
        :return: value response
        """
        return self.send_command(RestartList)

    def WriteCorTable(self, p1: bool, table=None):
        """
        This function would govern the interactions with the cor table command including sending the 0x10 command sends
        for the entire table.
        :param p1:
        :param table:
        :return: value response
        """
        return self.send_command(WriteCorTable, int(p1))

    def SetControlMode(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(SetControlMode, int(s1), int(value))

    def SetDelayMode(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(SetDelayMode, int(s1), int(value))

    def SetMaxPolyDelay(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(SetMaxPolyDelay, int(s1), int(value))

    def SetEndOfList(self):
        """
        No parameters
        :return: value response
        """
        return self.send_command(SetEndOfList)

    def SetFirstPulseKiller(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(SetFirstPulseKiller, s1, value)

    def SetLaserMode(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(SetLaserMode, s1, value)

    def SetTiming(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(SetTiming, s1, value)

    def SetStandby(self, v1: int, v2: int, v3: int, value: int):
        """
        4 parameters
        variable, variable, variable, value
        :param v1:
        :param v2:
        :param v3:
        :param value:
        :return: value response
        """
        return self.send_command(SetStandby, v1, v2, v3, value)

    def SetPwmHalfPeriod(self, s1: int, value: int):
        """
        2 parameters
        stack, value

        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(SetPwmHalfPeriod, s1, value)

    def StopExecute(self):
        """
        No parameters.

        :return: value response
        """
        return self.send_command(StopExecute)

    def StopList(self):
        """
        No parameters

        :return: value response
        """
        return self.send_command(StopList)

    def WritePort(self, v1: int = 0, s1: int = 0, value: int = 0):
        """
        3 parameters.
        variable, stack, value

        :param v1:
        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(WritePort, v1, s1, value)

    def WriteAnalogPort1(self, s1: int, value: int):
        """
        2 parameters.
        stack, value

        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(WriteAnalogPort1, s1, value)

    def WriteAnalogPort2(self, s1: int, value: int):
        """
        3 parameters.
        0, stack, value

        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(WriteAnalogPort2, 0, s1, value)

    def WriteAnalogPortX(self, v1: int, s1: int, value: int):
        """
        3 parameters.
        variable, stack, value

        :param v1:
        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(WriteAnalogPortX, v1, s1, value)

    def ReadPort(self):
        """
        No parameters

        :return: Status Information
        """
        return self.send_command(ReadPort)

    def SetAxisMotionParam(self, v1: int, s1: int, value: int):
        """
        3 parameters.
        variable, stack, value

        :return: value response
        """
        return self.send_command(SetAxisMotionParam, v1, s1, value)

    def SetAxisOriginParam(self, v1: int, s1: int, value: int):
        """
        3 parameters.
        variable, stack, value

        :return: value response
        """
        return self.send_command(SetAxisOriginParam, v1, s1, value)

    def AxisGoOrigin(self, v0: int):
        """
        1 parameter
        variable

        :param v0:
        :return: value response
        """
        return self.send_command(AxisGoOrigin, v0)

    def MoveAxisTo(self, axis, coord):
        """
        This typically accepted 1 32 bit int and used bits 1:8 and then 16:24 as parameters.

        :param axis: axis being moved
        :param coord: coordinate being matched
        :return: value response
        """
        return self.send_command(MoveAxisTo, axis, coord)

    def GetAxisPos(self, s1: int, value: int):
        """
        2 parameters

        stack, value

        :param s1:
        :param value:
        :return: axis position?
        """
        return self.send_command(GetAxisPos, s1, value)

    def GetFlyWaitCount(self, b1: bool):
        """
        1 parameter
        bool

        :param b1:
        :return: flywaitcount?
        """
        return self.send_command(GetFlyWaitCount, int(b1))

    def GetMarkCount(self, p1: bool):
        """
        1 parameter
        bool

        :param p1:
        :return: markcount?
        """
        return self.send_command(GetMarkCount, int(p1))

    def SetFpkParam2(self, v1, v2, v3, s1):
        """
        4 parameters
        variable, variable, variable stack

        :param v1:
        :param v2:
        :param v3:
        :param s1:
        :return:  value response
        """
        return self.send_command(SetFpkParam2, v1, v2, v3, s1)

    def IPG_OpemMO(self, s1: int, value: int):
        """
        2 parameters
        stack, value

        :param s1:
        :param value:
        :return: value response
        """
        return self.send_command(IPG_OpemMO, s1, value)

    def IPG_GETStMO_AP(self):
        """
        No parameters

        :return: value response
        """
        return self.send_command(IPG_GETStMO_AP)

    def ENABLEZ(self):
        """
        No parameters

        :return: value response
        """
        return self.send_command(ENABLEZ)

    def ENABLEZ2(self):
        """
        No parameters

        Alternate command. if unknown==0

        :return: value response
        """
        return self.send_command(ENABLEZ2)

    def SETZDATA(self, v1, s1, v2):
        """
        3 parameters

        variable, stack, variable

        :param v1:
        :param s1:
        :param v2:
        :return: value response
        """
        return self.send_command(SETZDATA, v1, s1, v2)

    def SetSPISimmerCurrent(self, v1, s1):
        """
        2 parameters
        variable, stack

        :param v1:
        :param s1:
        :return: value response
        """
        return self.send_command(SetSPISimmerCurrent, v1, s1)

    def SetFpkParam(self, v1, v2, v3, s1):
        """
        Probably "first pulse killer" = fpk
        4 parameters
        variable, variable, variable, stack

        :param v1:
        :param v2:
        :param v3:
        :param s1:
        :return: value response
        """
        return self.send_command(SetFpkParam, v1, v2, v3, s1)

    def send_command(
        self,
        command_code,
        parameter=0x0000,
        parameter2=0x0000,
        parameter3=0x0000,
        parameter4=0x0000,
        parameter5=0x0000
    ):
        """
        Send command code, and five additional 16 bit values.

        :param command_code:
        :param parameter:
        :param parameter2:
        :param parameter3:
        :param parameter4:
        :param parameter5:
        :return:
        """
        query = bytearray([0] * 12)
        query[0] = command_code & 0xFF
        query[1] = command_code >> 8
        query[2] = parameter & 0xFF
        query[3] = (parameter & 0xFF00) >> 8
        query[4] = parameter2 & 0xFF
        query[5] = (parameter2 & 0xFF00) >> 8

        query[6] = parameter3 & 0xFF
        query[7] = (parameter3 & 0xFF00) >> 8
        query[8] = parameter4 & 0xFF
        query[9] = (parameter4 & 0xFF00) >> 8
        query[10] = parameter5 & 0xFF
        query[11] = (parameter5 & 0xFF00) >> 8
        self.usb.write_command(query)
        return self._get_reply()

    def _get_reply(self):
        """
        Get the reply of the send_command sequence.
        :return: reply of usb_read_reply
        """
        return self.usb.read_reply()
