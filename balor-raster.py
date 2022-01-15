#!/usr/bin/env python3
import balor
import sys, argparse, os, io, pickle

parser = argparse.ArgumentParser(description='''
Tool to convert raster images to the machine-specific binary format used
by Beijing JCZ galvo-based laser engravers.
This program produces raw bytestreams that can be sent by balor.''',
epilog='''
NOTE: This software is EXPERIMENTAL and has only been tested with a
single machine. There are many different laser engraving machines 
and the fact that they look the same, or even have the same markings,
is not proof that they are really the same.''')

parser.add_argument('operation', 
        help="choose operational mode", default="light", choices=["mark", "light"])

parser.add_argument('-f', '--file', 
        help="filename to load, in an image format supported by Pillow.", default=None)

parser.add_argument('-o', '--output', 
    help="Specify the output file. (default stdout)",
    default=None)

parser.add_argument('-c', '--calfile',
    help="Provide a calibration file for the machine.")

parser.add_argument('-m', '--machine', 
        help="specify which machine interface to use. Valid machines: "+', '.join(
            [x.__name__ for x in balor.all_known_machines]), default="BJJCZ_LMCV4_FIBER_M")

parser.add_argument('--travel-speed',
    help="Specify the traveling speed (mm/s)",
    default=2000, type=float)
parser.add_argument('--cut-speed',
    help="Specify the cutting speed (mm/s)",
    default=500, type=float)
parser.add_argument('--laser-power',
    help="Specify the laser power in percentage.",
    default=50, type=float)
parser.add_argument('--q-switch-frequency',
    help="Specify the q switch frequency in KHz",
    default=30.0, type=float)

parser.add_argument('--raster-x-res',
    help="X resolution (in mm) of the laser.",
    default=0.15, type=float)
parser.add_argument('--raster-y-res',
    help="X resolution (in mm) of the laser.",
    default=0.15, type=float)

parser.add_argument('-x', '--xoffs',
    help="Specify an x offset for the image (mm.)",
    default=0.0, type=float)

parser.add_argument('-y', '--yoffs',
    help="Specify an y offset for the image (mm.)",
    default=0.0, type=float)
parser.add_argument('-d', '--dither',
    help="Configure dithering",
    default=0.1, type=float)
parser.add_argument('-s', '--scale',
    help="Pixels per mm (default 23.62 px/mm - 600 DPI)",
    default=23.622047, type=float)
parser.add_argument('-t', '--threshold',
    help="Greyscale threshold for burning (default 0.5, negative inverts)",
    default=0.5, type=float)

parser.add_argument('-g', '--grayscale',
    help="Greyscale rastering (power, speed, q_switch_frequency, passes)",
    default=False , type=None)

parser.add_argument('--grayscale-min',
    help="Minimum (black=1) value of the gray scale",
    default=None , type=float)
parser.add_argument('--grayscale-max',
    help="Maximum (white=255) value of the gray scale",
    default=None , type=float)

   
args = parser.parse_args()


import sys
from PIL import Image
if args.file is None:
    in_file = Image.open(sys.stdin.buffer)
else:
    in_file = Image.open(args.file)

import numpy as np
import scipy
import scipy.interpolate
def raster_render(job, cal, in_file, out_file, args):
    width = in_file.size[0] / args.scale
    height = in_file.size[1] / args.scale
    x0,y0 = args.xoffs, args.yoffs

    invert = False
    threshold = args.threshold
    if threshold < 0:
        invert = True
        threshold *= -1.0
    dither = 0
    passes = 1
    # approximate scale for speeds
    #ap_x_scale = cal.interpolate(10.0, 10.0)[0] - cal.interpolate(-10.0, -10.0)[0]
    #ap_y_scale = cal.interpolate(10.0, 10.0)[1] - cal.interpolate(-10.0, -10.0)[1]
    #ap_scale = (ap_x_scale+ap_y_scale)/20.0
    #print ("Approximate scale", ap_scale, "units/mm", file=sys.stderr)
    travel_speed = int(round(args.travel_speed / 2.0)) # units are 2mm/sec
    cut_speed = int(round(args.cut_speed / 2.0))
    laser_power = int(round(args.laser_power * 40.95))
    q_switch_period = int(round(1.0/(args.q_switch_frequency*1e3) / 50e-9))
    print ("Image size: %.2f mm x %.2f mm"%(width,height), file=sys.stderr)
    print ("Travel speed 0x%04X"%travel_speed, file=sys.stderr)
    print ("Cut speed 0x%04X"%cut_speed, file=sys.stderr)
    print ("Q switch period 0x%04X"%q_switch_period, file=sys.stderr)
    print ("Laser power 0x%04X"%laser_power, file=sys.stderr)

    if args.grayscale:
        gsmin = (args.grayscale_min)
        gsmax = (args.grayscale_max)
        gsslope = (gsmax-gsmin)/256.0

    job.cal = cal

    img = scipy.interpolate.RectBivariateSpline(
            np.linspace(y0, y0+height, in_file.size[1]),
            np.linspace(x0, x0+width, in_file.size[0]),
            np.asarray(in_file))

    if args.operation == 'light':
        job.add_light_prefix(travel_speed = travel_speed)
        for _ in range(32):
            job.line(x0, y0, x0+width, y0, Op=balor.MSBF.OpTravel)
            job.line(x0+width, y0, x0+width, y0+height, Op=balor.MSBF.OpTravel)
            job.line(x0+width, y0+height, x0, y0+height, Op=balor.MSBF.OpTravel)
            job.line(x0, y0+height, x0, y0, Op=balor.MSBF.OpTravel)
    else: # mark
        dither = 0
        job.add_mark_prefix(travel_speed = travel_speed,
                            laser_power=laser_power,
                            q_switch_period = q_switch_period,
                            cut_speed = cut_speed)
        y = y0
        count = 0
        burning = False
        old_y = y0
        while y < y0+height:
            x = x0
            job.append(balor.MSBF.OpTravel(*cal.interpolate(x,y)))
            old_x = x0
            while x < x0+width:
                px = img(y,x)[0][0]
                if invert: px = 255.0 - px

                if args.grayscale:
                    if px > 0:
                        gsval = gsmin + gsslope*px
                        if args.grayscale == 'power':
                            job.change_laser_power(gsval)
                        elif args.grayscale == 'speed':
                            job.change_cut_speed(gsval)
                        elif args.grayscale == 'q_switch_frequency':
                            job.change_q_switch_frequency(gsval)
                        elif args.grayscale == 'passes': 
                            passes = int(round(gsval))
                            # Would probably be better to do this over the course of multiple
                            # rasters for heat disappation during 2.5D engraving
                        #pp = int(round((int(px)/255) * args.laser_power * 40.95))
                        #job.change_settings(q_switch_period, pp, cut_speed)

                        if not burning:
                            job.laser_control(True) # laser turn on
                        i = passes
                        while i > 1:
                            job.append(balor.MSBF.OpCut(*cal.interpolate(x, y)))
                            job.append(balor.MSBF.OpCut(*cal.interpolate(old_x, old_y)))
                            i -= 2
                        job.append(balor.MSBF.OpCut(*cal.interpolate(x, y)))
                        burning=True

                    else:
                        if burning:
                            # laser turn off
                            job.laser_control(False)
                        job.append(balor.MSBF.OpTravel(*cal.interpolate(x,y)))
                        burning=False
                else:

                    if px+dither > threshold:
                        if not burning:
                            job.laser_control(True) # laser turn on
                        job.append(balor.MSBF.OpCut(*cal.interpolate(x, y)))
                        burning=True
                        dither = 0.0
                    else:
                        if burning:
                            # laser turn off
                            job.laser_control(False)
                        job.append(balor.MSBF.OpTravel(*cal.interpolate(x,y)))
                        dither += abs(px+dither-threshold)*args.dither
                        burning=False
                old_x = x
                x += args.raster_x_res
            if burning:
                # laser turn off
                job.laser_control(False)
                burning=False

            old_y = y
            y += args.raster_y_res
            count += 1
            if not (count % 20): print ("\ty = %.3f"%y, file=sys.stderr)



    job.calculate_distances()

if args.output is None:
    out_file = sys.stdout.buffer
else:
    out_file = open(args.output, 'wb')

import balor.MSBF, balor.Cal
cal = balor.Cal.Cal(args.calfile)
job = balor.MSBF.JobFactory(args.machine)
raster_render(job, cal, in_file, out_file, args)

out_file.write(job.serialize())
