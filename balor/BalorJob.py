import math
import numpy as np

import sys


class Simulation:
    """
    This class simulates a job. Fed the job it will determine the strokes from within the job. Calling draw() as given
    to the Simulator
    """

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
                int(round((cm / 100.0) * self.laser_power)),
            )
        self.draw.line(
            (self.x * self.scale, self.y * self.scale, self.scale * x, self.scale * y),
            fill=color,
            width=1,
        )
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
    name = "UNDEFINED OPERATION"
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
                    print(
                        "Parameter overflow", self.name, self.opcode, p, file=sys.stderr
                    )
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
                print(
                    "Parameter overflow %x" % param,
                    self.name,
                    self.opcode,
                    self.params,
                    file=sys.stderr,
                )
            i += 2
        return blank

    def validate(self):
        for n, param in enumerate(self.params):
            if param > 0xFFFF:
                raise ValueError(
                    "A parameter can't be greater than 0xFFFF (Op %s, Param %d = 0x%04X"
                    % (self.name, n, param)
                )

    def text_decode(self):
        return self.name

    def text_debug(self, show_tracking=False):
        return (
            ("%s:%03X" % (self.tracking, self.position) if show_tracking else "")
            + " | %04X | " % self.opcode
            + " ".join(["%04X" % x for x in self.params])
            + " | "
            + self.text_decode()
        )

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


class OpJumpTo(Operation):
    name = "TRAVEL (y, x, angle, distance)"
    opcode = 0x8001
    x = 1
    y = 0
    d = 3

    def text_decode(self):
        xs, ys, unit = self.job.get_scale()
        x = "%.3f %s" % (self.params[1] * xs, unit) if unit else "%d" % self.params[1]
        y = "%.3f %s" % (self.params[0] * ys, unit) if unit else "%d" % self.params[0]
        d = "%.3f %s" % (self.params[3] * xs, unit) if unit else "%d" % self.params[3]
        return "Travel to x=%s y=%s angle=%04X dist=%s" % (x, y, self.params[2], d)

    def simulate(self, sim):
        sim.travel(self.params[self.x], self.params[self.y])


class OpMarkEndDelay(Operation):
    name = "WAIT (time)"
    opcode = 0x8004

    def text_decode(self):
        return "Wait %d microseconds" % (self.params[0] * 10)


class OpMarkTo(Operation):
    name = "CUT (y, x, angle, distance)"
    opcode = 0x8005
    x = 1
    y = 0
    d = 3
    a = 2

    def text_decode(self):
        xs, ys, unit = self.job.get_scale()
        x = "%.3f %s" % (self.params[1] * xs, unit) if unit else "%d" % self.params[1]
        y = "%.3f %s" % (self.params[0] * ys, unit) if unit else "%d" % self.params[0]
        d = "%.3f %s" % (self.params[3] * xs, unit) if unit else "%d" % self.params[3]
        return "Cut to x=%s y=%s angle=%04X dist=%s" % (x, y, self.params[2], d)

    def simulate(self, sim):
        sim.cut(self.params[self.x], self.params[self.y])


class OpJumpSpeed(Operation):
    name = "SET TRAVEL SPEED (speed)"
    opcode = 0x8006

    def text_decode(self):
        return "Set travel speed = %.2f mm/s" % (self.params[0] * 1.9656)


class OpLaserOnDelay(Operation):
    name = "SET ON TIME COMPENSATION (time)"
    opcode = 0x8007

    def text_decode(self):
        return "Set on time compensation = %d us" % (self.params[0])


class OpLaserOffDelay(Operation):
    name = "SET OFF TIME COMPENSATION (time)"
    opcode = 0x8008

    def text_decode(self):
        return "Set off time compensation = %d us" % (self.params[0])


# TODO: 0x800A Mark Frequency (use differs by machine)
# TODO: 0x800B Mark Pulse Width (use differs by machine


class OpMarkSpeed(Operation):
    name = "SET CUTTING SPEED (speed)"
    opcode = 0x800C

    def text_decode(self):
        return "Set cut speed = %.2f mm/s" % (self.params[0] * 1.9656)

    def simulate(self, sim):
        sim.cut_speed = self.params[0] * 1.9656


class OpAltTravel(Operation):
    """
    This command was listed as Mystery Operation it is only called in listJumpTo as 0x8001 is called.
    """

    name = "Alternate travel (0x800D)"
    opcode = 0x800D

    def text_decode(self):
        return "Alternate travel operation 0x800D, param=%d" % self.params[0]

    def simulate(self, sim):
        sim.travel(self.params[self.x], self.params[self.y])

    def text_decode(self):
        xs, ys, unit = self.job.get_scale()
        x = "%.3f %s" % (self.params[1] * xs, unit) if unit else "%d" % self.params[1]
        y = "%.3f %s" % (self.params[0] * ys, unit) if unit else "%d" % self.params[0]
        d = "%.3f %s" % (self.params[3] * xs, unit) if unit else "%d" % self.params[3]
        return "Alt travel to x=%s y=%s angle=%04X dist=%s" % (x, y, self.params[2], d)


class OpPolygonDelay(Operation):
    name = "POLYGON DELAY"
    opcode = 0x800F

    def text_decode(self):
        return "Set polygon delay, param=%d" % self.params[0]


# TODO: 0x8011 listWritrPort


class MarkPowerRatio(Operation):
    name = "SET LASER POWER (power)"
    opcode = 0x8012

    def text_decode(self):
        return "Set laser power = %.1f%%" % (self.params[0] / 40.960)

    def simulate(self, sim):
        sim.laser_power = self.params[0] / 40.960


# TODO: 0x801A FlyEnable


class OpSetQSwitchPeriod(Operation):
    """
    Only called for some machines, from Mark Frequency
    """

    name = "SET Q SWITCH PERIOD (period)"
    opcode = 0x801B

    def text_decode(self):
        return "Set Q-switch period = %d ns (%.0f kHz)" % (
            self.params[0] * 50,
            1.0 / (1000 * self.params[0] * 50e-9),
        )

    def simulate(self, sim):
        sim.q_switch_period = self.params[0] * 50.0


# TODO: 0x801C Direct Laser Switch

# TODO: 0x801D Fly Delay

# TODO: 0x801E SetCo2FPK

# TODO: 0x801F Fly Wait Input


class OpLaserControl(Operation):
    name = "LASER CONTROL (on)"
    opcode = 0x8021

    def text_decode(self):
        return "Laser control - turn " + ("ON" if self.params[0] else "OFF")

    def simulate(self, sim):
        sim.laser_on = bool(self.params[0])


# TODO: 0x8023 CHANGE MARK COUNT

# TODO: 0x8024: SetWeldPowerWave

# TODO: 0x8025 Enable Weld Power Wave

# TODO: 0x8026 IPGYLPMPulseWidth, SetConfigExtend

# TODO: 0x8028 Fly Encoder Count

# TODO: 0x8029: SetDaZWord


class OpReadyMark(Operation):
    name = "BEGIN JOB"
    opcode = 0x8051

    def text_decode(self):
        return "Begin job"


all_operations = [
    OpReadyMark,
    OpLaserControl,
    OpSetQSwitchPeriod,
    OpMarkTo,
    MarkPowerRatio,
    OpPolygonDelay,
    OpAltTravel,
    OpMarkSpeed,
    OpLaserOffDelay,
    OpLaserOnDelay,
    OpJumpSpeed,
    OpMarkEndDelay,
    OpEndOfList,
    OpJumpTo,
]

operations_by_opcode = {OpClass.opcode: OpClass for OpClass in all_operations}


def OperationFactory(code, tracking=None, position=0):
    opcode = code[0] | (code[1] << 8)
    OpClass = operations_by_opcode.get(opcode, Operation)
    return OpClass(from_binary=code, tracking=tracking, position=position)

class Job:
    def __init__(self, machine=None):
        self.machine = machine
        self.x_scale = 1
        self.y_scale = 1
        self.scale_unit = ""
        self.operations = []

    def get_scale(self):
        return self.x_scale, self.y_scale, self.scale_unit

    def clear_operations(self):
        self.operations = []

    def get_position(self):
        return len(self.operations) - 1

    def duplicate(self, begin, end, repeats=1):
        for _ in range(repeats):
            self.operations.extend(self.operations[begin:end])

    def __iter__(self):
        return iter(self.operations)

    def add_light_prefix(self, travel_speed):
        self.extend(
            [
                OpReadyMark(),
                OpJumpSpeed(travel_speed),
                # OpMystery0D(0x0008)
            ]
        )

    def line(self, x0, y0, x1, y1, seg_size=5, Op=OpMarkTo):
        length = ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5
        segs = max(2, int(round(length / seg_size)))
        #print ("**", x0, y0, x1, y1, length, segs, file=sys.stderr)

        xs = np.linspace(x0, x1, segs)
        ys = np.linspace(y0, y1, segs)

        for n in range(segs):
            #print ("*", xs[n], ys[n], self.cal.interpolate(xs[n], ys[n]), file=sys.stderr)
            self.append(Op(*self.cal.interpolate(xs[n], ys[n])))

    def change_settings(self, q_switch_period, laser_power, cut_speed):
        self.extend(
            [
                OpSetQSwitchPeriod(q_switch_period),
                MarkPowerRatio(laser_power),
                OpMarkSpeed(cut_speed),
                # OpMystery0D(0x0008),
            ]
        )

    # self.settings[color] = (q_switch_period, laser_power, cut_speed, hatch_angle,
    #                hatch_spacing, hatch_pattern, repeats)

    def add_mark_prefix(self, travel_speed, q_switch_period, laser_power, cut_speed):
        self.extend(
            [
                OpReadyMark(),
                OpSetQSwitchPeriod(q_switch_period),
                MarkPowerRatio(laser_power),
                OpJumpSpeed(travel_speed),
                OpMarkSpeed(cut_speed),
                OpLaserOnDelay(0x0064, 0x8000),
                OpLaserOffDelay(0x0064),
                OpPolygonDelay(0x000A),
                # OpMystery0D(0x0008),
            ]
        )

    def laser_control(self, on):
        if on:
            self.extend(
                [
                    OpLaserControl(0x0001),
                    OpMarkEndDelay(0x0320),
                ]
            )
        else:
            self.extend(
                [
                    OpMarkEndDelay(0x001E),
                    OpLaserControl(0x0000),
                ]
            )

    def plot(self, draw, resolution=2048):
        sim = Simulation(self, self.machine, draw, resolution)
        for op in self.operations:
            sim.simulate(op)

    def set_scale(self, x=1, y=1, unit=""):
        self.x_scale = x
        self.y_scale = y
        self.scale_unit = unit

    def append(self, x):
        x.bind(self)
        self.operations.append(x)

    def extend(self, x):
        for op in x:
            op.bind(self)
        self.operations.extend(x)

    def get_operations(self):
        return self.operations

    def add_packet(self, data, tracking=None):
        # Parse MSBF data and add it as operations
        i = 0
        while i < len(data):
            command = data[i : i + 12]
            op = OperationFactory(command, tracking=tracking, position=i)
            op.bind(self)
            self.operations.append(op)
            i += 12

    def serialize(self):
        size = 256 * int(round(math.ceil(len(self.operations) / 256.0)))
        buf = bytearray(([0x02, 0x80] + [0] * 10) * size)  # Create buffer full of NOP
        i = 0
        for op in self.operations:
            buf[i : i + 12] = op.serialize()
            i += 12
        return buf

    def calculate_distances(self):
        last_xy = 0x8000, 0x8000
        for op in self.operations:
            if op.has_d():
                nx, ny = op.get_xy()
                x, y = last_xy
                op.set_d(int(((nx - x) ** 2 + (ny - y) ** 2) ** 0.5))

            if op.has_xy():
                last_xy = op.get_xy()

    def serialize_to_file(self, file):
        with open(file, "wb") as out_file:
            out_file.write(self.serialize())


def JobFactory(machine_name):
    # This is currently just a stub since we don't support any
    # incompatible machines
    return Job(machine=machine_name)
