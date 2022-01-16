from balor.sender import Sender
from math import sin


sender = Sender()

sender.open()
sender.set_xy(0x9000, 0x9000)


def tick(cmds, loop_index):
    cmds.clear()
    x = int(round(20 * sin(loop_index * 0.1)))
    cmds.set_travel_speed(2000)
    cmds.light(0x9000 + (x * 1000), 0x7000 + (x * 1000))
    cmds.light(0x7000 + (x * 1000), 0x7000 + (x * 1000))
    cmds.light(0x7000 + (x * 1000), 0x9000 + (x * 1000))
    cmds.light(0x9000 + (x * 1000), 0x9000 + (x * 1000))
    print(loop_index)


job = sender.job(tick=tick)
job.execute(1000)
sender.close()
