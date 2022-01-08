#!/usr/bin/env python3
import balor
import sys, argparse, os, io, pickle
import tkinter as tk
import numpy as np
import time
from tkinter import messagebox

parser = argparse.ArgumentParser(description='''
Creates alignment files with an optical / machine vision technique.''',
epilog='''
NOTE: This software is EXPERIMENTAL and has only been tested with a
single machine. There are many different laser engraving machines 
and the fact that they look the same, or even have the same markings,
is not proof that they are really the same.''')

parser.add_argument('-o', '--output', 
    help="Specify the output alignment file. (default stdout)",
    default=None)



parser.add_argument('-c', '--calfile',
    help="Provide a calibration file for the machine.")

parser.add_argument('-m', '--machine', 
        help="specify which machine interface to use. Valid machines: "+', '.join(
            [x.__name__ for x in balor.all_known_machines]), default="BJJCZ_LMCV4_FIBER_M")
parser.add_argument('-v', '--verbose', type=int, help="verbosity level", default=0)
parser.add_argument('--travel-speed',
    help="Specify the traveling speed (mm/s)",
    default=5000, type=float)
parser.add_argument('--cut-speed',
    help="Specify the cutting speed (mm/s)",
    default=100, type=float)
parser.add_argument('--laser-power', '-p',
    help="Specify the laser power in percentage.",
    default=70, type=float)
parser.add_argument('--q-switch-frequency', '-q',
    help="Specify the q switch frequency in KHz",
    default=30.0, type=float)
parser.add_argument('--camera',
    help="Specify which video source to use for microphotography",
    default=0, type=int)
parser.add_argument('-i', '--index', help="specify which machine to use, if there is more than one", type=int, default=0)
parser.add_argument('--axis-crosshair-size', 
    help="Size of the axis / origin crosshairs.",
    default=40, type=float)

import sys
args = parser.parse_args()
if args.output is None:
    out_file = sys.stdout.buffer
else:
    out_file = open(args.output, 'wb')


import balor.MSBF, balor.Cal


from tkinter import *
from tkinter import ttk
from PIL import ImageTk
from PIL import Image
import cv2

class Aligner:
    def save(self):
        print (self.alignment_offset[0], self.alignment_offset[1], self.alignment_angle, self.i_reverse_side.get())
    def register(self):
        dx,dy = self.fine_delta
        self.i_this_x.set(self.i_this_x.get() + dx)
        self.i_this_y.set(self.i_this_y.get() + dy)

        self.fine_points = [
                [0.25,0.25,  False],
                [0.75,0.25,  False],
                [0.75,0.75,  False],
                [0.45, 0.45, True],
                [0.55, 0.45, True],
                [0.55, 0.55, True]
        ]
        self.fine_delta = 0,0


    def __init__(self, args, machine):
        self.machine = machine
        self.args = args
        self.root = Tk()
        self.video = cv2.VideoCapture(args.camera)
        self.fine_delta = 0,0
        self.alignment_points = [
                [10.0, -10.0],
                [-10.0, -10.0],
                [10.0, 10.0],
        ]

        self.fine_points = [
                [0.25,0.25,  False],
                [0.75,0.25,  False],
                [0.75,0.75,  False],
                [0.45, 0.45, True],
                [0.55, 0.45, True],
                [0.55, 0.55, True]
        ]
        self.point_selected = 0

        self.fine_pos_ref = 0.5, 0.5
        self.fine_pos_fid = 0.5, 0.5

        self.laser_safety = True
        self.lasering = False

        self.alignment_offset = [0.0, 0.0]
        self.alignment_angle = 0.0

        self.img = None

        self.cal = balor.Cal.Cal(args.calfile)
        self.machine_type = args.machine

        self.make_widgets()
        
        self.machine_helper = machine.start_lighting_thread()

        self.dirty_geometry = True
        self.geometry = self.draw_geometry(first_run = True)
        self.machine_helper.set_pattern(self.geometry)

        
        self.update_video_geometry()
        self.root.after(1, self.update)

    def update_video_geometry(self):
        w,h = self.vid_w, self.vid_h
        s = int(round((self.vid_w+self.vid_h)/40))
        sel = self.point_selected
        for i in range(6):
            c = self.circ_fine[i]
            x,y,f = self.fine_points[i]
            ts = s/4 if f else s/2
            color = 'green' if sel == i else ('cyan' if f else 'white')
            #print (i, color)
            self.canvas.itemconfig(c, outline=color)
            self.canvas.coords(c, x*w-ts, y*h-ts, x*w+ts, y*h+ts)


        n = 0
        for i in range(5):
            l = self.line_fine[n]
            x0,y0,f0 = self.fine_points[i]
            x1,y1,f1 = self.fine_points[i+1]
            if f0 != f1: continue


            color = ('cyan' if f0 else 'white')
            self.canvas.itemconfig(l, fill=color)
            self.canvas.coords(l, x0*w, y0*h, x1*w, y1*h)
            n += 1

        fp = self.fine_points
        xref,yref,aref = self.circumcenter(fp[0][0], fp[0][1], fp[1][0], fp[1][1], fp[2][0], fp[2][1])
        xfid,yfid,afid = self.circumcenter(fp[3][0], fp[3][1], fp[4][0], fp[4][1], fp[5][0], fp[5][1])
        aref-= np.pi/2
        afid-= np.pi/2


        # Calculate scales
        (x0,y0,_),(x1,y1,_) = fp[0],fp[1]
        rel_width = ((x0-x1)**2 + (y0-y1)**2)**0.5
        (x0,y0,_),(x1,y1,_) = fp[1],fp[2]
        rel_height = ((x0-x1)**2 + (y0-y1)**2)**0.5
        # dimensions now in units of "framesizes"
        # the reference is 1mm on a side.
        self.canvas.coords(self.x_scale_bar, 0.06*w, 0.05*h, 0.06*w+rel_width*w, 0.06*h)
        self.canvas.coords(self.y_scale_bar, 0.05*w, 0.06*h, 0.06*w, 0.06*h+rel_height*h)

        


        
        self.canvas.coords(self.vector_ref, 0.1*w, 0.8*h, 0.1*w + np.cos(aref)*s*2,   0.8*h + np.sin(aref)*s*2)
        self.canvas.coords(self.vector_fid, 0.1*w, 0.8*h, 0.1*w + np.cos(afid)*s, 0.8*h + np.sin(afid)*s)

        self.fid_align.configure(text="Fiducial:  ΔX: %7.2f μm ΔY: %7.2f μm A: %6.2f°"%(
            (xfid-xref)/rel_width*1000,(yfid-yref)/rel_height*1000,np.degrees(afid)))

        self.fine_delta = (xfid-xref)/rel_width, (yfid-yref)/rel_height

        # 1 mm  = rel_width frames
        # w pixels = 1 frames
        # rel_width*w pixels = 1mm
        x_px_scale = 1/rel_width*w
        y_px_scale = 1/rel_height*h
        self.ref_align.configure(text="Reference: X: %6.2f μm/px Y: %6.2f μm/px A: %6.2f°"%(
            x_px_scale/1000,y_px_scale/1000,np.degrees(aref)))
        
        self.canvas.coords(self.line_crosshair_fid[0], xfid*w, 0, xfid*w, h)
        self.canvas.coords(self.line_crosshair_fid[1], 0, yfid*h, w, yfid*h)
        self.canvas.coords(self.line_crosshair_ref[0], xref*w-s*4, yref*h-s*4, xref*w+s*4, yref*h+s*4)
        self.canvas.coords(self.line_crosshair_ref[1], xref*w-s*4, yref*h+s*4, xref*w+s*4, yref*h-s*4)

        self.fine_post_ref = xref, yref
        self.fine_post_fid = xfid, yfid

         
            

    def circumcenter(self, x0, y0, x1, y1, x2, y2):
        A = np.array([[x2-x0,y2-y0],[x2-x1,y2-y1]])
        if np.linalg.det(A):
            Y = np.array([(x2**2 + y2**2 - x0**2 - y0**2),(x2**2+y2**2 - x1**2-y1**2)])
            Ai = np.linalg.inv(A)
            X = 0.5*np.dot(Ai,Y)
            aox,aoy = X[0],X[1]
        else:
            aox,aoy = 0.5,0.5

        mx, my = (x0+x1)/2.0, (y0+y1)/2.0
        aoa =  np.arctan2(aoy-my, aox-mx)
        return aox, aoy, aoa

    def left_click_video(self, event):
        # Select a marker
        w,h = self.vid_w, self.vid_h
        x,y = event.x/w, event.y/h
        #print ("left Clicked at", x, y)

        sn = 0
        sd = 2
        for n,(xr,yr,fid) in enumerate(self.fine_points):
            d = ((x-xr)**2 + (y-yr)**2)**0.5
            if d < sd: 
                sd = d
                sn = n
        #print ("nearest marker was", sn, "at distance", sd)
        self.point_selected = sn

    def left_motion_video(self, event):
        w,h = self.vid_w, self.vid_h
        x,y = event.x/w, event.y/h
        _,_,f = self.fine_points[self.point_selected]
        self.fine_points[self.point_selected] = [x,y,f]
        #print (x,y)

    def right_click_video(self, event):
        x,y = event.x, event.y
        w,h = self.vid_w, self.vid_h
        print ("right Clicked at", x/w, y/h)


    def calculate_geometry(self):
        aox = 0.0
        aoy = 0.0
        aoa = 0.0
    
        reverse = self.i_reverse_side.get()
        ap = self.alignment_points

        # calculate the circumcenter

        x0, y0 = ap[0]  
        x1, y1 = ap[1]
        x2, y2 = ap[2]

        A = np.array([[x2-x0,y2-y0],[x2-x1,y2-y1]])
        if np.linalg.det(A):
            Y = np.array([(x2**2 + y2**2 - x0**2 - y0**2),(x2**2+y2**2 - x1**2-y1**2)])
            Ai = np.linalg.inv(A)
            X = 0.5*np.dot(Ai,Y)
            aox,aoy = X[0],X[1]
        else:
            aox,aoy = 0,0

        # We draw the 'i' vector from the midpoint of the line x0y0-x1y1
        # to the circumcenter
        mx, my = (x0+x1)/2.0, (y0+y1)/2.0

        # angle of y axis
        aoa =  np.arctan2(aoy-my, aox-mx) 

        
        #FIXME: Decide how to define the angle so it flips right
    

        self.alignment_offset = aox, aoy
        self.alignment_angle = np.degrees(aoa)
        atext = "X: %6.2f Y: %6.2f A: %5.2f°"%(aox, aoy, self.alignment_angle)
        self.origin_label.config(text=atext)

    def safety_timer(self):
        if self.i_safety_off.get():
            self.button_safety.invoke()
            messagebox.showinfo(message="Laser arm timed out.")

    def laser_mark(self):
        mark_geometry = self.square_marking_geometry()

        assert not self.laser_safety, "Laser safety related bug."
        self.label_laser_state.configure(text="LASER EMISSION ON!", foreground='red')
        # Make a mark
        self.lasering = True
        self.machine_helper.set_pattern(mark_geometry)
        
        while not self.machine_helper.running:
            time.sleep(0.01)

        while self.machine_helper.running:
            time.sleep(0.01)

        self.lasering = False
        self.button_safety.invoke()
        assert self.laser_safety, "Laser safety related bug."

    def laser_cross(self):
        assert not self.laser_safety, "Laser safety related bug."
        self.label_laser_state.configure(text="LASER EMISSION ON!", foreground='red')
        # make a cross

        #self.button_safety.invoke()
        #assert self.laser_safety, "Laser safety related bug."

    def laser_safety_button(self):
        safety_off = self.i_safety_off.get()
        if self.laser_safety and safety_off:
            # Currently off, Enable emission
            self.label_laser_state.configure(text="Laser emission is ARMED!", foreground='orange')
            self.button_mark.configure(state=NORMAL)
            self.button_cross.configure(state=NORMAL)
            self.laser_safety = False
            self.root.after(5000, self.safety_timer)

        elif not self.laser_safety and not safety_off:
            # Currently on, Disable emission
            self.laser_safety = True
            self.button_cross.configure(state=DISABLED)
            self.button_mark.configure(state=DISABLED)
            self.label_laser_state.configure(text="Laser emission is secured.", foreground='green')

        else:
            assert False, "Some kind of race condition involving the laser safety"

    def square_marking_geometry(self):
        cur_point = self.i_which_point.get()
        cur_x, cur_y = self.alignment_points[cur_point]
        nx,ny = self.cal.interpolate(cur_x - 0.5, cur_y - 0.5)
        px,py = self.cal.interpolate(cur_x + 0.5, cur_y + 0.5)
        square = [(px,ny), (px,py), (nx,py),(nx,ny)]

        args = self.args
        laser_power = int(round(args.laser_power * 40.95))
        q_switch_period = int(round(1.0/(args.q_switch_frequency*1e3) / 50e-9))
        travel_speed = int(round(args.travel_speed / 2.0)) # units are 2mm/sec
        cut_speed = int(round(args.cut_speed / 2.0))

        job = balor.MSBF.JobFactory(self.args.machine)
        job.add_mark_prefix(travel_speed = travel_speed,
            laser_power=laser_power,
            q_switch_period = q_switch_period,
            cut_speed=cut_speed)
        job.append(balor.MSBF.OpTravel(nx, ny))
        job.laser_control(True)
        for vx,vy in square:
            job.append(balor.MSBF.OpCut(vx,vy,0x8000))
        job.laser_control(False)
        job.calculate_distances()
        return job.serialize()

    def draw_geometry(self, first_run=False):
        self.calculate_geometry()

        #print ("FIRST RUN", first_run, file=sys.stderr)

        job = balor.MSBF.JobFactory(self.args.machine)
        if first_run:
            travel_speed = int(round(self.args.travel_speed / 2.0)) # units are 2mm/sec
            job.add_light_prefix(
                    travel_speed=travel_speed
                    )
        cur_point = self.i_which_point.get()

        aox,aoy = self.alignment_offset
        ox,oy = self.cal.interpolate(aox,aoy)
        job.append(balor.MSBF.OpTravel(ox, oy))

        reverse = self.i_reverse_side.get()
         

        # Draw the other point squares
        light_all = self.i_light_all.get()

        for which_point in range(3):
            if not light_all and which_point != cur_point: continue
            #if which_point == 2 and not backside: continue
            #if which_point == 3 and backside: continue
            cur_x, cur_y = self.alignment_points[which_point]
            cx,cy = self.cal.interpolate(cur_x,cur_y)
            nx,ny = self.cal.interpolate(cur_x - 0.5, cur_y - 0.5)
            px,py = self.cal.interpolate(cur_x + 0.5, cur_y + 0.5)
            square = [(nx,ny), (px,ny), (px,py), (nx,py)]*2
            #job.append(balor.MSBF.OpTravel(0x8000, 0x8000))
            job.append(balor.MSBF.OpTravel(cx, cy))
            for _ in range(13 if which_point == cur_point else 3):
                for x,y in square[which_point:which_point+4]:
                    job.append(balor.MSBF.OpTravel(x,y))
            job.append(balor.MSBF.OpTravel(ox, oy))

        if self.i_light_origin.get():
            crl = self.args.axis_crosshair_size/2.0
            ang = np.radians(self.alignment_angle)+(-np.pi/2 if reverse else np.pi/2)
            anj = np.radians(self.alignment_angle)
            
            xaxp, xayp = self.cal.interpolate(aox+(crl+0)*np.cos(ang), aoy+(crl+0)*np.sin(ang))
            xaxp2, xayp2 = self.cal.interpolate(aox+(crl)*np.cos(ang), aoy+(crl)*np.sin(ang)+2*np.cos(ang))
            xaxp3, xayp3 = self.cal.interpolate(aox+(crl)*np.cos(ang), aoy+(crl)*np.sin(ang)-2*np.cos(ang))

            xaxn, xayn = self.cal.interpolate(aox-crl*np.cos(ang), aoy-crl*np.sin(ang))

            yaxp, yayp = self.cal.interpolate(aox+0.5*(crl+0)*np.cos(anj), aoy+0.5*(crl+0)*np.sin(anj))
            yaxp2, yayp2 =self.cal.interpolate(aox+0.5*(crl+0)*np.cos(anj)+1*np.sin(anj),  aoy+0.5*(crl+0)*np.sin(anj))
            yaxp3, yayp3 = self.cal.interpolate(aox+0.5*(crl+0)*np.cos(anj)-1*np.sin(anj), aoy+0.5*(crl+0)*np.sin(anj))

            yaxn, yayn = self.cal.interpolate(aox-0.5*crl*np.cos(anj), aoy-0.5*crl*np.sin(anj))

            for _ in range(2):
                job.append(balor.MSBF.OpTravel(ox, oy))

                job.append(balor.MSBF.OpTravel(xaxp,xayp))
                job.append(balor.MSBF.OpTravel(xaxp2,xayp2))
                job.append(balor.MSBF.OpTravel(xaxp3,xayp3))
                job.append(balor.MSBF.OpTravel(xaxp,xayp))

                job.append(balor.MSBF.OpTravel(xaxn,xayn))
                job.append(balor.MSBF.OpTravel(ox, oy))
                

                job.append(balor.MSBF.OpTravel(yaxp,yayp))
                job.append(balor.MSBF.OpTravel(yaxp2,yayp2))
                job.append(balor.MSBF.OpTravel(yaxp,yayp))
                job.append(balor.MSBF.OpTravel(yaxp3,yayp3))
                job.append(balor.MSBF.OpTravel(yaxp,yayp))

                job.append(balor.MSBF.OpTravel(yaxn,yayn))
        job.append(balor.MSBF.OpTravel(ox, oy))
            
        job.calculate_distances()

        self.dirty_geometry = False
        return job.serialize()

    def change_coord(self, *args, x=None, y=None):
        if x is None: x = self.i_this_x.get()
        if y is None: y = self.i_this_y.get()

        which = self.i_which_point.get()
        self.alignment_points[which] = [x,y]
        self.touch_geometry()


    def jog(self, x=0, y=0):
        step_size = float(self.i_step_size.get())
        if x: self.i_this_x.set(self.i_this_x.get() + x*step_size)
        if y: self.i_this_y.set(self.i_this_y.get() + y*step_size)

    def changed_point(self):
        which = self.i_which_point.get()

        x,y = self.alignment_points[which]

        self.i_this_x.set(x)
        self.i_this_y.set(y)

        self.touch_geometry()

    def clicked_reverse(self):
        which = self.i_which_point.get()
        reverse = self.i_reverse_side.get()

        for a in self.alignment_points:
            a[0] *= -1

        if reverse:
            self.button_a.grid(column=1, row=3)
            self.button_b.grid(column=2, row=3)
            self.button_c.grid(column=1, row=2)
            #if which == 1: self.button_a.invoke()
            #if which == 0: self.button_b.invoke()
        else:
            self.button_a.grid(column=2, row=3)
            self.button_b.grid(column=1, row=3)
            self.button_c.grid(column=2, row=2)
            #if which == 1: self.button_a.invoke()
            #if which == 0: self.button_b.invoke()


        self.touch_geometry()


    def touch_geometry(self):
        self.dirty_geometry = True

    def make_widgets(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')


        self.root.title("Balor Optical Aligner")
        self.frame = ttk.Frame(self.root, padding="3 3 12 12")
        self.frame.grid(column=0,row=0, sticky=(N, W, E, S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.i_monochrome = BooleanVar(value=False)
        ttk.Checkbutton(self.frame, text="Monochrome", variable=self.i_monochrome).grid(column=1,row=0)
        self.i_canny = BooleanVar(value=False)
        ttk.Checkbutton(self.frame, text="Canny Detection", variable=self.i_canny).grid(column=2,row=0)
        ttk.Label(self.frame, text="Current Alignment Point:").grid(column=1, row=1, columnspan=2, )
        ttk.Label(self.frame, text="X for this point:").grid(column=1, row=4)
        ttk.Label(self.frame, text="Y for this point:").grid(column=1, row=5)

        self.i_this_x = DoubleVar(value=self.alignment_points[0][0])
        self.i_this_x.trace_add("write", self.change_coord)
        self.x_entry = ttk.Entry(self.frame, textvariable=self.i_this_x)
        self.x_entry.grid(column=2, row=4)

        self.i_this_y = DoubleVar(value=self.alignment_points[0][1])
        self.i_this_y.trace_add("write", self.change_coord)
        self.y_entry = ttk.Entry(self.frame, textvariable=self.i_this_y, validatecommand=self.change_coord)
        self.y_entry.grid(column=2, row=5)

        self.i_which_point = IntVar(value=0)
        self.button_a = ttk.Radiobutton(self.frame, text='A', value=0, variable=self.i_which_point, command=self.changed_point)
        self.button_a.grid(
                column=1, row=3)
        self.button_b = ttk.Radiobutton(self.frame, text='B', value=1, variable=self.i_which_point, command=self.changed_point)
        self.button_b.grid(
                column=2, row=3)


        self.button_c = ttk.Radiobutton(self.frame, text='C', value=2, variable=self.i_which_point, command=self.changed_point)
        self.button_c.grid(column=1, row=2)
        #self.button_xpyp = ttk.Radiobutton(self.frame, text='C', value=2, variable=self.i_which_point, command=self.changed_point)
        #self.button_xpyp.grid(column=2, row=3, sticky=(E,N))
        #self.button_xpyp.configure(state=DISABLED)

        ttk.Label(self.frame, text="Full Calibrated Area:").grid(column=1, row=6, columnspan=2, )
        ttk.Label(self.frame, text="X %.3fmm to %.3fmm"%(self.cal.mm_xmin, self.cal.mm_xmax)).grid(column=1, row=7, columnspan=2, )
        ttk.Label(self.frame, text="Y %.3fmm to %.3fmm"%(self.cal.mm_ymin, self.cal.mm_ymax)).grid(column=1, row=8, columnspan=2, )

        ttk.Label(self.frame, text="Registered Alignment:").grid(column=1, row=9, columnspan=2, )
        self.origin_label = ttk.Label(self.frame, text="X: ---.-- Y: ---.-- A: --.--°")
        self.origin_label.grid(column=1, row=10, columnspan=2, )
        

        self.vid_w, self.vid_h = self.video.get(cv2.CAP_PROP_FRAME_WIDTH), self.video.get(cv2.CAP_PROP_FRAME_HEIGHT)
        self.canvas = tk.Canvas(self.frame, width=self.vid_w, height=self.vid_h, cursor='target')
        self.canvas.grid(column=0,row=0, rowspan=9, )
        self.canvas.bind("<Button-1>", self.left_click_video)
        self.canvas.bind("<B1-Motion>", self.left_motion_video)
        self.canvas.bind("<Button-2>", self.right_click_video)

        self.fid_align = ttk.Label(self.frame, font='TkFixedFont',  text="Fiducial:  X: ---.--- Y: ---.--- A: --.--°")
        self.fid_align.grid(column=0,row=9, )
        self.ref_align = ttk.Label(self.frame, font='TkFixedFont',  text="Reference: X: ---.--- Y: ---.--- A: --.--°")
        self.ref_align.grid(column=0,row=10, )
        self.machine_status7 = ttk.Label(self.frame, font='TkFixedFont', text="Register 0x07: -- -- -- -- -- -- -- --")
        self.machine_status7.grid(column=0,row=11, )


        w,h,s = self.vid_w, self.vid_h, int(round((self.vid_w+self.vid_h)/40))
        self.cam_img = self.canvas.create_image(0,0, anchor=NW, image=None)
        self.circ_fine = []
        for n,(x,y,fid) in enumerate(self.fine_points):
            ts = s/4 if fid else s/2
            color = "green" if self.point_selected == n else ("cyan" if fid else "white")
            c = self.canvas.create_oval(x*w-ts,y*h-ts,x*w+ts,y*h+ts,outline=color) 
            self.circ_fine.append(c)


        self.x_scale_bar = self.canvas.create_rectangle(0.06*w, 0.05*h, 0.25*w, 0.06*h, fill="white")
        self.y_scale_bar = self.canvas.create_rectangle(0.05*w, 0.06*h, 0.06*w, 0.25*h, fill="white")
        
        self.line_fine = [
                self.canvas.create_line(x0*w,y0*h,x1*w,y1*h,
                                        fill=("cyan" if fid1 else "white"), 
                                        ) for ((x0,y0,fid1),(x1,y1,fid2)) in zip(
                    self.fine_points[:-1], self.fine_points[1:]) if fid1 == fid2
                ]


        self.vector_ref = self.canvas.create_line(0.15*w, 0.95*h, 0.15*w, 0.8*h, fill='white', arrow=LAST)
        self.vector_fid = self.canvas.create_line(0.15*w, 0.95*h, 0.15*w, 0.88*h, fill='cyan', arrow=LAST)

        self.angle_fid = 0.0
        self.angle_ref = 0.0
        self.line_crosshair_fid = [
                self.canvas.create_line(w//2 - 2*s, h//2 - 2*s, w//2 + 2*s, h//2 + 2*s, fill=("cyan"), dash=6),
                self.canvas.create_line(w//2 - 2*s, h//2 + 2*s, w//2 + 2*s, h//2 - 2*s, fill=("cyan"), dash=6),
                ]

        self.line_crosshair_ref = [
                self.canvas.create_line(w//2, h//2 - 4*s, w//2, h//2 + 4*s, fill=("white"), dash=6),
                self.canvas.create_line(w//2 - 8*s, h//2, w//2 + 8*s, h//2, fill=("white"), dash=6),
                ]

        ttk.Label(self.frame, text="DANGER: These controls may cause", foreground='red').grid(column=3, row=0, columnspan=2)
        ttk.Label(self.frame, text="emission of hazardous radiation!", foreground='red').grid(column=3, row=1, columnspan=2)

        self.button_mark = ttk.Button(self.frame, text="Mark Target Square", command=self.laser_mark)
        self.button_mark.grid(column=3, row=2)
        self.button_mark.state(['disabled'])
        self.button_cross = ttk.Button(self.frame, text="Mark Test Cross", command=self.laser_cross)
        self.button_cross.grid(column=4, row=2)
        self.button_cross.state(['disabled'])


        self.i_reverse_side = BooleanVar(value=False)
        self.i_light_origin = BooleanVar(value=True)
        self.i_light_all = BooleanVar(value=True)
        self.i_safety_off = BooleanVar(value=False)

             
        self.button_backside = ttk.Checkbutton(self.frame, text="Reverse Side", variable=self.i_reverse_side,
                command=self.clicked_reverse)
        self.button_backside.grid(column=3, row=5)
        self.button_light_center = ttk.Checkbutton(self.frame, text="Light Axes", variable=self.i_light_origin, 
                command=self.touch_geometry)
        self.button_light_center.grid(column=4, row=5)
        self.button_light_all = ttk.Checkbutton(self.frame, text="Light All", variable=self.i_light_all,
                command=self.touch_geometry)
        self.button_light_all.grid(column=3, row=6)
        self.i_freeze = BooleanVar(value=False)
        self.button_freeze = ttk.Checkbutton(self.frame, text="Freeze Video", variable=self.i_freeze)
        self.button_freeze.grid(column=4, row=6)

        self.button_safety = ttk.Checkbutton(self.frame, text="Enable Fiber Laser Emission", variable=self.i_safety_off,
                command=self.laser_safety_button)
        self.button_safety.grid(column=3, row=3, columnspan=2)
        self.label_laser_state = ttk.Label(self.frame, text="Laser emission is secured.",foreground='green')
        self.label_laser_state.grid(column=3, row=4, columnspan=2)

        ttk.Label(self.frame, text="Coarse Alignment Controls:").grid(column=3, row=7, columnspan=2)

        self.button_xp = ttk.Button(self.frame, text="+X", command=(lambda: self.jog(x=1)))
        self.button_xp.grid(column=3, row=9)
        self.button_xn = ttk.Button(self.frame, text="-X", command=(lambda: self.jog(x=-1)))
        self.button_xn.grid(column=3, row=8)
        self.button_yp = ttk.Button(self.frame, text="+Y", command=(lambda: self.jog(y=1)))
        self.button_yp.grid(column=4, row=9)
        self.button_yn = ttk.Button(self.frame, text="-Y", command=(lambda: self.jog(y=-1)))
        self.button_yn.grid(column=4, row=8)
        # arrow key bindings interfere with text fields
        #self.root.bind("<Left>",  lambda _: self.button_xp.invoke())
        self.root.bind("a",  lambda _: self.button_xp.invoke())
        #self.root.bind("<Right>",  lambda _: self.button_xn.invoke())
        self.root.bind("d",  lambda _: self.button_xn.invoke())
        #self.root.bind("<Up>",  lambda _: self.button_yp.invoke())
        self.root.bind("w",  lambda _: self.button_yp.invoke())
        #self.root.bind("<Down>", lambda _: self.button_yn.invoke())
        self.root.bind("s", lambda _: self.button_yn.invoke())
        self.root.bind("z", lambda _: self.button_a.invoke())
        self.root.bind("x", lambda _: self.button_b.invoke())
        self.root.bind("c", lambda _: self.button_c.invoke())
        self.root.bind("q", lambda _: self.i_step_size.set("1"))
        self.root.bind("e", lambda _: self.i_step_size.set("0.1"))

        self.i_fine = BooleanVar(value=False)
        self.i_extra_fine = BooleanVar(value=False)


        self.i_step_size = StringVar(value="10")
        self.step_menu = ttk.OptionMenu(self.frame, self.i_step_size,"10", "10", "1", "0.1", "0.01")
        self.step_menu.grid(column=4, row=10)
        ttk.Label(self.frame, text="Step size (mm):").grid(column=3, row=10)

        self.button_save = ttk.Button(self.frame, text="Save Alignment", command=self.save)
        self.button_save.grid(column=1, row=11)
        self.button_register = ttk.Button(self.frame, text="Register Fine", command=self.register)
        self.button_register.grid(column=2, row=11)
        self.button_auto = ttk.Button(self.frame, text="Auto Fine")
        self.button_auto.grid(column=3, row=11)
        self.button_auto.state(['disabled'])
        self.button_freeze_time = ttk.Button(self.frame, text="Freeze Timer",
            command=(lambda: self.root.after(3000, self.button_freeze.invoke)))

        self.button_freeze_time.grid(column=4, row=11)
    def update(self):
        if not self.i_freeze.get():
            data = cv2.cvtColor(self.video.read()[1],cv2.COLOR_BGR2RGB)
            if self.i_monochrome.get():
                mono = (0.2126*data[:,:,0] + 0.7152*data[:,:,1] + 0.0722*data[:,:,2])
                mono_min = np.min(mono)
                mono_max = np.max(mono)
                mono -= mono_min
                mono /= (mono_max-mono_min)
                mono *= 255
                data[:,:,0] = mono
                data[:,:,1] = 0
                data[:,:,2] = mono
            if self.i_canny.get():
                data = cv2.GaussianBlur(data, (15, 15), 0)
                data = cv2.Canny(data, 64, 192)

            #print ("updating", data) 
            self.img = ImageTk.PhotoImage(Image.fromarray(data))
            self.canvas.itemconfig(self.cam_img, image=self.img)

            
        self.update_video_geometry()

        report = self.machine_helper.get_last_status_report()
        #status = 'Register 0x25: ' + ' '.join(["%02X"%x for x in report[0]])
        #self.machine_status.config(text=status)
        status = 'Register 0x07: ' + ' '.join(["%02X"%x for x in report[1]])
        self.machine_status7.config(text=status)
        #status = 'Register 0x19: ' + ' '.join(["%02X"%x for x in report[2]])
        #self.machine_status19.config(text=status)
        
        try:
            self.geometry = self.draw_geometry(self.dirty_geometry)
            if not self.lasering:
                self.machine_helper.set_pattern(self.geometry)
        except ValueError:
            pass

        self.root.after(int(round(1000.0/24)), self.update)

    def start(self):
        self.root.mainloop()

#ttk.Button(root, text="Hello World").grid()
# FIXME Needs to take reference angle into account when determining x/y offset for square
# TODO cross marking
# TODO small reference?

Machine_class = None
for Candidate in balor.all_known_machines:
    if Candidate.__name__ == args.machine:
        Machine_class = Candidate
        break
if Machine_class is None:
    print ("I don't know about a machine called `%s'."%args.machine, file=sys.stderr)
    sys.exit(-1)
machine = Machine_class(args.index)
machine.set_verbosity(args.verbose)

a = Aligner(args, machine)
a.start()


machine.close()
