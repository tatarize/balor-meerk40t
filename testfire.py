from balor.sender import Sender

sender = Sender()

sender.open()
job = sender.job()
"""
51 80 00 00 00 00 00 00 00 00 00 00 
04 80 20 03 00 00 00 00 00 00 00 00 
1B 80 E8 03 00 00 00 00 00 00 00 00 
12 80 66 02 00 00 00 00 00 00 00 00 
21 80 01 00 00 00 00 00 00 00 00 00 
04 80 20 03 00 00 00 00 00 00 00 00 
03 80 60 EA 00 00 00 00 00 00 00 00 
03 80 40 9C 00 00 00 00 00 00 00 00 
21 80 00 00 00 00 00 00 00 00 00 00
"""
job.raw_ready_mark()
job.raw_mark_end_delay(0x0320)
job.raw_q_switch_period(0x03E8)
job.raw_laser_control(1)
job.raw_mark_end_delay(0x0320)
job.raw_laser_on_mark(0xEA60)
job.raw_laser_on_mark(0x9C40)
job.raw_laser_control(0)
job.execute(1000)
sender.close()
