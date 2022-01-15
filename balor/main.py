import os
import sys
import threading
import time

from meerk40t.core.cutcode import LaserSettings, CutCode, LineCut
from meerk40t.core.spoolers import Spooler
from meerk40t.core.units import ViewPort
from meerk40t.kernel import Service

from PIL import Image, ImageDraw

from meerk40t.core.cutcode import LaserSettings, LineCut, CutCode, QuadCut, RasterCut
from meerk40t.core.elements import LaserOperation
from meerk40t.svgelements import Point, Path, SVGImage, Length, Polygon, Shape

import balor
from balor.GalvoConnection import GotoXY
from balor.BalorJob import CommandList
from balor.BalorDriver import BalorDriver

import numpy as np
import scipy
import scipy.interpolate


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


class BalorDevice(Service, ViewPort):
    """
    The BalorDevice is a MeerK40t service for the device type. It should be the main method of interacting with
    the rest of meerk40t. It defines how the scene should look and contains a spooler which meerk40t will give jobs
    to. This class additionally defines commands which exist as console commands while this service is activated.
    """

    def __init__(self, kernel, path, *args, **kwargs):
        Service.__init__(self, kernel, path)
        self.name = "balor"

        _ = kernel.translation

        choices = [
            {
                "attr": "lens_size",
                "object": self,
                "default": "110mm",
                "type": float,
                "label": _("Width"),
                "tip": _("Lens Size"),
            },
            {
                "attr": "bedheight",
                "object": self,
                "default": "110mm",
                "type": float,
                "label": _("Height"),
                "tip": _("Height of the laser bed."),
            },
        ]
        self.register_choices("bed_dim", choices)
        ViewPort.__init__(self, 0, 0, self.lens_size, self.lens_size)

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
                "attr": "calfile_enabled",
                "object": self,
                "default": False,
                "type": bool,
                "label": _("Enable Calibration File"),
                "tip": _("Use calibration file?"),
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
            {
                "attr": "mock",
                "object": self,
                "default": False,
                "type": bool,
                "label": _("Run mock-usb backend"),
                "tip": _(
                    "This starts connects to fake software laser rather than real one for debugging."
                ),
            },
        ]
        self.register_choices("balor", choices)

        self.state = 0
        self.spooler = Spooler(self)
        self.driver = BalorDriver(self)
        self.spooler.driver = self.driver

        # self.add_service_delegate(self.driver)
        self.add_service_delegate(self.spooler)

        self.viewbuffer = ""

        @self.console_command(
            "spool",
            help=_("spool <command>"),
            regex=True,
            input_type=(None, "plan", "device", "balor"),
            output_type="spooler",
        )
        def spool(
            command, channel, _, data=None, data_type=None, remainder=None, **kwgs
        ):
            """
            Registers the spool command for the Balor driver.
            """
            spooler = self.spooler
            if data is not None:
                if data_type == "balor":
                    spooler.job(("balor_job", data))
                    return "spooler", spooler
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
            "mark",
            input_type="elements",
            output_type="balor",
            help=_("runs mark on path."),
        )
        def mark(command, channel, _, data=None, remainder=None, **kwgs):
            channel("Creating mark job out of elements.")
            return "balor", self.driver.paths_to_mark_job(data)

        @self.console_option(
            "speed",
            "s",
            type=bool,
            action="store_true",
            help="Run this light job at slow speed for the parts that would have been cuts.",
        )
        @self.console_command(
            "light",
            input_type="elements",
            output_type="balor",
            help=_("runs light on events."),
        )
        def light(command, channel, _, speed=False, data=None, remainder=None, **kwgs):
            channel("Creating light job out of elements.")
            return "balor", self.driver.paths_to_light_job(data, speed=speed)

        @self.console_command(
            "stop",
            help=_("stops the idle running job"),
            input_type=(None),
        )
        def stoplight(command, channel, _, data=None, remainder=None, **kwgs):
            channel("Stopping idle job")
            self.spooler.set_idle(None)
            self.driver.connection.StopList()
            self.driver.connection.WritePort()

        @self.console_command(
            "usb_connect",
            help=_("connect usb"),
        )
        def usb_connect(command, channel, _, data=None, remainder=None, **kwgs):
            if self.driver.connecting:
                self.driver.disconnect()
                return
            if self.driver.connected:
                self.driver.disconnect()
                return
            if self.driver._shutdown:
                self.driver.restart()
                return

        @self.console_command(
            "usb_disconnect",
            help=_("connect usb"),
        )
        def usb_connect(command, channel, _, data=None, remainder=None, **kwgs):
            self.driver.disconnect()

        @self.console_command(
            "print",
            help=_("print balor info about generated job"),
            input_type="balor",
            output_type="balor",
        )
        def balor_print(command, channel, _, data=None, remainder=None, **kwgs):
            for d in data:
                print(d)
            return "balor", data

        @self.console_argument("filename", type=str, default="balor.bin")
        @self.console_command(
            "save",
            help=_("print balor info about generated job"),
            input_type="balor",
            output_type="balor",
        )
        def balor_save(
            command, channel, _, data=None, filename="balor.bin", remainder=None, **kwgs
        ):
            with open(filename, "wb") as f:
                for d in data:
                    f.write(d)
            channel("Saved file {filename} to disk.".format(filename=filename))
            return "balor", data

        @self.console_argument(
            "repeats", help="Number of times to duplicate the job", default=1
        )
        @self.console_command(
            "duplicate",
            help=_("loop the selected job forever"),
            input_type="balor",
            output_type="balor",
        )
        def balor_dup(
            command, channel, _, data=None, repeats=1, remainder=None, **kwgs
        ):
            data.duplicate(1, None, repeats)
            channel("Job duplicated")
            return "balor", data

        @self.console_command(
            "loop",
            help=_("loop the selected job forever"),
            input_type="balor",
            output_type="balor",
        )
        def balor_loop(command, channel, _, data=None, remainder=None, **kwgs):
            self.driver.connection.WritePort(0x0100)
            channel("Looping job: {job}".format(job=str(data)))
            self.spooler.set_idle(("light", data))
            return "balor", data

        @self.console_argument("x", type=float, default=0.0)
        @self.console_argument("y", type=float, default=0.0)
        @self.console_command(
            "goto",
            help=_("send laser a goto command"),
        )
        def balor_goto(command, channel, _, x=None, y=None, remainder=None, **kwgs):
            if x is not None and y is not None:
                rx = int(0x8000 + x) & 0xFFFF
                ry = int(0x8000 + y) & 0xFFFF
                self.driver.connection.GotoXY(rx, ry)

        @self.console_argument("off", type=str)
        @self.console_command(
            "red",
            help=_("Turns redlight on/off"),
        )
        def balor_on(command, channel, _, off=None, remainder=None, **kwgs):
            if off == "off":
                reply = self.driver.connection.WritePort()
                channel("Turning off redlight.")
            else:
                reply = self.driver.connection.WritePort(0x0100)
                channel("Turning on redlight.")

        @self.console_command(
            "status",
            help=_("Sends status check"),
        )
        def balor_status(command, channel, _, remainder=None, **kwgs):
            reply = self.driver.connection.ReadPort()
            channel("Command replied: {reply}".format(reply=str(reply)))
            for index, b in enumerate(reply):
                channel(
                    "Bit {index}: {bits}".format(
                        index="{0:x}".format(index), bits="{0:b}".format(b)
                    )
                )

        @self.console_command(
            "lstatus",
            help=_("Checks the list status."),
        )
        def balor_status(command, channel, _, remainder=None, **kwgs):
            reply = self.driver.connection.GetListStatus()
            channel("Command replied: {reply}".format(reply=str(reply)))
            for index, b in enumerate(reply):
                channel(
                    "Bit {index}: {bits}".format(
                        index="{0:x}".format(index), bits="{0:b}".format(b)
                    )
                )

        @self.console_command(
            "serial_number",
            help=_("Checks the serial number."),
        )
        def balor_serial(command, channel, _, remainder=None, **kwgs):
            reply = self.driver.connection.GetSerialNo()
            channel("Command replied: {reply}".format(reply=str(reply)))
            for index, b in enumerate(reply):
                channel(
                    "Bit {index}: {bits}".format(
                        index="{0:x}".format(index), bits="{0:b}".format(b)
                    )
                )

        @self.console_argument("filename", type=str, default=None)
        @self.console_command(
            "calibrate",
            help=_("set the calibration file"),
        )
        def set_calfile(command, channel, _, filename=None, remainder=None, **kwgs):
            if filename is None:
                calfile = self.calfile
                if calfile is None:
                    channel("No calibration file set.")
                else:
                    channel(
                        "Calibration file is set to: {file}".format(file=self.calfile)
                    )
                    from os.path import exists

                    if exists(calfile):
                        channel("Calibration file exists!")
                        cal = balor.Cal.Cal(calfile)
                        if cal.enabled:
                            channel("Calibration file successfully loads.")
                        else:
                            channel("Calibration file does not load.")
                    else:
                        channel("WARNING: Calibration file does not exist.")
            else:
                from os.path import exists

                if exists(filename):
                    self.calfile = filename
                else:
                    channel(
                        "The file at {filename} does not exist.".format(
                            filename=os.path.realpath(filename)
                        )
                    )
                    channel("Calibration file was not set.")

        @self.console_command(
            "position",
            help=_("give the galvo position of the selection"),
        )
        def galvo_pos(command, channel, _, data=None, args=tuple(), **kwargs):
            """
            Draws an outline of the current shape.
            """
            bounds = self.elements.selected_area()
            if bounds is None:
                channel(_("Nothing Selected"))
                return
            cal = balor.Cal.Cal(self.calibration_file)

            x0 = bounds[0] * self.get_native_scale_x
            y0 = bounds[1] * self.get_native_scale_y
            x1 = bounds[2] * self.get_native_scale_x
            y1 = bounds[3] * self.get_native_scale_y
            width = (bounds[2] - bounds[0]) * self.get_native_scale_x
            height = (bounds[3] - bounds[1]) * self.get_native_scale_y
            cx, cy = cal.interpolate(x0, y0)
            mx, my = cal.interpolate(x1, y1)
            channel(
                "Top Right: ({cx}, {cy}). Lower, Left: ({mx},{my})".format(
                    cx=cx, cy=cy, mx=mx, my=my
                )
            )

        @self.console_argument("lens_size", type=str, default=None)
        @self.console_command(
            "lens",
            help=_("give the galvo position of the selection"),
        )
        def galvo_lens(
            command, channel, _, data=None, lens_size=None, args=tuple(), **kwargs
        ):
            """
            Sets lens size.
            """
            if lens_size is None:
                raise SyntaxError
            self.bedwidth = lens_size
            self.bedheight = lens_size

            channel(
                "Set Bed Size : ({sx}, {sy}).".format(
                    sx=self.bedwidth, sy=self.bedheight
                )
            )

            self.signal("bed_size")

        @self.console_command(
            "box",
            help=_("outline the current selected elements"),
            output_type="elements",
        )
        def element_outline(command, channel, _, data=None, args=tuple(), **kwargs):
            """
            Draws an outline of the current shape.
            """
            bounds = self.elements.selected_area()
            if bounds is None:
                channel(_("Nothing Selected"))
                return
            x, y, height, width = bounds
            channel("Element bounds: {bounds}".format(bounds=str(bounds)))
            points = [
                (x, y),
                (x + width, y),
                (x + width, y + height),
                (x, y + height),
                (x, y),
            ]
            return "elements", [Polygon(*points)]

        @self.console_command(
            "hull",
            help=_("convex hull of the current selected elements"),
            input_type=(None, "elements"),
            output_type="elements",
        )
        def element_outline(command, channel, _, data=None, args=tuple(), **kwargs):
            """
            Draws an outline of the current shape.
            """
            if data is None:
                data = list(self.elements.elems(emphasized=True))
            pts = []
            for obj in data:
                if isinstance(obj, Shape):
                    if not isinstance(obj, Path):
                        obj = Path(obj)
                    epath = abs(obj)
                    pts += [q for q in epath.as_points()]
                elif isinstance(obj, SVGImage):
                    bounds = obj.bbox()
                    pts += [
                        (bounds[0], bounds[1]),
                        (bounds[0], bounds[3]),
                        (bounds[2], bounds[1]),
                        (bounds[2], bounds[3]),
                    ]
            hull = [p for p in Point.convex_hull(pts)]
            if len(hull) == 0:
                channel(_("No elements bounds to trace."))
                return
            hull.append(hull[0])  # loop
            return "elements", [Polygon(*hull)]

        def ant_points(points, steps):
            points = list(points)
            movement = 1 + int(steps / 10)
            forward_steps = steps + movement
            pos = 0
            size = len(points)
            cycles = int(size / movement) + 1
            for cycle in range(cycles):
                for f in range(pos, pos + forward_steps, 1):
                    index = f % size
                    point = points[index]
                    yield point
                pos += forward_steps
                for f in range(pos, pos - steps, -1):
                    index = f % size
                    point = points[index]
                    yield point
                pos -= steps

        @self.console_option(
            "q",
            "quantization",
            default=200,
            help="Number of segments to break each path into.",
        )
        @self.console_command(
            "ants",
            help=_("Marching ants of the given element path."),
            input_type=(None, "elements"),
            output_type="elements",
        )
        def element_ants(
            command, channel, _, data=None, quantization=200, args=tuple(), **kwargs
        ):
            """
            Draws an outline of the current shape.
            """
            if data is None:
                data = list(self.elements.elems(emphasized=True))
            points_list = []
            points = list()
            for e in data:
                if isinstance(e, Shape):
                    if not isinstance(e, Path):
                        e = Path(e)
                    e = abs(e)
                for i in range(0, quantization + 1):
                    x, y = e.point(i / float(quantization))
                    x *= self.get_native_scale_x
                    y *= self.get_native_scale_y
                    points.append((x, y))
                points_list.append(list(ant_points(points, int(quantization / 10))))
            return "elements", [Polygon(*p) for p in points_list]

        @self.console_option(
            "raster-x-res",
            help="X resolution (in mm) of the laser.",
            default=0.15,
            type=float,
        )
        @self.console_option(
            "raster-y-res",
            help="X resolution (in mm) of the laser.",
            default=0.15,
            type=float,
        )
        @self.console_option(
            "x",
            "xoffs",
            help="Specify an x offset for the image (mm.)",
            default=0.0,
            type=float,
        )
        @self.console_option(
            "y",
            "yoffs",
            help="Specify an y offset for the image (mm.)",
            default=0.0,
            type=float,
        )
        @self.console_option(
            "d", "dither", help="Configure dithering", default=0.1, type=float
        )
        @self.console_option(
            "s",
            "scale",
            help="Pixels per mm (default 23.62 px/mm - 600 DPI)",
            default=23.622047,
            type=float,
        )
        @self.console_option(
            "t",
            "threshold",
            help="Greyscale threshold for burning (default 0.5, negative inverts)",
            default=0.5,
            type=float,
        )
        @self.console_option(
            "g",
            "grayscale",
            help="Greyscale rastering (power, speed, q_switch_frequency, passes)",
            default=False,
            type=bool,
        )
        @self.console_option(
            "grayscale-min",
            help="Minimum (black=1) value of the gray scale",
            default=None,
            type=float,
        )
        @self.console_option(
            "grayscale-max",
            help="Maximum (white=255) value of the gray scale",
            default=None,
            type=float,
        )
        @self.console_command("balor-raster", input_type="image", output_type="balor")
        def balor_raster(
            command,
            channel,
            _,
            data=None,
            raster_x_res=0.15,
            raster_y_res=0.15,
            xoffs=0.0,
            yoffs=0.0,
            dither=0.1,
            scale=23.622047,
            threshold=0.5,
            grayscale=False,
            grayscale_min=None,
            grayscale_max=None,
            **kwgs
        ):
            # def raster_render(self, job, cal, in_file, out_file, args):
            if len(data) == 0:
                channel("No image selected.")
                return
            in_file = data[0].image
            width = in_file.size[0] / scale
            height = in_file.size[1] / scale
            x0, y0 = xoffs, yoffs

            invert = False
            if threshold < 0:
                invert = True
                threshold *= -1.0
            dither = 0
            passes = 1
            if grayscale:
                gsmin = grayscale_min
                gsmax = grayscale_max
                gsslope = (gsmax - gsmin) / 256.0
            job = balor.BalorJob.CommandList()
            cal = balor.Cal.Cal(self.calibration_file)
            job.cal = cal

            img = scipy.interpolate.RectBivariateSpline(
                np.linspace(y0, y0 + height, in_file.size[1]),
                np.linspace(x0, x0 + width, in_file.size[0]),
                np.asarray(in_file),
            )

            dither = 0
            job.set_mark_settings(
                travel_speed=self.travel_speed,
                power=self.laser_power,
                frequency=self.q_switch_frequency,
                cut_speed=self.cut_speed,
                laser_on_delay=100,
                laser_off_delay=100,
                polygon_delay=100,
            )
            y = y0
            count = 0
            burning = False
            old_y = y0
            while y < y0 + height:
                x = x0
                job.goto(x,y)
                old_x = x0
                while x < x0 + width:
                    px = img(y, x)[0][0]
                    if invert:
                        px = 255.0 - px

                    if grayscale:
                        if px > 0:
                            gsval = gsmin + gsslope * px
                            if grayscale == "power":
                                job.set_power(gsval)
                            elif grayscale == "speed":
                                job.set_cut_speed(gsval)
                            elif grayscale == "q_switch_frequency":
                                job.set_frequency(gsval)
                            elif grayscale == "passes":
                                passes = int(round(gsval))
                                # Would probably be better to do this over the course of multiple
                                # rasters for heat disappation during 2.5D engraving
                            # pp = int(round((int(px)/255) * args.laser_power * 40.95))
                            # job.change_settings(q_switch_period, pp, cut_speed)

                            if not burning:
                                job.laser_control(True)  # laser turn on
                            i = passes
                            while i > 1:
                                job.mark(x,y)
                                job.mark(old_x, old_y)
                                i -= 2
                            job.mark(x,y)
                            burning = True

                        else:
                            if burning:
                                # laser turn off
                                job.laser_control(False)
                            job.goto(x,y)
                            burning = False
                    else:

                        if px + dither > threshold:
                            if not burning:
                                job.laser_control(True)  # laser turn on
                            job.mark(x,y)
                            burning = True
                            dither = 0.0
                        else:
                            if burning:
                                # laser turn off
                                job.laser_control(False)
                            job.goto(x,y)
                            dither += abs(px + dither - threshold) * dither
                            burning = False
                    old_x = x
                    x += raster_x_res
                if burning:
                    # laser turn off
                    job.laser_control(False)
                    burning = False

                old_y = y
                y += raster_y_res
                count += 1
                if not (count % 20):
                    print("\ty = %.3f" % y, file=sys.stderr)

            return "balor", job

    @property
    def current_x(self):
        """
        @return: the location in nm for the current known x value.
        """
        return float(self.driver.native_x / self.width) * 0xFFF

    @property
    def current_y(self):
        """
        @return: the location in nm for the current known y value.
        """
        return float(self.driver.native_y * (0xFFFF / self.height))

    @property
    def get_native_scale_x(self):
        """
        Native x goes from 0x0000 to 0xFFFF with 0x8000 being zero.
        :return:
        """
        actual_size_in_nm = self.width
        galvo_range = 0xFFFF
        nm_per_galvo = actual_size_in_nm / galvo_range
        return 1.0 / nm_per_galvo

    @property
    def get_native_scale_y(self):
        actual_size_in_nm = self.height
        galvo_range = 0xFFFF
        nm_per_galvo = actual_size_in_nm / galvo_range
        return 1.0 / nm_per_galvo

    @property
    def calibration_file(self):
        if self.calfile_enabled:
            return self.calfile
        else:
            return None
