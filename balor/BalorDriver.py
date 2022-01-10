import sys
import time

from meerk40t.core.cutcode import LaserSettings

from balor.GalvoConnection import GalvoConnection


class BalorDriver:
    def __init__(self, service):
        self.service = service
        self.name = str(self.service)
        self.connection = GalvoConnection(service)
        self.connected = False
        self.connecting = False

        self.settings = LaserSettings()

        self.holds = []
        self.temp_holds = []

        self.is_relative = False
        self.laser = False

        self._shutdown = False

        self.queue = []

        self.connect()

    def __repr__(self):
        return "BalorDriver(%s)" % self.name

    def service_attach(self):
        self._shutdown = False

    def service_detach(self):
        self._shutdown = True

    def connect(self):
        """
        Connect to the GalvoConnection
        :return:
        """
        self.connected = False
        self.connecting = True
        while not self.connected:
            self.connected = self.connection.open()
            if not self.connected:
                self.service.signal("pipe;usb_status", "Connecting...")
                if self._shutdown:
                    self.connecting = False
                    self.service.signal("pipe;usb_status", "Failed to connect")
                    return
                time.sleep(1)
        self.connected = True
        self.connecting = False
        self.service.signal("pipe;usb_status", "Connected")

    def disconnect(self):
        self.connection.close()
        self.connected = False
        self.connecting = False
        self.service.signal("pipe;usb_status", "Disconnected")

    def cutcode_to_light_job(self, queue):
        """
        Converts a queue of cutcode operations into a light job.

        :param queue:
        :return:
        """
        import balor
        job = balor.MSBF.Job()
        job.cal = balor.Cal.Cal(self.service.calfile)
        travel_speed = int(round(self.service.travel_speed / 2.0))  # units are 2mm/sec
        cut_speed = int(round(self.service.cut_speed / 2.0))
        laser_power = int(round(self.service.laser_power * 40.95))
        q_switch_period = int(round(1.0 / (self.service.q_switch_frequency * 1e3) / 50e-9))
        job.add_light_prefix(travel_speed)
        job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))  # centerize?

        for plot in queue:
            start = plot.start()
            # job.laser_control(False)
            job.append(balor.MSBF.OpJumpTo(*job.cal.interpolate(start[0], start[1])))
            # job.laser_control(True)
            for e in plot.generator():
                on = 1
                if len(e) == 2:
                    x, y = e
                else:
                    x, y, on = e
                if on == 0:
                    try:
                        # job.laser_control(False)
                        job.append(balor.MSBF.OpJumpTo(*job.cal.interpolate(x, y)))
                        # job.laser_control(True)
                        # print("Moving to {x}, {y}".format(x=x, y=y))
                    except ValueError:
                        print("Not including this stroke path:", file=sys.stderr)
                else:
                    job.append(balor.MSBF.OpJumpTo(*job.cal.interpolate(x, y)))
                self.service.current_x = x
                self.service.current_y = y
        # job.laser_control(False)
        job.calculate_distances()
        return job

    def cutcode_to_mark_job(self, queue):
        import balor
        job = balor.MSBF.Job()
        job.cal = balor.Cal.Cal(self.service.calfile)
        travel_speed = int(round(self.service.travel_speed / 2.0))  # units are 2mm/sec
        cut_speed = int(round(self.service.cut_speed / 2.0))
        laser_power = int(round(self.service.laser_power * 40.95))
        q_switch_period = int(round(1.0 / (self.service.q_switch_frequency * 1e3) / 50e-9))
        job.add_mark_prefix(
            travel_speed=travel_speed,
            laser_power=laser_power,
            q_switch_period=q_switch_period,
            cut_speed=cut_speed,
        )
        job.append(balor.MSBF.OpJumpTo(0x8000, 0x8000))  # centerize?

        job.laser_control(True)
        for plot in queue:
            start = plot.start()
            job.append(balor.MSBF.OpJumpTo(*job.cal.interpolate(start[0], start[1])))

            for e in plot.generator():
                on = 1
                if len(e) == 2:
                    x, y = e
                else:
                    x, y, on = e
                if on == 0:
                    try:
                        job.append(balor.MSBF.OpJumpTo(*job.cal.interpolate(x, y)))
                        # print("Moving to {x}, {y}".format(x=x, y=y))
                    except ValueError:
                        print("Not including this stroke path:", file=sys.stderr)
                else:
                    job.append(balor.MSBF.OpMarkTo(*job.cal.interpolate(x, y)))
                self.service.current_x = x
                self.service.current_y = y
        job.laser_control(False)
        job.calculate_distances()
        return job

    def hold_work(self):
        return self.hold()

    def hold_idle(self):
        return False

    def hold(self):
        """
        Holds are criteria to use to pause the data interpretation. These halt the production of new data until the
        criteria is met. A hold is constant and will always halt the data while true. A temp_hold will be removed
        as soon as it does not hold the data.

        :return: Whether data interpretation should hold.
        """
        temp_hold = False
        fail_hold = False
        for i, hold in enumerate(self.temp_holds):
            if not hold():
                self.temp_holds[i] = None
                fail_hold = True
            else:
                temp_hold = True
        if fail_hold:
            self.temp_holds = [hold for hold in self.temp_holds if hold is not None]
        if temp_hold:
            return True
        for hold in self.holds:
            if hold():
                return True
        return False

    def laser_off(self, *values):
        self.laser = False

    def laser_on(self, *values):
        self.laser = True

    def laser_disable(self, *values):
        self.settings.laser_enabled = False

    def laser_enable(self, *values):
        self.settings.laser_enabled = True

    def plot(self, plot):
        """
        :param plot:
        :return:
        """
        self.queue.append(plot)

    def light(self, job):
        self.connection.send_data(job.serialize())

    def plot_start(self):
        mark_job = self.cutcode_to_mark_job(self.queue)
        self.queue = []
        self.connection.send_data(mark_job.serialize())

    # self.laser_off()
    # self.laser_on()
    # self.laser_disable()
    # self.laser_enable()
    # self.cut(x, y)
    # self.move(x, y)
    # self.move_abs(x, y)
    # self.move_rel(x, y)
    # self.home(*values)
    # self.lock_rail()
    # self.unlock_rail()
    # self.plot_plot(values[0])
    # self.send_blob(values[0], values[1])
    # self.plot_start()
    # self.set_speed(values[0])
    # self.set_power(values[0])
    # self.set_ppi(values[0])
    # self.set_pwm(values[0])
    # self.set_step(values[0])
    # self.set_overscan(values[0])
    # self.set_acceleration(values[0])
    # self.set_d_ratio(values[0])
    # self.set_directions(values[0], values[1], values[2], values[3])
    # self.set_incremental()
    # self.set_absolute()
    # self.set_position(values[0], values[1])
    # self.ensure_rapid_mode(*values)
    # self.ensure_program_mode(*values)
    # self.ensure_raster_mode(*values)
    # self.ensure_finished_mode(*values)
    # self.wait(values[0])
    # self.wait_finish()
    # self.function()
    # self.signal()
    # # Realtime:
    # self.pause()
    # self.resume()
    # self.reset()
    # self.status()
