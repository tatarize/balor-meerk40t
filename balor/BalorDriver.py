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

        The cutcode objects will have properties like speed. These are currently not being respected.

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
        """
        Convert cutcode to a mark job.

        @param queue:
        @return:
        """
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
        """
        This is checked by the spooler to see if we should hold any work from being processed from the work queue.

        For example if we pause, we don't want it trying to call some functions. Only priority jobs will execute if
        we hold the work queue. This is so that "resume" commands can be processed.

        :return:
        """
        return self.hold()

    def hold_idle(self):
        """
        This is checked by the spooler to see if we should abort checking if there's any idle job after the work queue
        was found to be empty.
        :return:
        """
        return False

    def hold(self):
        """
        Holds are criteria to use to pause the data interpretation. These halt the production of new data until the
        criteria is met. A hold is constant and will always halt the data while true. A temp_hold will be removed
        as soon as it does not hold the data.

        -- This is generally just a much fancier way to process any holds we might have.

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
        """
        This command expects to stop pulsing the laser in place.

        @param values:
        @return:
        """
        self.laser = False

    def laser_on(self, *values):
        """
        This command expects to start pulsing the laser in place.

        @param values:
        @return:
        """
        self.laser = True

    def plot(self, plot):
        """
        This command is called with bits of cutcode as they are processed through the spooler. This should be optimized
        bits of cutcode data with settings on them from paths etc.

        :param plot:
        :return:
        """
        self.queue.append(plot)

    def light(self, job):
        """
        This is not a typical meerk40t command. But, the light commands in the main balor add this as the idle job.

        self.spooler.set_idle(("light", self.driver.cutcode_to_light_job(cutcode)))
        That will the spooler's idle job be calling "light" on the driver with the light job. Which is a MSBF.Job class
        We serialize that and hand it to the send_data routine of the connection.

        @param job:
        @return:
        """
        self.connection.send_data(job.serialize())

    def plot_start(self):
        """
        This is called after all the cutcode objects are sent. This says it shouldn't expect more cutcode for a bit.

        :return:
        """
        mark_job = self.cutcode_to_mark_job(self.queue)
        self.queue = []
        self.connection.send_data(mark_job.serialize())

    def move_abs(self, x, y):
        """
        This is called with the actual x and y values with units. If without units we should expect to move in native
        units.

        :param x:
        :param y:
        :return:
        """
        print("tried to move to", x,y)

    def move_rel(self, dx, dy):
        """
        This is called with dx and dy values to move a relative amount.

        :param dx:
        :param dy:
        :return:
        """
        print("tried to move by", dx, dy)

    def home(self, x=None, y=None):
        """
        This is called with x, and y, to set an adjusted home or use whatever home we have.
        :param x:
        :param y:
        :return:
        """
        self.move_abs(0,0)

    def unlock_rail(self):
        """
        This is called to unlock the gantry so we can move the laser plotting head freely.
        :return:
        """
        #hard
        pass

    def lock_rail(self):
        """
        This is called to lock the gantry so we can move the laser plotting head freely.
        :return:
        """
        pass

    def blob(self, data_type, data):
        """
        This is called to give pure data to the backend. Data is assumed to be native data-type as loaded from a file.

        :param data_type:
        :param data:
        :return:
        """
        if data_type == "balor":
            self.connection.send_data(data.serialize())

    def set(self, attribute, value):
        """
        This is called to set particular attributes. These attributes will be set in the cutcode as well but sometimes
        there is a need to set these outside that context. This can also set the default values to be used inside
        the cutcode being processed.

        :param attribute:
        :param value:
        :return:
        """
        if attribute == "speed":
            pass
        print(attribute, value)


    def rapid_mode(self):
        """
        Expects to be in rapid jogging mode.
        :return:
        """
        pass

    def program_mode(self):
        """
        Expects to run jobs at a speed in a programmed mode.
        :return:
        """
        pass

    def raster_mode(self, *args):
        """
        Expects to run a raster job. Raster information is set in special modes to stop the laser head from moving
        too far.

        :return:
        """
        pass

    def wait_finished(self):
        """
        Expects to be caught up such that the next command will happen immediately rather than get queued.

        :return:
        """
        pass

    def function(self, function):
        function()

    def wait(self, secs):
        time.sleep(secs)

    def beep(self):
        """
        Wants a system beep to be issued.

        :return:
        """
        self.service("beep\n")

    def signal(self, signal, *args):
        """
        Wants a system signal to be sent.

        :param signal:
        :param args:
        :return:
        """
        self.service.signal(signal, *args)

    def pause(self):
        """
        Wants the driver to pause.
        :return:
        """
        pass # you don't tell me what to do!

    def resume(self):
        """
        Wants the driver to resume.

        This typically issues from the realtime queue which means it will call even if we tell work_hold that we should
        hold the work.

        :return:
        """
        pass

    def reset(self):
        """
        Wants the job to be aborted and action to be stopped.

        :return:
        """
        pass # Dunno how to do this.

    def status(self):
        """
        Wants a status report of what the driver is doing.
        :return:
        """
        pass
