import os
import sys
import threading
import time

from meerk40t.core.cutcode import LaserSettings, CutCode, LineCut
from meerk40t.core.spoolers import Spooler
from meerk40t.kernel import Service

from PIL import Image, ImageDraw

from meerk40t.core.cutcode import LaserSettings, LineCut, CutCode, QuadCut, RasterCut
from meerk40t.core.elements import LaserOperation
from meerk40t.svgelements import Point, Path, SVGImage, Length

import balor
from balor.GalvoConnection import GotoXY
from balor.MSBF import Job
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


class BalorDevice(Service):
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
                "tip": _("This starts connects to fake software laser rather than real one for debugging."),
            },
        ]
        self.register_choices("balor", choices)

        self.current_x = 0.0
        self.current_y = 0.0
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

        @self.console_argument("minimum", type=float, default=0x7000)
        @self.console_argument("maximum", type=float, default=0x9000)
        @self.console_command(
            "light",
            help=_("Turn redlight on."),
        )
        def light(command, channel, _, minimum=0x7000, maximum=0x9000, data=None, remainder=None, **kwgs):
            cutcode = CutCode()
            settings = LaserSettings()
            cutcode.append(
                LineCut(Point(minimum, minimum), Point(minimum, maximum), settings=settings)
            )
            cutcode.append(
                LineCut(Point(minimum, maximum), Point(maximum, maximum), settings=settings)
            )
            cutcode.append(
                LineCut(Point(maximum, maximum), Point(maximum, minimum), settings=settings)
            )
            cutcode.append(
                LineCut(Point(maximum, minimum), Point(minimum, minimum), settings=settings)
            )
            self.spooler.set_idle(("light", self.driver.cutcode_to_light_job(cutcode)))

        @self.console_command(
            "nolight",
            help=_("turn light off"),
            input_type=(None),
        )
        def light(command, channel, _, data=None, remainder=None, **kwgs):
            self.spooler.set_idle(None)

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

        @self.console_command(
            "loop",
            help=_("loop the selected job forever"),
            input_type="balor",
            output_type="balor",
        )
        def balor_loop(command, channel, _, data=None,  remainder=None, **kwgs):

            # Maybe each should be run in sequence instead?
            if isinstance(data, list): data = data[0]

            #print ("Saving trace")
            #open("/home/bryce/Projects/Balor/meerk40t-log.bin", 'wb').write(data)

            # The light_data command will end up being called on the current BalorDriver repeatedly.
            self.spooler.set_idle(("light_data", data))

        @self.console_argument("x", type=float, default=0.0)
        @self.console_argument("y", type=float, default=0.0)
        @self.console_command(
            "redlight",
            help=_("send laser as a goto"),
        )
        def balor_goto(command, channel, _, x=None, y=None, remainder=None, **kwgs):
            if x is not None and y is not None:
                rx = int(0x8000 + x) & 0xFFFF
                ry = int(0x8000 + y) & 0xFFFF
                self.driver.connection.GotoXY(rx, ry)

        @self.console_command(
            "laser_on",
            help=_("sends enable laser."),
        )
        def balor_on(command, channel, _, remainder=None, **kwgs):
            self.driver.connection.EnableLaser()


        @self.console_command(
            "laser_off",
            help=_("sends disable laser."),
        )
        def balor_on(command, channel, _, remainder=None, **kwgs):
            self.driver.connection.DisableLaser()

        @self.console_command(
            "signal_on",
            help=_("sends enable laser."),
        )
        def balor_on(command, channel, _, remainder=None, **kwgs):
            self.driver.connection.LaserSignalOn()

        @self.console_command(
            "signal_off",
            help=_("sends disable laser."),
        )
        def balor_on(command, channel, _, remainder=None, **kwgs):
            self.driver.connection.LaserSignalOff()


        @self.console_command(
            "unknown7",
            help=_("sends unknown command save."),
        )
        def balor_on(command, channel, _, remainder=None, **kwgs):
            reply = self.driver.connection.Unknown0x0700()
            channel("Command replied: {reply}".format(reply=str(reply)))

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
                    channel("Calibration file is set to: {file}".format(file=self.calfile))
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
                    channel("The file at {filename} does not exist.".format(filename=os.path.realpath(filename)))
                    channel("Calibration file set to None.")
                    self.calfile = "0"

        @self.console_command(
            "position",
            help=_("give the galvo position of the selection"),
        )
        def galvo_pos(
                command,
                channel,
                _,
                data=None,
                args=tuple(),
                **kwargs
        ):
            """
            Draws an outline of the current shape.
            """
            bounds = self.elements.selected_area()
            if bounds is None:
                channel(_("Nothing Selected"))
                return
            cal = balor.Cal.Cal(self.calfile)

            x0 = bounds[0]
            y0 = bounds[1]
            width = bounds[2] - bounds[0]
            height = bounds[3] - bounds[1]
            cx, cy = cal.interpolate(x0, y0)
            mx, my = cal.interpolate(bounds[2], bounds[3])

            channel("Top Right: ({cx}, {cy}). Lower, Left: ({mx},{my})".format(cx=cx, cy=cy, mx=mx, my=my))


        @self.console_argument("lens_size", type=Length, default=None)
        @self.console_command(
            "lens",
            help=_("give the galvo position of the selection"),
        )
        def galvo_lens(
                command,
                channel,
                _,
                data=None,
                lens_size=None,
                args=tuple(),
                **kwargs
        ):
            """
            Sets lens size.
            """
            if lens_size is None:
                raise SyntaxError
            self.scale_x = (lens_size / (float((0xFFFF)))).value(ppi=1000)
            self.scale_y = (lens_size / (float((0xFFFF)))).value(ppi=1000)
            channel("Scale Factor set to : ({sx}, {sy}).".format(sx=self.scale_x, sy=self.scale_y))
            self.signal("bed_size")


        @self.console_option("x", "x_offset", type=Length, help=_("x offset."))
        @self.console_option("y", "y_offset", type=Length, help=_("y offset"))
        @self.console_command(
            "lightbox",
            help=_("outline the current selected elements"),
            output_type="balor",
        )
        def element_outline(
            command,
            channel,
            _,
            x_offset=Length(0),
            y_offset=Length(0),
            data=None,
            args=tuple(),
            **kwargs
        ):
            """
            Draws an outline of the current shape.
            """
            if x_offset is None:
                raise SyntaxError
            bounds = self.elements.selected_area()
            if bounds is None:
                channel(_("Nothing Selected"))
                return
            x0 = bounds[0]
            y0 = bounds[1]
            width = bounds[2] - bounds[0]
            height = bounds[3] - bounds[1]
            offset_x = (
                y_offset.value(ppi=1000.0, relative_length=width)
                if len(args) >= 1
                else 0
            )
            offset_y = (
                x_offset.value(ppi=1000.0, relative_length=height)
                if len(args) >= 2
                else offset_x
            )
            #print ("Box parameters", x0, y0, width, height)
            x0 -= offset_x
            y0 -= offset_y
            width += offset_x * 2
            height += offset_y * 2
            job = balor.MSBF.Job()
            job.cal = balor.Cal.Cal(self.calfile)
            job.add_light_prefix(travel_speed=int(self.travel_speed))

            for _ in range(200):
                job.line(int(x0), int(y0), int(x0 + width), int(y0), seg_size=500, Op=balor.MSBF.OpJumpTo)
                job.line(int(x0 + width), int(y0), int(x0 + width), int(y0 + height), seg_size=500, Op=balor.MSBF.OpJumpTo)
                job.line(int(x0 + width), int(y0 + height), int(x0), int(y0 + height), seg_size=500, Op=balor.MSBF.OpJumpTo)
                job.line(int(x0), int(y0 + height), int(x0), int(y0), seg_size=500, Op=balor.MSBF.OpJumpTo)
                job.calculate_distances()
            return "balor", [job.serialize()]

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
            # approximate scale for speeds
            # ap_x_scale = cal.interpolate(10.0, 10.0)[0] - cal.interpolate(-10.0, -10.0)[0]
            # ap_y_scale = cal.interpolate(10.0, 10.0)[1] - cal.interpolate(-10.0, -10.0)[1]
            # ap_scale = (ap_x_scale+ap_y_scale)/20.0
            # print ("Approximate scale", ap_scale, "units/mm", file=sys.stderr)
            travel_speed = int(round(self.travel_speed / 2.0))  # units are 2mm/sec
            cut_speed = int(round(self.cut_speed / 2.0))
            laser_power = int(round(self.laser_power * 40.95))
            q_switch_period = int(round(1.0 / (self.q_switch_frequency * 1e3) / 50e-9))
            print("Image size: %.2f mm x %.2f mm" % (width, height), file=sys.stderr)
            print("Travel speed 0x%04X" % travel_speed, file=sys.stderr)
            print("Cut speed 0x%04X" % cut_speed, file=sys.stderr)
            print("Q switch period 0x%04X" % q_switch_period, file=sys.stderr)
            print("Laser power 0x%04X" % laser_power, file=sys.stderr)

            if grayscale:
                gsmin = grayscale_min
                gsmax = grayscale_max
                gsslope = (gsmax - gsmin) / 256.0
            job = balor.MSBF.Job()
            cal = balor.Cal.Cal(self.calfile)
            job.cal = cal

            img = scipy.interpolate.RectBivariateSpline(
                np.linspace(y0, y0 + height, in_file.size[1]),
                np.linspace(x0, x0 + width, in_file.size[0]),
                np.asarray(in_file),
            )

            dither = 0
            job.add_mark_prefix(
                travel_speed=travel_speed,
                laser_power=laser_power,
                q_switch_period=q_switch_period,
                cut_speed=cut_speed,
            )
            y = y0
            count = 0
            burning = False
            old_y = y0
            while y < y0 + height:
                x = x0
                job.append(balor.MSBF.OpTravel(*cal.interpolate(x, y)))
                old_x = x0
                while x < x0 + width:
                    px = img(y, x)[0][0]
                    if invert:
                        px = 255.0 - px

                    if grayscale:
                        if px > 0:
                            gsval = gsmin + gsslope * px
                            if grayscale == "power":
                                job.change_laser_power(gsval)
                            elif grayscale == "speed":
                                job.change_cut_speed(gsval)
                            elif grayscale == "q_switch_frequency":
                                job.change_q_switch_frequency(gsval)
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
                                job.append(balor.MSBF.OpCut(*cal.interpolate(x, y)))
                                job.append(
                                    balor.MSBF.OpCut(*cal.interpolate(old_x, old_y))
                                )
                                i -= 2
                            job.append(balor.MSBF.OpCut(*cal.interpolate(x, y)))
                            burning = True

                        else:
                            if burning:
                                # laser turn off
                                job.laser_control(False)
                            job.append(balor.MSBF.OpTravel(*cal.interpolate(x, y)))
                            burning = False
                    else:

                        if px + dither > threshold:
                            if not burning:
                                job.laser_control(True)  # laser turn on
                            job.append(balor.MSBF.OpCut(*cal.interpolate(x, y)))
                            burning = True
                            dither = 0.0
                        else:
                            if burning:
                                # laser turn off
                                job.laser_control(False)
                            job.append(balor.MSBF.OpTravel(*cal.interpolate(x, y)))
                            dither += abs(px + dither - threshold) * args.dither
                            burning = False
                    old_x = x
                    x += args.raster_x_res
                if burning:
                    # laser turn off
                    job.laser_control(False)
                    burning = False

                old_y = y
                y += args.raster_y_res
                count += 1
                if not (count % 20):
                    print("\ty = %.3f" % y, file=sys.stderr)

            job.calculate_distances()
            return "balor", [job.serialize()]
