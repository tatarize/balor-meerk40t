from balor.sender import Sender

sender = Sender()

sender.open()
sender.set_xy(0x9000, 0x9000)
job = sender.job()
job.set_travel_speed(2000)
job.light(0x9000, 0x7000)
job.light(0x7000, 0x7000)
job.light(0x7000, 0x9000)
job.light(0x9000, 0x900)
job.execute(1000)
sender.close()
