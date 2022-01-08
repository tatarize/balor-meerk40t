#!/usr/bin/env python3
import balor
import sys, argparse, os, io, pickle

parser = argparse.ArgumentParser(
    description="""
Tool to convert gcode to the machine-specific binary format used by Beijing 
JCZ galvo-based laser engravers. This program produces raw bytestreams that 
can be sent by balor. The gcode should be substantially 2D, as the machine 
being below Z0 is interpreted as "laser on" and above Z0 (positive Z) is 
interpreted as "laser off." The main compatibility target is the output of
FlatCAM.""",
    epilog="""
NOTE: This software is EXPERIMENTAL and has only been tested with a
single machine. There are many different laser engraving machines 
and the fact that they look the same, or even have the same markings,
is not proof that they are really the same.""",
)

parser.add_argument(
    "operation",
    help="choose operational mode (in lighting mode, a bounding box will be drawn with crosshairs at 0,0.)",
    default="light",
    choices=["mark", "light"],
)

parser.add_argument(
    "-f", "--file", help="gcode / ngc file to load (default stdin).", default=None
)

parser.add_argument(
    "-o", "--output", help="Specify the output file. (default stdout)", default=None
)

parser.add_argument(
    "-c", "--calfile", help="Provide a calibration file for the machine."
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
    "--cut-speed", help="Specify the cutting speed (mm/s)", default=800, type=float
)
parser.add_argument(
    "--laser-power",
    help="Specify the laser power in percentage.",
    default=80,
    type=float,
)
parser.add_argument(
    "--q-switch-frequency",
    help="Specify the q switch frequency in KHz",
    default=30.0,
    type=float,
)
parser.add_argument(
    "--repetition",
    "-r",
    help="Specify the number of passes. The file will be repeated from the first G00 movement.",
    default=10,
    type=int,
)

args = parser.parse_args()


def render_gcode_bounding(gfile, job, cal, args):
    travel_speed = int(round(args.travel_speed / 2.0))  # units are 2mm/sec
    print("Travel speed 0x%04X" % travel_speed, file=sys.stderr)
    job.add_light_prefix(travel_speed=travel_speed)
    x, y, z = 0.0, 0.0, 0.0
    xmax, xmin, ymax, ymin = 0, 0, 0, 0
    metric_specified = False
    first_step = None
    burning = False
    i = 0
    while i < len(gfile.lines):
        line = gfile.lines[i]
        if line.comment:
            print("#", line.comment, file=sys.stderr)
        code, index = line.command
        params = line.params
        if code == "G":
            if index == 0:
                if first_step is None:
                    first_step = i
                # Rapid travel
                if "Z" in params:
                    z = params["Z"]
                    if burning and z >= 0:
                        # Stop laser
                        job.laser_control(False)
                    elif not burning and z < 0:
                        # Start laser
                        job.laser_control(True)
                else:
                    x = params["X"] if "X" in params else x
                    y = params["Y"] if "Y" in params else y
                if burning and x > xmax:
                    xmax = x
                if burning and x < xmin:
                    xmin = x
                if burning and y > ymax:
                    ymax = y
                if burning and y < ymin:
                    ymin = y
            elif index == 1:
                if first_step is None:
                    first_step = i
                if "Z" in params:
                    z = params["Z"]
                    if burning and z >= 0:
                        # Stop laser
                        burning = False
                    elif not burning and z < 0:
                        # Start laser
                        burning = True
                else:
                    x = params["X"] if "X" in params else x
                    y = params["Y"] if "Y" in params else y
                if burning and x > xmax:
                    xmax = x
                if burning and x < xmin:
                    xmin = x
                if burning and y > ymax:
                    ymax = y
                if burning and y < ymin:
                    ymin = y

                # Cut
            elif index == 4:  # dwell
                # delay = params['P']
                # Probably not useful to actually do this
                # job.append(balor.MSBF.OpWait(delay*1e6))
                pass
            elif index == 90:
                absolute = True
            elif index == 91:
                absolute = False
            elif index == 20:
                print(
                    "Error: Probably using the wrong units. (G20, should be G21)",
                    file=sys.stderr,
                )
                sys.exit(-20)
            elif index == 21:
                metric_specified = True
            elif index == 94:
                pass  # print (params, file=sys.stderr)
            else:
                print(
                    "Error: unknown gcode: %s%d" % (code, index),
                    params,
                    file=sys.stderr,
                )
                sys.exit(-1)
        elif code == "M":
            if index == 0:
                if not repetition:
                    break  # program stop
            elif index in [3, 4]:
                pass  # Ignore spindle
        else:  # code == 'F':
            print("Unknown code %s%d" % (code, index), params, file=sys.stderr)
            # travel_speed = int(round(params['F'] / (64*2.0)))
        i += 1

    job.append(balor.MSBF.OpJumpTo(*cal.interpolate(0.0, 0.0)))

    print(
        "Bounding box: (%.2f, %.2f), (%.2f, %.2f)" % (xmin, ymin, xmax, ymax),
        file=sys.stderr,
    )
    job.append(balor.MSBF.OpJumpTo(*cal.interpolate(xmin, ymin)))
    for _ in range(args.repetition):
        job.append(balor.MSBF.OpJumpTo(*cal.interpolate(xmax, ymin)))
        job.append(balor.MSBF.OpJumpTo(*cal.interpolate(xmax, ymax)))
        job.append(balor.MSBF.OpJumpTo(*cal.interpolate(xmin, ymax)))
        job.append(balor.MSBF.OpJumpTo(*cal.interpolate(xmin, ymin)))

    job.calculate_distances()

    if not metric_specified:
        print("Warning - Metric units were not specified.", file=sys.stderr)


def render_gcode(gfile, job, cal, args):
    x, y, z = 0.0, 0.0, 0.0
    burning = False
    absolute = False
    xmax, xmin, ymax, ymin = 0, 0, 0, 0
    metric_specified = False
    first_step = None
    repetition = args.repetition

    travel_speed = int(round(args.travel_speed / 2.0))  # units are 2mm/sec
    cut_speed = int(round(args.cut_speed / 2.0))
    laser_power = int(round(args.laser_power * 40.95))
    q_switch_period = int(round(1.0 / (args.q_switch_frequency * 1e3) / 50e-9))

    print("Travel speed 0x%04X" % travel_speed, file=sys.stderr)
    print("Cut speed 0x%04X" % cut_speed, file=sys.stderr)
    print("Q switch period 0x%04X" % q_switch_period, file=sys.stderr)
    print("Laser power 0x%04X" % laser_power, file=sys.stderr)

    # Add prefix
    job.add_mark_prefix(
        travel_speed=travel_speed,
        laser_power=laser_power,
        q_switch_period=q_switch_period,
        cut_speed=cut_speed,
    )

    i = 0
    while i < len(gfile.lines):
        line = gfile.lines[i]
        if line.comment:
            print("#", line.comment, file=sys.stderr)
        code, index = line.command
        params = line.params
        if code == "G":
            if index == 0:
                if first_step is None:
                    first_step = i
                # Rapid travel
                if "Z" in params:
                    z = params["Z"]
                    if burning and z >= 0:
                        # Stop laser
                        job.laser_control(False)
                        burning = False
                    elif not burning and z < 0:
                        # Start laser
                        job.laser_control(True)
                        burning = True
                else:
                    x = params["X"] if "X" in params else x
                    y = params["Y"] if "Y" in params else y
                job.append(balor.MSBF.OpJumpTo(*cal.interpolate(x, y)))
                if burning and x > xmax:
                    xmax = x
                if burning and x < xmin:
                    xmin = x
                if burning and y > ymax:
                    ymax = y
                if burning and y < ymin:
                    ymin = y
            elif index == 1:
                if first_step is None:
                    first_step = i
                if "Z" in params:
                    z = params["Z"]
                    if burning and z >= 0:
                        # Stop laser
                        job.laser_control(False)
                    elif not burning and z < 0:
                        # Start laser
                        job.laser_control(True)
                else:
                    x = params["X"] if "X" in params else x
                    y = params["Y"] if "Y" in params else y
                if burning and x > xmax:
                    xmax = x
                if burning and x < xmin:
                    xmin = x
                if burning and y > ymax:
                    ymax = y
                if burning and y < ymin:
                    ymin = y

                # Cut
                job.append(balor.MSBF.OpMarkTo(*cal.interpolate(x, y)))
            elif index == 4:  # dwell
                # delay = params['P']
                # Probably not useful to actually do this
                # job.append(balor.MSBF.OpWait(delay*1e6))
                pass
            elif index == 90:
                absolute = True
            elif index == 91:
                absolute = False
            elif index == 20:
                print(
                    "Error: Probably using the wrong units. (G20, should be G21)",
                    file=sys.stderr,
                )
                sys.exit(-20)
            elif index == 21:
                metric_specified = True
            elif index == 94:
                pass  # print (params, file=sys.stderr)
            else:
                print(
                    "Error: unknown gcode: %s%d" % (code, index),
                    params,
                    file=sys.stderr,
                )
                sys.exit(-1)
        elif code == "M":
            if index == 0:
                if not repetition:
                    break  # program stop
            elif index in [3, 4]:
                pass  # Ignore spindle
        else:  # code == 'F':
            print("Unknown code %s%d" % (code, index), params, file=sys.stderr)
            # travel_speed = int(round(params['F'] / (64*2.0)))
        i += 1
        if i == len(gfile.lines) and repetition:
            repetition -= 1
            print(
                "Repetition %d/%d" % (args.repetition - repetition, args.repetition),
                file=sys.stderr,
            )
            i = first_step

    if burning:
        # laser turn off
        job.laser_control(False)
        burning = False
    job.append(balor.MSBF.OpJumpTo(*cal.interpolate(0.0, 0.0)))
    job.calculate_distances()

    if not metric_specified:
        print("Warning - Metric units were not specified.", file=sys.stderr)


from gcodeparser import GcodeParser
import sys

if args.file is None:
    in_file = GcodeParser(sys.stdin.read())
else:
    in_file = GcodeParser(open(args.file, "r").read())

if args.output is None:
    out_file = sys.stdout.buffer
else:
    out_file = open(args.output, "wb")

import balor.MSBF, balor.Cal

cal = balor.Cal.Cal(args.calfile)
job = balor.MSBF.JobFactory(args.machine)

if args.operation == "mark":
    render_gcode(in_file, job, cal, args)
else:
    render_gcode_bounding(in_file, job, cal, args)

out_file.write(job.serialize())
