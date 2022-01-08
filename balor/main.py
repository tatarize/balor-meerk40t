import os
import sys
import threading
import time

from meerk40t.core.cutcode import LaserSettings, CutCode, LineCut
from meerk40t.core.spoolers import Spooler
from meerk40t.device.lasercommandconstants import *
from meerk40t.kernel import Service
import balor
from balor.MSBF import Job
from PIL import Image, ImageDraw

from meerk40t.core.cutcode import LaserSettings, LineCut, CutCode, QuadCut, RasterCut
from meerk40t.core.elements import LaserOperation
from meerk40t.svgelements import Point, Path, SVGImage


def plugin(kernel, lifecycle):
    if lifecycle == "register":
        kernel.register("provider/device/balor", BalorDevice)
    elif lifecycle == "preboot":
        suffix = "balor"
        for d in kernel.settings.derivable(suffix):
            kernel.root(
                "service device start -p {path} {suffix}\n".format(
                    path=d, suffix=suffix
                )
            )


class BalorDevice(Service):
    def __init__(self, kernel, path, *args, **kwargs):
        Service.__init__(self, kernel, path)
        self.name = "balor"

        _ = kernel.translation

        choices = [
            {
                "attr": "bedwidth",
                "object": self,
                "default": 0xFFFF,
                "type": float,
                "label": _("Width"),
                "tip": _("Width of the laser bed."),
            },
            {
                "attr": "bedheight",
                "object": self,
                "default": 0xFFFF,
                "type": float,
                "label": _("Height"),
                "tip": _("Height of the laser bed."),
            },
            {
                "attr": "scale_x",
                "object": self,
                "default": 0.06608137,
                "type": float,
                "label": _("X Scale Factor"),
                "tip": _(
                    "Scale factor for the X-axis. This defines the ratio of mils to steps. This is usually at 1:1 steps/mils but due to functional issues it can deviate and needs to be accounted for"
                ),
            },
            {
                "attr": "scale_y",
                "object": self,
                "default": 0.06608137,
                "type": float,
                "label": _("Y Scale Factor"),
                "tip": _(
                    "Scale factor for the Y-axis. This defines the ratio of mils to steps. This is usually at 1:1 steps/mils but due to functional issues it can deviate and needs to be accounted for"
                ),
            },
        ]
        self.register_choices("bed_dim", choices)

        choices = [
            {
                "attr": "label",
                "object": self,
                "default": "balor-device",
                "type": str,
                "label": _("Label"),
                "tip": _("What is this device called."),
            },
            {
                "attr": "operation",
                "object": self,
                "default": "light",
                "type": str,
                "choices": ("light", "mark"),
                "label": _("Operation type: light or mark"),
                "tip": _("Mark or light outline"),
            },
            {
                "attr": "calfile",
                "object": self,
                "default": None,
                "type": str,
                "label": _("Calibration File"),
                "tip": _("Provide a calibration file for the machine"),
            },
            {
                "attr": "machine",
                "object": self,
                "default": "BJJCZ_LMCV4_FIBER_M",
                "type": str,
                "label": _("Machine Type"),
                "tip": _("What type of machine are we controlling?"),
            },
            {
                "attr": "travel_speed",
                "object": self,
                "default": 2000.0,
                "type": float,
                "label": _("Travel Speed"),
                "tip": _("How fast do we travel when not cutting?"),
            },
            {
                "attr": "laser_power",
                "object": self,
                "default": 50.0,
                "type": float,
                "label": _("Laser Power"),
                "tip": _("How what power level do we cut at?"),
            },
            {
                "attr": "cut_speed",
                "object": self,
                "default": 100.0,
                "type": float,
                "label": _("Cut Speed"),
                "tip": _("How fast do we cut?"),
            },
            {
                "attr": "q_switch_frequency",
                "object": self,
                "default": 30.0,
                "type": float,
                "label": _("Q Switch Frequency"),
                "tip": _("Frequency of the Q Switch (full disclosure, no clue)"),
            },
            {
                "attr": "output",
                "object": self,
                "default": None,
                "type": str,
                "label": _("Output File"),
                "tip": _("Additional save to file option for a job."),
            },
        ]
        self.register_choices("balor", choices)

        @self.console_argument("machine_type", type=str, help="machine specified")
        @self.console_command(
            "machine", help=_("Specify which machine interface to use.")
        )
        def set_machine_type(command, channel, _, machine_type, **kwargs):
            if machine_type is None:
                channel(
                    "Current machine is set to: {machine}".format(machine=self.machine)
                )
                channel(
                    "Valid machines: "
                    + ", ".join([x.__name__ for x in balor.all_known_machines])
                )
            else:
                self.machine = machine_type

        self.current_x = 0.0
        self.current_y = 0.0
        self.state = 0
        self.spooler = Spooler(self)

        self.driver = BalorDriver(self)
        self.add_service_delegate(self.driver)
        self.controller = BalorController(self)
        self.add_service_delegate(self.controller)

        self.viewbuffer = ""

        @self.console_command(
            "spool",
            help=_("spool <command>"),
            regex=True,
            input_type=(None, "plan", "device"),
            output_type="spooler",
        )
        def spool(command, channel, _, data=None, remainder=None, **kwgs):
            """
            Registers the spool command for the Balor driver.
            """
            spooler = self.spooler
            if data is not None:
                # If plan data is in data, then we copy that and move on to next step.
                spooler.jobs(data.plan)
                channel(_("Spooled Plan."))
                self.signal("plan", data.name, 6)

            if remainder is None:
                channel(_("----------"))
                channel(_("Spoolers:"))
                for d, d_name in enumerate(self.match("device", suffix=True)):
                    channel("%d: %s" % (d, d_name))
                channel(_("----------"))
                channel(_("Spooler on device %s:" % str(self.label)))
                for s, op_name in enumerate(spooler.queue):
                    channel("%d: %s" % (s, op_name))
                channel(_("----------"))

            return "spooler", spooler

        @self.console_command(
            "light",
            help=_("Turn redlight on."),
        )
        def light(command, channel, _, data=None, remainder=None, **kwgs):
            cutcode = CutCode()
            settings = LaserSettings()
            cutcode.append(LineCut(Point(7000, 7000), Point(7000, 9000), settings=settings))
            cutcode.append(LineCut(Point(7000, 9000), Point(9000, 9000), settings=settings))
            cutcode.append(LineCut(Point(9000, 9000), Point(9000, 7000), settings=settings))
            cutcode.append(LineCut(Point(9000, 7000), Point(7000, 7000), settings=settings))
            self.controller.loop_job = self.cutcode_to_job(cutcode, light=True).serialize()

        @self.console_command(
            "nolight",
            help=_("turn light off"),
            regex=True,
            input_type=(None, "elements"),
            output_type="spooler",
        )
        def light(command, channel, _, data=None, remainder=None, **kwgs):
            self.controller.loop_job = None


    def cutcode_to_job(self, queue, light=False):
        job = balor.MSBF.Job()
        job.cal = balor.Cal.Cal(self.calfile)
        travel_speed = int(round(self.travel_speed / 2.0))  # units are 2mm/sec
        cut_speed = int(round(self.cut_speed / 2.0))
        laser_power = int(round(self.laser_power * 40.95))
        q_switch_period = int(
            round(1.0 / (self.q_switch_frequency * 1e3) / 50e-9)
        )
        if light:
            job.add_light_prefix(travel_speed)
        else:
            job.add_mark_prefix(
                travel_speed=travel_speed,
                laser_power=laser_power,
                q_switch_period=q_switch_period,
                cut_speed=cut_speed,
            )
        job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))  # centerize?

        mils_per_mm = 39.3701
        for plot in queue:
            start = plot.start()
            job.laser_control(False)
            job.append(
                balor.MSBF.OpJumpTo(
                    *job.cal.interpolate(
                        start[0] / mils_per_mm, start[1] / mils_per_mm
                    )
                )
            )
            job.laser_control(True)
            for e in plot.generator():
                on = 1
                if len(e) == 2:
                    x, y = e
                else:
                    x, y, on = e
                x /= mils_per_mm
                y /= mils_per_mm
                if on == 0:
                    try:
                        job.laser_control(False)
                        job.append(
                            balor.MSBF.OpJumpTo(*job.cal.interpolate(x, y))
                        )
                        job.laser_control(True)
                        # print("Moving to {x}, {y}".format(x=x, y=y))
                    except ValueError:
                        print("Not including this stroke path:", file=sys.stderr)
                else:
                    job.line(self.current_x, self.current_y, x, y, Op=OpJumpTo if light else OpMarkTo)
                    # print("Cutting {x}, {y} at power {on}".format(x=x, y=y, on=on))
                self.current_x = x
                self.current_y = y
        job.laser_control(False)
        return job


class BalorDriver:
    def __init__(self, service, *args, **kwargs):
        self.service = service
        self.name = str(self.service)

        self.laser_initialized = False
        self.settings = LaserSettings()

        self.process_item = None
        self.spooled_item = None

        self.holds = []
        self.temp_holds = []

        self._thread = None
        self._shutdown = False
        self.last_fetch = None

        self.queue = []

        kernel = service._kernel
        _ = kernel.translation

    def __repr__(self):
        return "BalorDriver(%s)" % self.name

    def shutdown(self, *args, **kwargs):
        self._shutdown = True

    def added(self, origin=None, *args):
        if self._thread is None:

            def clear_thread(*a):
                self._shutdown = True

            self._thread = self.service.threaded(
                self._driver_threaded,
                result=clear_thread,
                thread_name="Driver(%s)" % self.service.path,
            )
            self._thread.stop = clear_thread

    def _driver_threaded(self, *args):
        """
        Fetch and Execute.

        :param args:
        :return:
        """
        while True:
            if self._shutdown:
                return
            if self.spooled_item is None:
                self._fetch_next_item_from_spooler()
            if self.spooled_item is None:
                time.sleep(0.1)
            self._process_spooled_item()

    def _process_spooled_item(self):
        """
        Default Execution Cycle. If Held, we wait. Otherwise we process the spooler.

        Processes one item in the spooler. If the spooler item is a generator. Process one generated item.
        """
        if self.hold():
            time.sleep(0.01)
            return
        if self.spooled_item is None:
            return  # Fetch Next.

        # We have a spooled item to process.
        if self.command(self.spooled_item):
            self.spooled_item = None
            self.service.spooler.pop()
            return

        # We are dealing with an iterator/generator
        try:
            e = next(self.spooled_item)
            if not self.command(e):
                raise ValueError
        except StopIteration:
            # The spooled item is finished.
            self.spooled_item = None
            self.service.spooler.pop()

    def _fetch_next_item_from_spooler(self):
        """
        Fetches the next item from the spooler.

        :return:
        """
        element = self.service.spooler.peek()

        if self.last_fetch is not None:
            self.service.channel("spooler")(
                "Time between fetches: %f" % (time.time() - self.last_fetch)
            )
            self.last_fetch = None

        if element is None:
            return  # Spooler is empty.

        self.last_fetch = time.time()

        if isinstance(element, int):
            self.spooled_item = (element,)
        elif isinstance(element, tuple):
            self.spooled_item = element
        else:
            try:
                self.spooled_item = element.generate()
            except AttributeError:
                try:
                    self.spooled_item = element()
                except TypeError:
                    # This could be a text element, some unrecognized type.
                    return

    def command(self, command, *values):
        """Commands are middle language LaserCommandConstants there values are given."""
        if isinstance(command, tuple):
            values = command[1:]
            command = command[0]
        if not isinstance(command, int):
            return False  # Command type is not recognized.

        if command == COMMAND_LASER_OFF:
            pass
        elif command == COMMAND_LASER_ON:
            pass
        elif command == COMMAND_LASER_DISABLE:
            self.laser_disable()
        elif command == COMMAND_LASER_ENABLE:
            self.laser_enable()
        elif command == COMMAND_CUT:
            x, y = values
            # self.cut(x, y, 1.0)
        elif command == COMMAND_MOVE:
            x, y = values
            # self.move(x, y)
        elif command == COMMAND_JOG:
            x, y = values
            # self.move(x,y)
        elif command == COMMAND_JOG_SWITCH:
            x, y = values
            # self.move(x, y)
        elif command == COMMAND_JOG_FINISH:
            x, y = values
            # self.move(x, y)
        elif command == COMMAND_HOME:
            # self.home(*values)
            pass
        elif command == COMMAND_LOCK:
            pass
        elif command == COMMAND_UNLOCK:
            pass
        elif command == COMMAND_PLOT:
            self.plot_plot(values[0])
        elif command == COMMAND_BLOB:
            pass
        elif command == COMMAND_PLOT_START:
            self.plot_start()
        elif command == COMMAND_SET_SPEED:
            self.settings.speed = values[0]
        elif command == COMMAND_SET_POWER:
            self.settings.power = values[0]
        elif command == COMMAND_SET_PPI:
            self.settings.power = values[0]
        elif command == COMMAND_SET_PWM:
            self.settings.power = values[0]
        elif command == COMMAND_SET_STEP:
            self.settings.raster_step = values[0]
        elif command == COMMAND_SET_OVERSCAN:
            self.settings.overscan = values[0]
        elif command == COMMAND_SET_ACCELERATION:
            self.settings.acceleration = values[0]
        elif command == COMMAND_SET_D_RATIO:
            self.settings.dratio = values[0]
        elif command == COMMAND_SET_DIRECTION:
            pass
        elif command == COMMAND_SET_INCREMENTAL:
            self.set_incremental()
        elif command == COMMAND_SET_ABSOLUTE:
            self.set_absolute()
        elif command == COMMAND_SET_POSITION:
            self.set_position(values[0], values[1])
        elif command == COMMAND_MODE_RAPID:
            pass
        elif command == COMMAND_MODE_PROGRAM:
            pass
        elif command == COMMAND_MODE_RASTER:
            pass
        elif command == COMMAND_MODE_FINISHED:
            pass
        elif command == COMMAND_WAIT:
            self.wait(values[0])
        elif command == COMMAND_WAIT_FINISH:
            self.wait_finish()
        elif command == COMMAND_BEEP:
            self.service("beep\n")
        elif command == COMMAND_FUNCTION:
            if len(values) >= 1:
                t = values[0]
                if callable(t):
                    t()
        elif command == COMMAND_SIGNAL:
            if isinstance(values, str):
                self.service.signal(values, None)
            elif len(values) >= 2:
                self.service.signal(values[0], *values[1:])

        return True

    def realtime_command(self, command, *values):
        """Asks for the execution of a realtime command. Unlike the spooled commands these
        return False if rejected and something else if able to be performed. These will not
        be queued. If rejected. They must be performed in realtime or cancelled.
        """
        try:
            if command == REALTIME_PAUSE:
                pass
            elif command == REALTIME_RESUME:
                pass
            elif command == REALTIME_RESET:
                pass
            elif command == REALTIME_STATUS:
                pass
        except AttributeError:
            pass  # Method doesn't exist.

    def hold(self):
        """
        Holds are criteria to use to pause the data interpretation. These halt the production of new data until the
        criteria is met. A hold is constant and will always halt the data while true. A temp_hold will be removed
        as soon as it does not hold the data.

        :return: Whether data interpretation should hold.
        """
        temp_hold = False
        fail_hold = False
        for i, hold in enumerate(self.temp_holds):
            if not hold():
                self.temp_holds[i] = None
                fail_hold = True
            else:
                temp_hold = True
        if fail_hold:
            self.temp_holds = [hold for hold in self.temp_holds if hold is not None]
        if temp_hold:
            return True
        for hold in self.holds:
            if hold():
                return True
        return False

    def laser_disable(self, *values):
        self.settings.laser_enabled = False

    def laser_enable(self, *values):
        self.settings.laser_enabled = True

    def plot_plot(self, plot):
        """
        :param plot:
        :return:
        """
        self.queue.append(plot)

    def plot_start(self):
        self.service.controller.queue_job(self.service.cutcode_to_job(self.queue))

    def set_power(self, power=1000.0):
        self.settings.power = power
        if self.settings.power > 1000.0:
            self.settings.power = 1000.0
        if self.settings.power <= 0:
            self.settings.power = 0.0

    def set_ppi(self, power=1000.0):
        self.settings.power = power
        if self.settings.power > 1000.0:
            self.settings.power = 1000.0
        if self.settings.power <= 0:
            self.settings.power = 0.0

    def set_pwm(self, power=1000.0):
        self.settings.power = power
        if self.settings.power > 1000.0:
            self.settings.power = 1000.0
        if self.settings.power <= 0:
            self.settings.power = 0.0

    def set_overscan(self, overscan=None):
        self.settings.overscan = overscan

    def set_incremental(self, *values):
        self.is_relative = True

    def set_absolute(self, *values):
        self.is_relative = False

    def set_position(self, x, y):
        self.current_x = x
        self.current_y = y

    def wait(self, t):
        time.sleep(float(t))

    def wait_finish(self, *values):
        """Adds an additional holding requirement if the pipe has any data."""
        self.temp_holds.append(lambda: len(self.output) != 0)

    def status(self):
        parts = list()
        parts.append("x=%f" % self.current_x)
        parts.append("y=%f" % self.current_y)
        parts.append("speed=%f" % self.settings.speed)
        parts.append("power=%d" % self.settings.power)
        status = ";".join(parts)
        self.service.signal("driver;status", status)

    @property
    def type(self):
        return "lhystudios"


class BalorController:
    def __init__(self, service):

        self._shutdown = False
        self.index = 0
        self.loop_job = None
        self.service = service
        self.service.setting(bool, "mock", False)
        self.connected_machine = balor.BJJCZ_LMCV4_FIBER_M.BJJCZ_LMCV4_FIBER_M()
        self.job_queue = []
        self.lock = threading.Lock()

        self.service.threaded(self.data_sender, thread_name="balor-controller")

    def shutdown(self):
        self._shutdown = True

    def queue_job(self, job):
        if isinstance(job, Job):
            job = job.serialize()
        with self.lock:
            self.job_queue.append(job)

    def data_sender(self):
        print("data_sender")
        queue = []
        connected = False
        while not connected:
            connected = self.connected_machine.connect_device(self.index)
            if not connected:
                print("connection failed")
                time.sleep(0.5)
                if self.service.mock:
                    self.connected_machine.mock = True
        while not self._shutdown:
            if self.job_queue:
                with self.lock:
                    queue.extend(self.job_queue)
                    self.job_queue.clear()
                for q in queue:
                    self.connected_machine.mark(q)
                continue
            if self.loop_job is not None:
                self.connected_machine.mark(self.loop_job)
        self.connected_machine.disconnect_device(self.index)
