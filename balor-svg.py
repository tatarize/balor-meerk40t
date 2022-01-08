#!/usr/bin/env python3
import balor
import argparse

parser = argparse.ArgumentParser(
    description="""
Tool to convert a subset of SVG (scalable vector graphics) files to the 
machine-specific binary format used by Beijing JCZ galvo-based laser engravers.
This program produces raw bytestreams that can be sent by balor. SVG files
should not have any transforms or effects, and only paths will be converted
(e.g. no raster images, and no text - though text can just be converted to 
paths without incident.) You can also provide a settings file to associate
colors with engraver settings (q switch frequency, power, etc). Note: if this
is giving ValueErrors due to parameter overflow in travel/cut operations, 
your SVG file probably has group transforms (translate) that this program
ignores currently. (Basically, you just need to "flatten transforms.")""",
    epilog="""
NOTE: This software is EXPERIMENTAL and has only been tested with a
single machine. There are many different laser engraving machines 
and the fact that they look the same, or even have the same markings,
is not proof that they are really the same.""",
)

parser.add_argument(
    "operation",
    help="choose operational mode (in lighting mode, a bounding box will be drawn.)",
    default="light",
    choices=["mark", "light"],
)

parser.add_argument("-f", "--file", help="svg file to load.", default=None)

parser.add_argument(
    "-o", "--output", help="Specify the output file. (default stdout)", default=None
)

parser.add_argument(
    "-c", "--calfile", help="Provide a calibration file for the machine."
)

parser.add_argument(
    "-s",
    "--settings",
    help="Provide a settings file matching colors to machine settings.",
)


parser.add_argument(
    "-m",
    "--machine",
    help="specify which machine interface to use. Valid machines: "
    + ", ".join([x.__name__ for x in balor.all_known_machines]),
    default="BJJCZ_LMCV4_FIBER_M",
)

parser.add_argument(
    "--travel-speed",
    help="Specify the traveling speed (mm/s)",
    default=2000,
    type=float,
)
parser.add_argument(
    "--cut-speed",
    help="Specify the default cutting speed (mm/s)",
    default=800,
    type=float,
)
parser.add_argument(
    "--laser-power",
    help="Specify the default laser power in percentage.",
    default=80,
    type=float,
)
parser.add_argument(
    "--q-switch-frequency",
    help="Specify the default q switch frequency in KHz",
    default=30.0,
    type=float,
)
parser.add_argument(
    "--repetition",
    "-r",
    help="Specify the default number of passes. The file will be repeated from the first G00 movement.",
    default=10,
    type=int,
)
parser.add_argument(
    "--hatch-spacing",
    help="Specify the default hatching spacing in microns",
    default=40.0,
    type=float,
)
parser.add_argument(
    "--hatch-angle",
    help="Specify the default hatching angle in degrees",
    default=45.0,
    type=float,
)
parser.add_argument(
    "--segment-length",
    help="Maximum path segment length in mm",
    default=1.0,
    type=float,
)
parser.add_argument(
    "--xscale",
    help="Scale the x coordinates by this factor (before translation)",
    default=1.0,
    type=float,
)
parser.add_argument(
    "--yscale",
    help="Scale the y coordinates by this factor (before translation)",
    default=1.0,
    type=float,
)

parser.add_argument(
    "-x",
    "--xoff",
    help="Add this value to all x coordinates (after scaling)",
    default=0.0,
    type=float,
)
parser.add_argument(
    "-y",
    "--yoff",
    help="Add this value to all y coordinates (after scaling)",
    default=0.0,
    type=float,
)


args = parser.parse_args()
import numpy as np


def separate_points(path, seglen, xscale, yscale, xoff, yoff):
    points = []
    lastx, lasty = path[0].start.real, path[0].start.imag
    for segment in path:
        startx, starty = segment.start.real, segment.start.imag
        endx, endy = segment.end.real, segment.end.imag
        samples = max(2, 1 + int(round(segment.length() / seglen)))
        ts = np.linspace(0, 1, samples)
        discontinuity = startx != lastx or starty != lasty
        for t in ts:
            point = segment.point(t)
            points.append(
                (point.real * xscale + xoff, point.imag * yscale + yoff, discontinuity)
            )

            discontinuity = False
        lastx, lasty = endx, endy

    # print (repr(points), file=sys.stderr)
    return points


from svgpathtools import Line


def render_fill(path, job, cal, settings, args, fill_color):
    print(
        "$FILL", path.bbox(), path.iscontinuous() and path.isclosed(), file=sys.stderr
    )
    brush = settings.get(fill_color)
    xmin, xmax, ymin, ymax = path.bbox()
    job.change_settings(*brush[:3])
    # TODO - multiple hatch patterns, pay attention to hatch angle, etc
    hatch_x = np.linspace(
        xmin - 0.1,
        xmax + 0.1,
        int(round((0.2 + xmax - xmin) / (float(brush[4]) / 1000.0))),
    )
    sys.stderr.write(("|" * (len(hatch_x) // 50)) + "\n")
    sys.stderr.flush()
    for n, x in enumerate(hatch_x):
        if not n % 50:
            sys.stderr.write(".")
            sys.stderr.flush()
        line = Line(complex(x, ymin - 0.1), complex(x, ymax + 0.1))

        try:
            base_intersects = path.intersect(line)
        except ValueError:
            print("Caution - ValueError in intersect calculation.", file=sys.stderr)
            continue
        intersects = []
        for ((_, seg, t0), (_, _, t1)) in base_intersects:
            p0 = line.point(t1)
            x0, y0 = p0.real, p0.imag
            intersects.append((x0, y0))

        intersects.sort()

        for (x0, y0), (x1, y1) in zip(intersects[::2], intersects[1::2]):
            job.append(balor.MSBF.OpJumpTo(*cal.interpolate(x0, y0)))
            job.laser_control(True)
            job.line(x0, y0, x1, y1)
            job.laser_control(False)
            # print("$$", x0,y0, ",", x1,y1, file=sys.stderr)
    print("... done.", file=sys.stderr)

    # job.change_settings(*settings.get(fill_color))


def render_svg(*args):
    if args.operation == "mark":
        render_svg_mark(*args)
    else:
        render_svg_light(*args)


def render_svg_light(svg, job, cal, args, settings):
    paths, attributes, svg_attributes = svg

    travel_speed = int(round(args.travel_speed / 2.0))  # units are 2mm/sec

    job.add_light_prefix(travel_speed=travel_speed)
    job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))
    begin = job.get_position()
    for path, attribute in zip(paths, attributes):
        print("begin", attribute.get("id", "no id"), file=sys.stderr)
        stroke_color = None
        if "style" in attribute:
            style = attribute["style"].split(";")
            for atr in style:
                if not atr or not ":" in atr:
                    continue
                k, v = atr.split(":")
                # If this is failing, I guess it's because your svg program
                # does something different from Inkscape. Send me a patch:
                if k == "fill":
                    fill_color = None if v == "none" else int(v[1:], 16)
                elif k == "stroke":
                    stroke_color = None if v == "none" else int(v[1:], 16)

        if stroke_color is not None:
            print(
                "rendering lighting stroke of",
                attribute.get("id", "no id"),
                file=sys.stderr,
            )
            length = path.length()
            ts = np.linspace(0, 1, int(round(path.length() / args.segment_length)))
            points = [
                (c.real * args.xscale + args.xoff, c.imag * args.yscale + args.yoff)
                for c in [path.point(t) for t in ts]
            ]
            ix, iy = points[0]
            job.append(balor.MSBF.OpJumpTo(*cal.interpolate(*points[0])))
            for x, y in points[1:]:
                job.line(ix, iy, x, y, Op=balor.MSBF.OpJumpTo)
                ix, iy = x, y
        print("finished", attribute.get("id", "no id"), file=sys.stderr)

    end = job.get_position()
    print(
        "Adding %d repetitions %d:%d" % (args.repetition, begin, end + 1),
        file=sys.stderr,
    )
    if args.repetition > 1:
        job.duplicate(begin, end + 1, args.repetition - 1)
    print("Length of operations", len(job.operations), file=sys.stderr)
    job.append(balor.MSBF.OpJumpTo(*cal.interpolate(0.0, 0.0)))
    job.calculate_distances()


def render_svg_mark(svg, job, cal, args, settings):
    paths, attributes, svg_attributes = svg

    travel_speed = int(round(args.travel_speed / 2.0))  # units are 2mm/sec
    cut_speed = int(round(args.cut_speed / 2.0))
    laser_power = int(round(args.laser_power * 40.95))
    q_switch_period = int(round(1.0 / (args.q_switch_frequency * 1e3) / 50e-9))

    job.add_mark_prefix(
        travel_speed=travel_speed,
        laser_power=laser_power,
        q_switch_period=q_switch_period,
        cut_speed=cut_speed,
    )
    job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))
    for path, attribute in zip(paths, attributes):
        print("begin", attribute.get("id", "no id"), file=sys.stderr)
        fill_color = None
        stroke_color = None
        if "style" in attribute:
            style = attribute["style"].split(";")
            for atr in style:
                if not atr or not ":" in atr:
                    continue
                k, v = atr.split(":")
                # If this is failing, I guess it's because your svg program
                # does something different from Inkscape. Send me a patch:
                if k == "fill":
                    fill_color = None if v == "none" else int(v[1:], 16)
                elif k == "stroke":
                    stroke_color = None if v == "none" else int(v[1:], 16)
        # print ("fill: %06X"%fill_color if fill_color is not None else "no fill", file=sys.stderr)
        # print ("path: %06X"%stroke_color if stroke_color is not None else "no path",
        #        file=sys.stderr)
        if fill_color != None and args.operation == "mark":
            print(
                "rendering hatching of", attribute.get("id", "no id"), file=sys.stderr
            )
            render_fill(path, job, cal, settings, args, fill_color)
        if stroke_color != None:
            print(
                "rendering marking stroke of",
                attribute.get("id", "no id"),
                file=sys.stderr,
            )
            length = path.length()
            points = separate_points(
                path,
                args.segment_length,
                args.xscale,
                args.yscale,
                args.xoff,
                args.yoff,
            )
            # points = [(c.real*args.xscale + args.xoff,c.imag*args.yscale + args.yoff
            #                        ) for c in [path.point(t) for t in ts]]
            job.change_settings(*settings.get(stroke_color)[:3])
            print("Path", len(path), len(points), repr(path), file=sys.stderr)
            for _ in range(settings.get(stroke_color)[6]):
                job.laser_control(True)
                ix, iy, _ = points[0]
                try:
                    job.append(balor.MSBF.OpJumpTo(*cal.interpolate(ix, iy)))
                except ValueError:
                    print("Not including this stroke path:", path, file=sys.stderr)
                    break
                for x, y, discon in points[1:]:
                    if discon:
                        job.laser_control(False)
                        job.append(balor.MSBF.OpJumpTo(*cal.interpolate(x, y)))
                        job.laser_control(True)
                    else:
                        job.line(ix, iy, x, y)
                    ix, iy = x, y
                job.laser_control(False)
        print("finished", attribute.get("id", "no id"), file=sys.stderr)
    job.append(balor.MSBF.OpJumpTo(*cal.interpolate(0.0, 0.0)))
    job.calculate_distances()


class MachineSettings:
    def __init__(self, args):
        self.settings = {}
        # add default settings
        self.add(
            0,
            cut_speed=int(round(args.cut_speed / 2.0)),
            laser_power=int(round(args.laser_power * 40.95)),
            q_switch_period=int(round(1.0 / (args.q_switch_frequency * 1e3) / 50e-9)),
            repeats=args.repetition,
            hatch_angle=90.0,
            hatch_spacing=40.0,
            hatch_pattern=None,
        )

    def add(
        self,
        color,
        cut_speed,
        laser_power,
        q_switch_period,
        repeats,
        hatch_angle,
        hatch_spacing,
        hatch_pattern,
    ):
        self.settings[color] = (
            q_switch_period,
            laser_power,
            cut_speed,
            hatch_angle,
            hatch_spacing,
            hatch_pattern,
            repeats,
        )

        print(
            "Pen 0x%06X:" % color,
            "qs_period=0x%04X; laser_power=0x%04X; cut_speed=0x%04X;\n\thatch_angle=%.2f deg; hatch_spacing=%.2f um; hatch_pattern='%s';\n\trepeats=%d"
            % self.settings[color],
            file=sys.stderr,
        )

    def get(self, color=0):
        return self.settings.get(color, self.settings[0])

    def mine_settings(self, data):
        i = 0
        while i < len(data):
            i = data.find("!pen", i)
            j = data.find("</", i)
            if i == -1 or j == -1:
                break
            setting = data[i:j].split()[1:]
            self.add(
                int(setting[0], 16),
                laser_power=int(round(float(setting[2]) * 40.95)),
                q_switch_period=int(round(1.0 / (float(setting[1]) * 1e3) / 50e-9)),
                cut_speed=int(round(float(setting[3]) / 2.0)),
                repeats=int(setting[7]),
                hatch_angle=float(setting[4]),
                hatch_spacing=float(setting[5]),
                hatch_pattern=setting[6],
            )
            i = j + 1

    def add_csv(self, data):
        for line in data.split("\n"):
            line = line.strip()
            if not line or line[0] == "#":
                continue
            setting = line.split()
            self.add(
                int(setting[0], 16),
                laser_power=int(round(float(setting[2]) * 40.95)),
                q_switch_period=int(round(1.0 / (float(setting[1]) * 1e3) / 50e-9)),
                cut_speed=int(round(float(setting[3]) / 2.0)),
                repeats=int(setting[7]),
                hatch_angle=float(setting[4]),
                hatch_spacing=float(setting[5]),
                hatch_pattern=setting[6],
            )


from svgpathtools import svg2paths2

import sys

in_file = svg2paths2(args.file)

if args.output is None:
    out_file = sys.stdout.buffer
else:
    out_file = open(args.output, "wb")

import balor.MSBF, balor.Cal

cal = balor.Cal.Cal(args.calfile)
settings = MachineSettings(args)
if args.settings:
    settings.add_csv(open(args.settings, "r").read())
settings.mine_settings(open(args.file, "r").read())

job = balor.MSBF.JobFactory(args.machine)
job.cal = cal

render_svg(in_file, job, cal, args, settings)

out_file.write(job.serialize())
