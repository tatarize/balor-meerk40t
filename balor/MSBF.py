import math

import numpy as np

import sys

#TODO: Angle for Travel and Cut is really high bits of distance.


class Simulation:
    def __init__(self, job, machine, draw, resolution):
        self.job = job
        self.machine = machine
        self.draw = draw
        self.resolution = resolution
        self.scale = float(self.resolution) / 0x10000
        self.segcount = 0
        self.laser_power = 0
        self.laser_on = False
        self.q_switch_period = 0
        self.cut_speed = 0
        self.x = 0x8000
        self.y = 0x8000

    def simulate(self, op):
        op.simulate(self)

    def cut(self, x, y):
        cm = 128 if self.segcount % 2 else 255
        self.segcount += 1

        if not self.laser_on:
            color = (cm, 0, 0)
        else:
            color = (
                int(cm * ((self.q_switch_period - 5000) / 50000.0)),
                int(round(cm * (2000 - self.cut_speed) / 2000.0)),
                # cm,)
                int(round((cm / 100.0) * self.laser_power)))
        self.draw.line((self.x * self.scale, self.y * self.scale,
                        self.scale * x, self.scale * y),
                       fill=color,
                       width=1)
        self.x, self.y = x, y

    def travel(self, x, y):
        cm = 128 if self.segcount % 2 else 255
        self.segcount += 1
        # self.draw.line((self.x*self.scale, self.y*self.scale,
        #    self.scale*x, self.scale*y),
        #    fill=(cm//2,cm//2,cm//2, 64), width=1)
        self.x, self.y = x, y


class Operation:
    opcode = 0x8000
    name = 'UNDEFINED OPERATION'
    x = None  # know which is x and which is y,
    y = None  # for adjustment purposes by correction filters
    d = None
    a = None
    job = None

    def bind(self, job):
        self.job = job

    def simulate(self, sim):
        pass

    def __init__(self, *params, from_binary=None, tracking=None, position=0):
        self.tracking = tracking
        self.position = position
        self.params = [0] * 5
        if from_binary is None:
            for n, p in enumerate(params):
                self.params[n] = p
                if p > 0xFFFF:
                    print("Parameter overflow", self.name, self.opcode, p, file=sys.stderr)
                    raise ValueError
        else:
            self.opcode = from_binary[0] | (from_binary[1] << 8)
            i = 2
            while i < len(from_binary):
                self.params[i // 2 - 1] = from_binary[i] | (from_binary[i + 1] << 8)
                i += 2

        self.validate()

    def serialize(self):
        blank = bytearray([0] * 12)
        blank[0] = self.opcode & 0xFF
        blank[1] = self.opcode >> 8
        i = 2
        for param in self.params:
            blank[i] = param & 0xFF
            try:
                blank[i + 1] = param >> 8
            except ValueError:
                print("Parameter overflow %x" % param, self.name, self.opcode, self.params, file=sys.stderr)
            i += 2
        return blank

    def validate(self):
        for n, param in enumerate(self.params):
            if param > 0xFFFF: raise ValueError(
                "A parameter can't be greater than 0xFFFF (Op %s, Param %d = 0x%04X" % (self.name,
                                                                                        n, param))

    def text_decode(self):
        return self.name

    def text_debug(self, show_tracking=False):
        return (('%s:%03X' % (self.tracking, self.position) if show_tracking else '')
                + ' | %04X | ' % self.opcode
                + ' '.join(['%04X' % x for x in self.params])
                + ' | ' + self.text_decode())

    def has_xy(self):
        return self.x is not None and self.y is not None

    def has_d(self):
        return self.d is not None

    def set_xy(self, nxy):
        self.params[self.x] = nxy[0]
        self.params[self.y] = nxy[1]
        self.validate()

    def set_d(self, d):
        self.params[self.d] = d
        self.validate()

    def set_a(self, a):
        self.params[self.a] = a
        self.validate()

    def get_xy(self):
        return self.params[self.x], self.params[self.y]


class OpEndOfList(Operation):
    name = "NO OPERATION ()"
    opcode = 0x8002

    def text_decode(self):
        return "No operation"


class OpTravel(Operation):
    name = "TRAVEL (y, x, angle, distance)"
    opcode = 0x8001
    x = 1
    y = 0
    d = 3

    def text_decode(self):
        xs, ys, unit = self.job.get_scale()
        x = '%.3f %s' % (self.params[1] * xs, unit) if unit else '%d' % self.params[1]
        y = '%.3f %s' % (self.params[0] * ys, unit) if unit else '%d' % self.params[0]
        d = '%.3f %s' % (self.params[3] * xs, unit) if unit else '%d' % self.params[3]
        return "Travel to x=%s y=%s angle=%04X dist=%s" % (
            x, y, self.params[2],
            d)

    def simulate(self, sim):
        sim.travel(self.params[self.x], self.params[self.y])


class OpSetMarkEndDelay(Operation):
    name = "WAIT (time)"
    opcode = 0x8004

    def text_decode(self):
        return "Wait %d microseconds" % (self.params[0] * 10)


class OpCut(Operation):
    name = "CUT (y, x, angle, distance)"
    opcode = 0x8005
    x = 1
    y = 0
    d = 3
    a = 2

    def text_decode(self):
        xs, ys, unit = self.job.get_scale()
        x = '%.3f %s' % (self.params[1] * xs, unit) if unit else '%d' % self.params[1]
        y = '%.3f %s' % (self.params[0] * ys, unit) if unit else '%d' % self.params[0]
        d = '%.3f %s' % (self.params[3] * xs, unit) if unit else '%d' % self.params[3]
        return "Cut to x=%s y=%s angle=%04X dist=%s" % (
            x, y, self.params[2],
            d)

    def simulate(self, sim):
        sim.cut(self.params[self.x], self.params[self.y])


class OpSetTravelSpeed(Operation):
    name = "SET TRAVEL SPEED (speed)"
    opcode = 0x8006

    def text_decode(self):
        return "Set travel speed = %.2f mm/s" % (self.params[0] * 1.9656)


class OpSetLaserOnDelay(Operation):
    name = "SET ON TIME COMPENSATION (time)"
    opcode = 0x8007

    def text_decode(self):
        return "Set on time compensation = %d us" % (self.params[0])


class OpSetLaserOffDelay(Operation):
    name = "SET OFF TIME COMPENSATION (time)"
    opcode = 0x8008

    def text_decode(self):
        return "Set off time compensation = %d us" % (self.params[0])


class OpSetCutSpeed(Operation):
    name = "SET CUTTING SPEED (speed)"
    opcode = 0x800C

    def text_decode(self):
        return "Set cut speed = %.2f mm/s" % (self.params[0] * 1.9656)

    def simulate(self, sim):
        sim.cut_speed = self.params[0] * 1.9656


class OpJumpCalibration(Operation):
    name = "Alternate travel (0x800D)"
    opcode = 0x800D

    def text_decode(self):
        return "Alternate travel operation 0x800D, param=%d" % self.params[0]

    def simulate(self, sim):
        sim.travel(self.params[self.x], self.params[self.y])

    def text_decode(self):
        xs, ys, unit = self.job.get_scale()
        x = '%.3f %s' % (self.params[1] * xs, unit) if unit else '%d' % self.params[1]
        y = '%.3f %s' % (self.params[0] * ys, unit) if unit else '%d' % self.params[0]
        d = '%.3f %s' % (self.params[3] * xs, unit) if unit else '%d' % self.params[3]
        return "Alt travel to x=%s y=%s angle=%04X dist=%s" % (
            x, y, self.params[2],
            d)


class OpSetPolygonDelay(Operation):
    name = "POLYGON DELAY"
    opcode = 0x800F

    def text_decode(self):
        return "Set polygon delay, param=%d" % self.params[0]


class OpMarkPowerRatio(Operation):
    name = "SET LASER POWER (power)"
    opcode = 0x8012

    def text_decode(self):
        return "Set laser power = %.1f%%" % (self.params[0] / 40.960)

    def simulate(self, sim):
        sim.laser_power = self.params[0] / 40.960


class OpSetQSwitchPeriod(Operation):
    name = "SET Q SWITCH PERIOD (period)"
    opcode = 0x801B

    def text_decode(self):
        return "Set Q-switch period = %d ns (%.0f kHz)" % (
            self.params[0] * 50,
            1.0 / (1000 * self.params[0] * 50e-9))

    def simulate(self, sim):
        sim.q_switch_period = self.params[0] * 50.0


class OpLaserControl(Operation):
    name = "LASER CONTROL (on)"
    opcode = 0x8021

    def text_decode(self):
        return "Laser control - turn " + ('ON' if self.params[0] else 'OFF')

    def simulate(self, sim):
        sim.laser_on = bool(self.params[0])


class OpReadyMark(Operation):
    name = "BEGIN JOB"
    opcode = 0x8051

    def text_decode(self):
        return "Begin job"


class OpFlyEnable(Operation):

    opcode = 0x801A
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpMarkFrequency(Operation):
    opcode = 0x800A
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpMarkPulseWidth(Operation):

    opcode = 0x800B
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpWritePort(Operation):
    opcode = 0x8011
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpDirectLaserSwitch(Operation):
    opcode = 0x801C
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpFlyDelay(Operation):
    opcode = 0x801D
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpSetCo2FPK(Operation):
    opcode = 0x801E
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpFlyWaitInput(Operation):

    opcode = 0x801F
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpChangeMarkCount(Operation):
    opcode = 0x8023
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpSetWeldPowerWave(Operation):

    opcode = 0x8024
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpEnableWeldPowerWave(Operation):

    opcode = 0x8025
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpIPGYLPMPulseWidth(Operation):
    opcode = 0x8026
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpFlyEncoderCount(Operation):

    opcode = 0x8028
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


class OpSetDaZWord(Operation):

    opcode = 0x8029
    # name = "Name"
    name = str(opcode)

    def text_decode(self):
        return "sets command {opcode}={p1}, {p2}, {p3}, {p4}".format(
            opcode=self.opcode,
            p1=self.params[1],
            p2=self.params[1],
            p3=self.params[1],
            p4=self.params[1]
        )


all_operations = [OpReadyMark, OpLaserControl, OpSetQSwitchPeriod, OpCut,
                  OpMarkPowerRatio, OpSetPolygonDelay, OpJumpCalibration, OpSetCutSpeed,
                  OpSetLaserOffDelay, OpSetLaserOnDelay, OpSetTravelSpeed,
                  OpSetMarkEndDelay, OpEndOfList, OpTravel, OpMarkFrequency, OpMarkPulseWidth,
                  OpWritePort, OpDirectLaserSwitch, OpFlyDelay, OpSetCo2FPK, OpFlyWaitInput,
                  OpChangeMarkCount, OpSetWeldPowerWave, OpEnableWeldPowerWave, OpIPGYLPMPulseWidth,
                  OpFlyEncoderCount, OpSetDaZWord
                  ]

operations_by_opcode = {OpClass.opcode: OpClass for OpClass in all_operations}


def OperationFactory(code, tracking=None, position=0):
    opcode = code[0] | (code[1] << 8)
    OpClass = operations_by_opcode.get(opcode, Operation)
    return OpClass(from_binary=code, tracking=tracking, position=position)


class CommandList:
    def __init__(self, machine=None, x=0x8000, y=0x8000, cal=None):
        self.machine = machine
        self.cal = cal
        self.operations = []
        self._last_x = x
        self._last_y = y
        self._start_x = x
        self._start_y = y
        self._ready = False
        self._cut_speed = None
        self._travel_speed = None
        self._frequency = None
        self._power = None
        self._jump_calibration = None
        self._laser_control = None
        self._laser_on_delay = None
        self._laser_off_delay = None
        self._poly_delay = None
        self._mark_end_delay = None
        self._light = None

    @property
    def position(self):
        return len(self.operations) - 1

    def duplicate(self, begin, end, repeats=1):
        for _ in range(repeats):
            self.operations.extend(self.operations[begin:end])

    def append(self, x):
        x.bind(self)
        self.operations.append(x)

    def extend(self, x):
        for op in x:
            op.bind(self)
        self.operations.extend(x)

    def __iter__(self):
        return iter(self.operations)

    def __bytes__(self):
        return bytes(self.serialize())

    def serialize(self):
        """
        Performs final operations before creating bytearray.

        :return:
        """
        # Calculate distances.
        last_xy = self._start_x, self._start_y
        for op in self.operations:
            if op.has_d():
                nx, ny = op.get_xy()
                x, y = last_xy
                op.set_d(int(((nx - x) ** 2 + (ny - y) ** 2) ** 0.5))

            if op.has_xy():
                last_xy = op.get_xy()

        # Write buffer.
        size = 256 * int(round(math.ceil(len(self.operations) / 256.0)))
        buf = bytearray(([0x02, 0x80] + [0] * 10) * size)  # Create buffer full of NOP
        i = 0
        for op in self.operations:
            buf[i : i + 12] = op.serialize()
            i += 12
        return buf

    def packet_generator(self):
        """
        Performs final operations and generates packets on the fly.

        :return:
        """
        last_xy = self._start_x, self._start_y

        # Write buffer.
        buf = bytearray([0] * 0xC00)  # Create a packet.
        eol = bytes([0x02, 0x80] + [0] * 10)  # End of Line Command
        i = 0
        for op in self.operations:
            if op.has_d():
                nx, ny = op.get_xy()
                x, y = last_xy
                op.set_d(int(((nx - x) ** 2 + (ny - y) ** 2) ** 0.5))

            if op.has_xy():
                last_xy = op.get_xy()
            buf[i : i + 12] = op.serialize()
            i += 12
            if i >= 0xC00:
                i = 0
                yield buf
        while i < 0xC00:
            buf[i: i + 12] = eol
            i += 12
        yield buf

    ######################
    # GEOMETRY HELPERS
    ######################

    def draw_line(self, x0, y0, x1, y1, seg_size=5, Op=OpCut):
        length = ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5
        segs = max(2, int(round(length / seg_size)))
        # print ("**", x0, y0, x1, y1, length, segs, file=sys.stderr)

        xs = np.linspace(x0, x1, segs)
        ys = np.linspace(y0, y1, segs)

        for n in range(segs):
            # print ("*", xs[n], ys[n], self.cal.interpolate(xs[n], ys[n]), file=sys.stderr)
            self.append(Op(*self.pos(xs[n], ys[n])))

    ######################
    # UNIT CONVERSION
    ######################

    def pos(self, x, y):
        if self.cal is None:
            return x, y
        return self.cal.interpolate(x, y)

    def convert_time(self, time):
        # TODO: WEAK IMPLEMENTATION
        raise NotImplementedError("No time units")

    def convert_speed(self, speed):
        return int(round(speed / 2.0))  # units are 2mm/sec

    def convert_power(self, power):
        return int(round(power * 40.95))

    def convert_frequency(self, frequency):
        # q_switch_period
        return int(round(1.0 / (frequency * 1e3) / 50e-9))

    ######################
    # COMMAND DELEGATES
    ######################

    def ready(self):
        """
        Flag this job with ReadyMark.

        :return:
        """
        if not self._ready:
            self._ready = True
            self.append(OpReadyMark())

    def laser_control(self, control):
        """
        Enable the laser control.

        :param control:
        :return:
        """
        if self._laser_control == control:
            return
        self._laser_control = control

        # TODO: Does this order matter?
        if control:
            self.append(OpLaserControl(0x0001))
            self.set_mark_end_delay(0x0320)
        else:
            self.set_mark_end_delay(0x001E)
            self.append(OpLaserControl(0x0000))

    def set_travel_speed(self, speed):
        if self._travel_speed == speed:
            return
        self.ready()
        self._travel_speed = speed
        self.append(OpSetTravelSpeed(self.convert_speed(speed)))

    def set_cut_speed(self, speed):
        if self._cut_speed == speed:
            return
        self.ready()
        self._cut_speed = speed
        self.append(OpSetCutSpeed(self.convert_speed(speed)))

    def set_power(self, power):
        # TODO: use or conversion differs by machine
        if self._power == power:
            return
        self.ready()
        self._power = power
        self.append(OpMarkPowerRatio(self.convert_power(power)))

    def set_frequency(self, frequency):
        # TODO: use differs by machine: 0x800A Mark Frequency, 0x800B Mark Pulse Width
        if self._frequency == frequency:
            return
        self._frequency = frequency
        self.append(OpSetQSwitchPeriod(self.convert_frequency(frequency)))

    def set_light(self, on):
        # TODO: WEAK IMPLEMENTATION
        if self._light == on:
            return
        self.ready()
        # In theory WriterPort(0x100) maybe should turn the light on if it isn't on.
        # More research needed.
        pass

    def set_laser_on_delay(self, *args):
        # TODO: WEAK IMPLEMENTATION
        if self._laser_on_delay == args:
            return
        self.ready()
        self._laser_on_delay = args
        self.append(OpSetLaserOnDelay(*args))

    def set_laser_off_delay(self, delay):
        # TODO: WEAK IMPLEMENTATION
        if self._laser_off_delay == delay:
            return
        self.ready()
        self._laser_off_delay = delay
        self.append(OpSetLaserOffDelay(delay))

    def set_polygon_delay(self, delay):
        # TODO: WEAK IMPLEMENTATION
        if self._poly_delay == delay:
            return
        self.ready()
        self._poly_delay = delay
        self.append(OpSetPolygonDelay(delay))

    def set_mark_end_delay(self, delay):
        # TODO: WEAK IMPLEMENTATION
        if self._mark_end_delay == delay:
            return
        self.ready()
        self._mark_end_delay = delay
        self.append(OpSetMarkEndDelay(delay))

    def mark(self, x, y):
        """
        Mark to a new location with the laser firing.

        :param x:
        :param y:
        :return:
        """
        self.ready()
        if self._frequency is None:
            raise ValueError("Qswitch frequency must be set before a mark(x,y)")
        if self._power is None:
            raise ValueError("Laser Power must be set before a mark(x,y)")
        if self._cut_speed is None:
            raise ValueError("Mark Speed must be set before a mark(x,y)")
        if self._laser_on_delay is None:
            raise ValueError("LaserOn Delay must be set before a mark(x,y)")
        if self._laser_off_delay is None:
            raise ValueError("LaserOff Delay must be set before a mark(x,y)")
        if self._poly_delay is None:
            raise ValueError("Polygon Delay must be set before a mark(x,y)")
        self._last_x = x
        self._last_y = y
        self.append(OpCut(*self.pos(x, y)))

    def jump_calibration(self, calibration=0x0008):
        if self._jump_calibration == calibration:
            return
        self.ready()
        self._jump_calibration = calibration
        self.append(OpJumpCalibration(calibration))

    def light(self, x, y, calibration=None):
        """
        Move to a new location with light enabled.

        :param x:
        :param y:
        :param calibration:
        :return:
        """
        self.goto(x, y, light=True, calibration=calibration)

    def goto(self, x, y, light=False, calibration=None):
        """
        Move to a new location without laser or light.

        :param x:
        :param y:
        :param light:
        :param calibration:
        :return:
        """
        self.ready()
        if not self._travel_speed:
            raise ValueError("Travel speed must be set before a jumping")
        self._last_x = x
        self._last_y = y
        if light and not self._light:
            self.set_light(True)
        if calibration is not None:
            self.jump_calibration(calibration)
        self.append(OpTravel(*self.pos(x, y)))

    def init(self, x, y):
        """
        Sets the initial position. This is the position we came from to get to this set of operations. It matters for
        the time calculation to the initial goto or mark commands.

        :param x:
        :param y:
        :return:
        """
        self._last_x = x
        self._last_y = y
        self._start_x = x
        self._start_y = y

    def set_mark_settings(
        self,
        travel_speed,
        frequency,
        power,
        cut_speed,
        laser_on_delay,
        laser_off_delay,
        polygon_delay,
    ):
        self.set_frequency(frequency)
        self.set_power(power)
        self.set_travel_speed(travel_speed)
        self.set_cut_speed(cut_speed)
        self.set_laser_on_delay(laser_on_delay)
        self.set_laser_off_delay(laser_off_delay)
        self.set_polygon_delay(polygon_delay)

    ######################
    # DEBUG FUNCTIONS
    ######################

    def add_packet(self, data, tracking=None):
        """
        Parse MSBF data and add it as operations

        :param data:
        :param tracking:
        :return:
        """
        i = 0
        while i < len(data):
            command = data[i : i + 12]
            op = OperationFactory(command, tracking=tracking, position=i)
            op.bind(self)
            self.operations.append(op)
            i += 12

    def plot(self, draw, resolution=2048):
        sim = Simulation(self, self.machine, draw, resolution)
        for op in self.operations:
            sim.simulate(op)

    def serialize_to_file(self, file):
        with open(file, "wb") as out_file:
            out_file.write(self.serialize())

