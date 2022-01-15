#!/usr/bin/env python3

import balor
import balor.sender

sender = balor.sender.Sender(cor_table=open("balor/default.cor",'rb').read())


import sys

import balor.MSBF, balor.Cal
machine = "BJJCZ_LMCV4_FIBER_M"
calfile = "cal_0002.csv"
cal = balor.Cal.Cal(calfile)

def job(x):
    job = balor.MSBF.JobFactory(machine)
    job.cal = cal
    job.add_light_prefix(travel_speed=8000) # 4000 mm/s
    # make a triangle
    for _ in range(10):
        job.line(0+x,0, 20+x, 20, Op=balor.MSBF.OpTravel)
        job.line(20+x,20, 0+x, 20, Op=balor.MSBF.OpTravel)
        job.line(0+x,20, 0+x, 0, Op=balor.MSBF.OpTravel)
    job.calculate_distances()
    data = job.serialize()
    return data
#open("sender-test-log.bin",'wb').write(data)

import numpy as np
class JobCallable:
    def __init__(self):
        self.t = 0

    def job(self, *p):
        job = balor.MSBF.JobFactory(machine)
        job.cal = cal
        job.add_light_prefix(travel_speed=8000) # 4000 mm/s
        # make a triangle
        for _ in range(10):
            self.t += 1
            x = int(round(20*np.sin(self.t*0.1)))
            job.line(0+x,0, 20+x, 20, Op=balor.MSBF.OpTravel)
            job.line(20+x,20, 0+x, 20, Op=balor.MSBF.OpTravel)
            job.line(0+x,20, 0+x, 0, Op=balor.MSBF.OpTravel)
        job.calculate_distances()
        data = job.serialize()
        return data


import threading

import time
time.sleep(0.1)
c = sender.get_condition()
x, y = sender.get_xy()
print ("Initial Condition: 0x%04X   X: 0x%04X  Y: 0x%04X"%(c,x,y))

job = JobCallable()

def loop():
    sender.loop_job(job.job, loop_count=True)


print ("Enter 'a' to abort, 's' to start.")
while 1:
    c = sender.get_condition()
    print ("Condition: 0x%04X"%c)
    

    cmd = sys.stdin.readline().split()
    if 'a' in cmd:
        sender.abort()
    if 's' in cmd:
        threading.Thread(target=loop).start()


