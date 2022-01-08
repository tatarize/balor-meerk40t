#!/usr/bin/env python3
import balor
import sys, argparse, os, io, pickle

parser = argparse.ArgumentParser(description='''
Tool to produce test patterns in the machine-specific binary format used
by Beijing JCZ galvo-based laser engravers.
This program produces raw bytestreams that can be sent by balor.''',
epilog='''
NOTE: This software is EXPERIMENTAL and has only been tested with a
single machine. There are many different laser engraving machines 
and the fact that they look the same, or even have the same markings,
is not proof that they are really the same.''')
parser.add_argument('-m', '--machine', 
        help=("specify which machine protocol to use. Valid machines: "
            +', '.join([x.__name__ for x in balor.all_known_machines])), 
        default="BJJCZ_LMCV4_FIBER_M")


parser.add_argument('-o', '--output', 
    help="Specify the output file. (default stdout)",
    default=None)

parser.add_argument('-t', '--type',
    help="Specify the pattern type (grid, parameters)",
    default="grid", )

parser.add_argument('--calfile',
    help="Provide a calibration file for patterns that use one.")

parser.add_argument('--cut-speed',
    help="Specify the cutting speed (uncalibrated units)",
    default=100, type=int)
parser.add_argument('--q-switch-period',
    help="Specify the q switch period in uncalibrated units",
    default=667, type=int)
parser.add_argument('--travel-speed',
    help="Specify the traveling speed (uncalibrated units)",
    default=500, type=int)
parser.add_argument('--laser-power',
    help="Specify the laser power in uncalibrated units",
    default=2048, type=int)


parser.add_argument('-x', '--xparam',
    help="Specify the parameter to be varied in x",
    default="cutting_speed")
parser.add_argument('-y', '--yparam',
    help="Specify the parameter to be varied in y",
    default="cutting_speed")
parser.add_argument('--xmin',
    help="Specify the minimum parameter value for x",
    default=0, type=int)
parser.add_argument('--xmax',
    help="Specify the maximum parameter value for x",
    default=0x10000, type=int)
parser.add_argument('--ymin',
    help="Specify the minimum parameter value for y",
    default=0, type=int)
parser.add_argument('--ymax',
    help="Specify the maximum parameter value for y",
    default=0x10000, type=int)
parser.add_argument('--xsteps',
    help="How many steps in x?",
    default=0, type=int)
parser.add_argument('--ysteps',
    help="How many steps in y?",
    default=0, type=int)
parser.add_argument('-c', '--cell',
    help="Gird or parameter cell size in native/galvo units",
    default=0x10000//0x40, type=int)
parser.add_argument('operation', 
        help="choose operational mode", default="light", choices=["mark", "light"])




args = parser.parse_args()

#################
import balor.MSBF

class TestPattern:
    name = 'test'
    def __init__(self, args, job):
        self.args = args
        self.job = job
    
        if args.operation == 'light':
            self.add_light_prefix()
        elif args.operation == 'mark':
            self.add_mark_prefix()


        


    def add_light_prefix(self):
        self.job.extend([
                balor.MSBF.OpReadyMark(),
                balor.MSBF.OpJumpSpeed(self.args.travel_speed),
                balor.MSBF.OpAltTravel(0x0008),
            ])

    def laser_power(self, on):
        if on:
            self.job.extend([
                balor.MSBF.OpLaserControl(0x0001),
                balor.MSBF.OpMarkEndDelay(0x0320),
            ])
        else:
            self.job.extend([
                balor.MSBF.OpMarkEndDelay(0x001E),
                balor.MSBF.OpLaserControl(0x0000),
            ])


    def add_mark_prefix(self):
        self.job.extend([
                balor.MSBF.OpReadyMark(),
                balor.MSBF.OpSetQSwitchPeriod(self.args.q_switch_period),
                balor.MSBF.MarkPowerRatio(self.args.laser_power),
                balor.MSBF.OpJumpSpeed(self.args.travel_speed),
                balor.MSBF.OpMarkSpeed(self.args.cut_speed),
                balor.MSBF.OpLaserOnDelay(0x0064, 0x8000),
                balor.MSBF.OpLaserOffDelay(0x0064),
                balor.MSBF.OpPolygonDelay(0x000A),
                balor.MSBF.OpAltTravel(0x0008),
            ])

class OldGridPattern(TestPattern):
    name='oldgrid'
    def render(self):
        marking = args.operation == 'mark'
        Op = balor.MSBF.OpMarkTo if marking else balor.MSBF.OpJumpTo
        xmin, xmax, ymin, ymax = args.xmin, args.xmax, args.ymin, args.ymax
        cell_size = self.args.cell

        if marking and ymin > cell_size and xmin > cell_size:
            fiducial_size = cell_size // 3
            fiducial_offset = cell_size // 5
            # Make a square marking at 0,0
            self.job.append(balor.MSBF.OpJumpTo(ymin + fiducial_offset, xmin + fiducial_offset))
            self.laser_power(True)
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset,
                                                xmin + fiducial_offset + fiducial_size))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset + fiducial_size,
                                                xmin + fiducial_offset + fiducial_size))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset + fiducial_size,
                                                xmin + fiducial_offset))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset,
                                                xmin + fiducial_offset))
            self.laser_power(False)
            # Make a triangle at max X
            self.job.append(balor.MSBF.OpJumpTo(ymin + fiducial_offset,
                                                xmax - fiducial_offset))
            self.laser_power(True)
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset,
                                                xmax - fiducial_offset + fiducial_size))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset + fiducial_size,
                                                xmax - fiducial_offset + fiducial_size))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset,
                                                xmax - fiducial_offset))
            self.laser_power(False)
        # getting rid of either the x or y lines makes it stop working
        # as does using too large a grid size
        # long packet is played back successfully
        # short packet is not

        x = xmin
        while x < xmax:
            self.job.append(balor.MSBF.OpJumpTo(ymin, x))
            if marking: self.laser_power(True)
            self.job.append(           Op(ymax-1, x))
            if marking: self.laser_power(False)            
            if x+cell_size >= xmax: break
            self.job.append(balor.MSBF.OpJumpTo(ymax - 1, x + cell_size))
            if marking: self.laser_power(True)            
            self.job.append(           Op(ymin, x+cell_size))
            if marking: self.laser_power(False)            
            x += cell_size*2

        y = ymin
        while y < ymax:
            self.job.append(balor.MSBF.OpJumpTo(y, xmin))
            if marking: self.laser_power(True)
            self.job.append(           Op(y, xmax-1))
            if marking: self.laser_power(False)
            if y+cell_size >= ymax: break
            self.job.append(balor.MSBF.OpJumpTo(y + cell_size, xmax - 1))
            if marking: self.laser_power(True)
            self.job.append(           Op(y+cell_size, xmin))
            if marking: self.laser_power(False)
            y += cell_size*2


        self.job.calculate_distances()

class CopyGridPattern(TestPattern):
    name='grid'
    def render(self):
        marking = args.operation == 'mark'
        Op = balor.MSBF.OpMarkTo if marking else balor.MSBF.OpJumpTo
        xmin, xmax, ymin, ymax = args.xmin, args.xmax, args.ymin, args.ymax
        cell_size = self.args.cell

        if marking and ymin > cell_size and xmin > cell_size:
            fiducial_size = cell_size // 3
            fiducial_offset = cell_size // 5
            # Make a square marking at 0,0
            self.job.append(balor.MSBF.OpJumpTo(ymin + fiducial_offset, xmin + fiducial_offset))
            self.laser_power(True)
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset,
                                                xmin + fiducial_offset + fiducial_size))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset + fiducial_size,
                                                xmin + fiducial_offset + fiducial_size))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset + fiducial_size,
                                                xmin + fiducial_offset))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset,
                                                xmin + fiducial_offset))
            self.laser_power(False)
            # Make a triangle at max X
            self.job.append(balor.MSBF.OpJumpTo(ymin + fiducial_offset,
                                                xmax - fiducial_offset))
            self.laser_power(True)
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset,
                                                xmax - fiducial_offset + fiducial_size))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset + fiducial_size,
                                                xmax - fiducial_offset + fiducial_size))
            self.job.append(balor.MSBF.OpMarkTo(ymin + fiducial_offset,
                                                xmax - fiducial_offset))
            self.laser_power(False)


        x = xmin
        while x < xmax:
            self.job.append(balor.MSBF.OpJumpTo(ymin, x))
            if marking: self.laser_power(True)
            self.job.append(           Op(ymax-1, x))
            if marking: self.laser_power(False)            
            if x+cell_size >= xmax: break
            self.job.append(balor.MSBF.OpJumpTo(ymax - 1, x + cell_size))
            if marking: self.laser_power(True)            
            self.job.append(           Op(ymin, x+cell_size))
            if marking: self.laser_power(False)            
            x += cell_size*2

        y = ymin
        while y < ymax:
            self.job.append(balor.MSBF.OpJumpTo(y, xmin))
            if marking: self.laser_power(True)
            self.job.append(           Op(y, xmax-1))
            if marking: self.laser_power(False)
            if y+cell_size >= ymax: break
            self.job.append(balor.MSBF.OpJumpTo(y + cell_size, xmax - 1))
            if marking: self.laser_power(True)
            self.job.append(           Op(y+cell_size, xmin))
            if marking: self.laser_power(False)
            y += cell_size*2


        self.job.calculate_distances()


class GridPattern(TestPattern):
    name='grid'
    def render(self):
        marking = args.operation == 'mark'
        Op = balor.MSBF.OpMarkTo if marking else balor.MSBF.OpJumpTo
        cell_size = 6144

        xmin = 6144
        xmax = 2**16-6144
        ymin = 6144
        ymax = 2**16-6144

        # x lines
        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))
        for n in range(-4,5):
            self.job.append(balor.MSBF.OpJumpTo(0x8000 + n * cell_size, xmin))
            if marking: self.laser_power(True)
            self.job.append(                 Op(0x8000+n*cell_size, 0x8000-cell_size))
            if not n:
                if marking: self.laser_power(False)
                self.job.append(balor.MSBF.OpJumpTo(0x8000 + n * cell_size, 0x8000 + cell_size))
                if marking: self.laser_power(True)
            else:
                self.job.append(             Op(0x8000+n*cell_size, 0x8000+cell_size))
            self.job.append(                 Op(0x8000+n*cell_size, xmax))
            if marking: self.laser_power(False)
        
        # y lines
        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))
        for n in range(-4,5):
            self.job.append(balor.MSBF.OpJumpTo(xmin, 0x8000 + n * cell_size))
            if marking: self.laser_power(True)
            self.job.append(                 Op(0x8000-cell_size, 0x8000+n*cell_size))
            if not n:
                if marking: self.laser_power(False)
                self.job.append(balor.MSBF.OpJumpTo(0x8000 + cell_size, 0x8000 + n * cell_size))
                if marking: self.laser_power(True)
            else:
                self.job.append(             Op(0x8000+cell_size, 0x8000+n*cell_size))
            self.job.append(                 Op(ymax, 0x8000+n*cell_size))
            if marking: self.laser_power(False)

        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))

        
        self.job.append(balor.MSBF.OpJumpTo(0x8000 - cell_size, 0x8000 - cell_size))
        if marking: self.laser_power(True)
        self.job.append(                 Op(0x8000+cell_size, 0x8000+cell_size))
        if marking: self.laser_power(False)
        self.job.append(balor.MSBF.OpJumpTo(0x8000 + cell_size, 0x8000 - cell_size))
        if marking: self.laser_power(True)
        self.job.append(                 Op(0x8000-cell_size, 0x8000+cell_size))
        if marking: self.laser_power(False)

        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))
        self.job.append(balor.MSBF.OpJumpTo(ymax - 5 * cell_size // 6, xmax - 5 * cell_size // 6))
        if marking: self.laser_power(True)
        self.job.append(                 Op(ymax-5*cell_size//6, xmax-3*cell_size//6))
        self.job.append(                 Op(ymax-3*cell_size//6, xmax-3*cell_size//6))
        self.job.append(                 Op(ymax-5*cell_size//6, xmax-5*cell_size//6))
        if marking: self.laser_power(False)

        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))

        #x = xmin
        #while x < xmax:
        #    self.job.append(balor.MSBF.OpTravel(ymin, x))
        #    if marking: self.laser_power(True)
        #    self.job.append(           Op(ymax-1, x))
        #    if marking: self.laser_power(False)            
        #    if x+cell_size >= xmax: break
        #    self.job.append(balor.MSBF.OpTravel(ymax-1, x+cell_size))
        #    if marking: self.laser_power(True)            
        #    self.job.append(           Op(ymin, x+cell_size))
        #    if marking: self.laser_power(False)            
        #    x += cell_size*2

        for _ in range(200):
            self.job.append(balor.MSBF.OpMarkEndDelay(0x100))

        self.job.append(balor.MSBF.OpAltTravel(0x0008))
        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))

        self.job.calculate_distances()

import numpy as np
class CalPattern(TestPattern):
    name='cal'
    def square(self, x, y, w, h):
        self.line(x,y,      x,y+h)
        self.line(x,y+h,    x+w,y+h)
        self.line(x+w, y+h, x+w,y)
        self.line(x+w, y,   x,y)
    def line(self, x0, y0, x1, y1, seg_size=5):
        length = ((x0-x1)**2 + (y0-y1)**2)**0.5
        segs = max(2,int(round(length / seg_size)))
        #print ("**", x0, y0, x1, y1, length, segs, file=sys.stderr)

        xs = np.linspace(x0, x1, segs)
        ys = np.linspace(y0, y1, segs)

        for n in range(segs):
            #print ("*", xs[n], ys[n], file=sys.stderr)
            self.job.append(balor.MSBF.OpMarkTo(*self.cal.interpolate(xs[n], ys[n])))

    def render(self):
        marking = self.args.operation == 'mark'
        
        cal = balor.Cal.Cal(self.args.calfile)
        self.cal = cal

        # make squares
        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))
        for nx in range(-4,4):
            for ny in range(-4,4):
                self.job.append(balor.MSBF.OpJumpTo(*cal.interpolate(nx * 15.0 + 2.5, ny * 15.0 + 2.5)))
                if marking: self.laser_power(True)
                self.square(nx*15.0+2.5, ny*15.0+2.5, 10.0, 10.0)
                if marking: self.laser_power(False)


        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))

        # make the X
        self.job.append(balor.MSBF.OpJumpTo(*cal.interpolate(-60, -60)))
        if marking: self.laser_power(True)
        self.line(-60,-60,  60,60)
        if marking: self.laser_power(False)
        self.job.append(balor.MSBF.OpJumpTo(*cal.interpolate(60, -60)))
        if marking: self.laser_power(True)
        self.line(60,-60,  -60,60)
        if marking: self.laser_power(False)

        # make the cross
        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))
        self.job.append(balor.MSBF.OpJumpTo(*cal.interpolate(-60, 0)))
        if marking: self.laser_power(True)
        self.line(-60,0,  60,0)
        if marking: self.laser_power(False)
        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))
        self.job.append(balor.MSBF.OpJumpTo(*cal.interpolate(0, -60)))
        if marking: self.laser_power(True)
        self.line(0,-60,  0,60)
        if marking: self.laser_power(False)

        # Make the big square
        self.job.append(balor.MSBF.OpJumpTo(*cal.interpolate(60, 60)))
        if marking: self.laser_power(True)
        self.line(60,   60,      60,  -60)
        self.line(60,  -60,     -60,  -60)
        self.line(-60, -60,     -60,   60)
        self.line(-60,  60,      60,   60)
        if marking: self.laser_power(False)
        
        # make the +x +y triangle
        self.job.append(balor.MSBF.OpJumpTo(*cal.interpolate(55, 55)))
        if marking: self.laser_power(True)
        self.line(55,   55,      50,  55)
        self.line(50,   55,      50,  50)
        self.line(50,   50,      55,  55)
        if marking: self.laser_power(False)


        for _ in range(200):
            self.job.append(balor.MSBF.OpMarkEndDelay(0x100))

        self.job.append(balor.MSBF.OpAltTravel(0x0008))
        self.job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))

        self.job.calculate_distances()

all_test_patterns = {x.name:x for x in [GridPattern, OldGridPattern, CalPattern]}

#################

if args.output is None:
    output_file = sys.stdout.buffer
else:
    output_file = open(args.output, 'wb')



job = balor.MSBF.JobFactory(args.machine)
pattern = all_test_patterns[args.type](args, job)
pattern.render()

output_file.write(job.serialize())



    




