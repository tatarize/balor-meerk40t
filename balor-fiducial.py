#!/usr/bin/env python3
import balor
import sys, argparse, os, io, pickle


parser = argparse.ArgumentParser(description='''
Tool drill fiducial marks for double-sided processing of materials, e.g. for
double-sized PCBs. The general process here is to move the workpiece around
on the bed of the machine and drill three holes, forming approximately a 
right triangle. Then an alignment file can be produced by balor-align, and
the alignment can be used with the other balor programs (ngc, svg, raster,
and so forth.)''',
epilog='''
NOTE: This software is EXPERIMENTAL and has only been tested with a
single machine. There are many different laser engraving machines 
and the fact that they look the same, or even have the same markings,
is not proof that they are really the same.''')



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
    default=200, type=float)
parser.add_argument('--cut-speed',
    help="Specify the cutting speed (mm/s)",
    default=100, type=float)
parser.add_argument('--size',
    help="Specify the size of the fiducial mark (micrometers)",
    default=250, type=float)
parser.add_argument('--gap',
    help="Specify the size of the gap separating the axes of the fiducial (micrometers)",
    default=50, type=float)
parser.add_argument('--wait',
    help="Wait time between steps for cooldown between groups (ms)",
    default=50, type=float)

parser.add_argument('-x',
    help="Specify the x position (mm) default 0",
    default=0, type=float)
parser.add_argument('-y',
    help="Specify the y position (mm) default 0",
    default=0, type=float)
parser.add_argument('--laser-power', '-p',
    help="Specify the laser power in percentage.",
    default=70, type=float)
parser.add_argument('--q-switch-frequency', '-q',
    help="Specify the q switch frequency in KHz",
    default=30.0, type=float)
parser.add_argument('--repetition', '-r',
    help="Specify the number of passes in a group. ",
    default=8, type=int)
parser.add_argument('--groups', '-g',
    help="Specify the number of groups of passes.  ",
    default=18, type=int)


def render_fiducial(job, cal, args):
    laser_power = int(round(args.laser_power * 40.95))
    q_switch_period = int(round(1.0/(args.q_switch_frequency*1e3) / 50e-9))
    travel_speed = int(round(args.travel_speed / 2.0)) # units are 2mm/sec
    cut_speed = int(round(args.cut_speed / 2.0))
    wait_time = int(round(args.wait * 1e3))
    print ("Q switch period 0x%04X"%q_switch_period, file=sys.stderr)
    print ("Laser power 0x%04X"%laser_power, file=sys.stderr)
    print ("Travel speed 0x%04X"%travel_speed, file=sys.stderr)
    print ("Cut speed 0x%04X"%cut_speed, file=sys.stderr)
    # Add prefix
    job.add_mark_prefix(travel_speed = travel_speed,
                            laser_power=laser_power,
                            q_switch_period = q_switch_period,
                            cut_speed=cut_speed)
    job.append(balor.MSBF.OpJumpTo(*cal.interpolate(args.x, args.y)))

    xmin,ymin = cal.interpolate(args.x - args.size*1e-3/2,args.y - args.size*1e-3/2)
    xmax,ymax = cal.interpolate(args.x + args.size*1e-3/2,args.y + args.size*1e-3/2)
    # Cut the X line
    job.append(balor.MSBF.OpJumpTo(xmin, ymin))
    for _ in range(args.groups):
        job.laser_control(True)
        for __ in range(args.repetition):
            job.append(balor.MSBF.OpMarkTo(xmin, ymax, 0x8000))
            job.append(balor.MSBF.OpMarkTo(xmax, ymax, 0x8000))
            job.append(balor.MSBF.OpMarkTo(xmax, ymin, 0x8000))
            job.append(balor.MSBF.OpMarkTo(xmin, ymin, 0x8000))
        job.laser_control(False)
        job.append(balor.MSBF.OpMarkEndDelay(wait_time))
    job.append(balor.MSBF.OpAltTravel(0x0008))
    job.append(balor.MSBF.OpJumpTo(*cal.interpolate(args.x, args.y)))
    

       

    job.append(balor.MSBF.OpJumpTo(*cal.interpolate(0.0, 0.0)))
    
    for _ in range(200): job.append(balor.MSBF.OpMarkEndDelay(0x100))
    job.append(balor.MSBF.OpAltTravel(0x0008))
    job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))
    job.calculate_distances()


import sys
args = parser.parse_args()
if args.output is None:
    out_file = sys.stdout.buffer
else:
    out_file = open(args.output, 'wb')

import balor.MSBF, balor.Cal
cal = balor.Cal.Cal(args.calfile)
job = balor.MSBF.JobFactory(args.machine)

render_fiducial(job, cal, args)

out_file.write(job.serialize())
