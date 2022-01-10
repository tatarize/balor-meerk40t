import threading
import time

from balor.GalvoConnection import GalvoConnection


class BalorLooper:
    def __init__(self, service):
        self._shutdown = False
        self.service = service
        self.name = str(self.service)

        self.connection = GalvoConnection(service)

        self._program_queue = []
        self.abort_working_program = False

        self.idle_program = None

        self.process_checks = None

        self.lock = threading.Lock()
        self.connected = False
        self.connecting = False

        # # Typical MeerK40t Driver
        # self.settings = LaserSettings()
        #
        # self.process_item = None
        # self.spooled_item = None
        #
        # self.holds = []
        # self.temp_holds = []
        #
        # self._thread = None
        # self._shutdown = False
        # self.last_fetch = None
        #
        # self.queue = []

    def __repr__(self):
        return "BalorDriver(%s)" % self.name

    def service_detach(self):
        self.shutdown()

    def shutdown(self, *args, **kwargs):
        self._shutdown = True

    def added(self, origin=None, *args):
        self.restart()

    def restart(self):
        self.service.signal("pipe;usb_status", "Restarting...")
        self._shutdown = False
        if self._thread is None:

            def clear_thread(*a):
                self._shutdown = True

            self._thread = self.service.threaded(
                self._driver_threaded,
                result=clear_thread,
                thread_name="Driver(%s)" % self.service.path,
            )
            self._thread.stop = clear_thread
        self.service.threaded(self.run, thread_name="balor-controller")

    def set_loop(self, job):
        self.idle_program = job

    def unset_loop(self):
        self.idle_program = None

    def queue_program(self, job):
        with self.lock:
            # threadsafe
            self._program_queue.append(job)

    def _connect(self):
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

    def run(self):
        """
        The loop will process any programs queued for execution. When those programs are finished,
        we return to center and execute the idle_program job if one exists. If a new item is added to the
        execution queue, we return to origin and execute the queue.

        A program generates data bursts until finished. No guarantee is given as to knowing when or if this function
        will stop providing data. Data must be packets must be correctly defined serialized jobs in bytes. These can be of
        any length provided by the job.serialize() code, but should be evenly divided by 0xC00.
        """
        self._connect()
        while True:
            # Forever Looping.
            if self._shutdown:
                # We have been told to stop.
                break
            if len(self._program_queue):
                # There is active work to do.
                with self.lock:
                    # threadsafe
                    program = self._program_queue.pop()
                if program is not None:
                    # Process all data in the program.
                    for data in program:
                        if self.abort_working_program:
                            # We have been told to abort this work.
                            break
                        self.connection.send_data(data)
                    self.abort_working_program = True
                continue
            if self.process_checks is not None:
                # Run process_check function if it exists. If returns
                if self.process_checks():
                    # If function returns something truthy, we don't check for work and do not idle.
                    continue

            if self.idle_program is not None:
                for data in self.idle_program:
                    if len(self._program_queue):
                        # Stop the Idle Work, we have real work to do.
                        break
                    if self.idle_program is None:
                        # Stop the Idle Work, the program was unset.
                        break
                    self.connection.send_data(data)
                # Finished idle cycle.
                continue
            # There is nothing to send or do.
            time.sleep(1)
        # We are shutting down.
        self.connection.close()
        self.connected = False
        self.service.signal("pipe;usb_status", "Disconnected.")
    #
    # def _driver_threaded(self, *args):
    #     """
    #     Fetch and Execute.
    #
    #     :param args:
    #     :return:
    #     """
    #     while True:
    #         if self._shutdown:
    #             return
    #         if self.spooled_item is None:
    #             self._fetch_next_item_from_spooler()
    #         if self.spooled_item is None:
    #             # There is no data to interpret. Fetch Failed.
    #             if self.context._quit:
    #                 self.context("quit\n")
    #                 self._shutdown = True
    #                 return
    #             time.sleep(0.1)
    #         self._process_spooled_item()
    #
    # def _process_spooled_item(self):
    #     """
    #     Default Execution Cycle. If Held, we wait. Otherwise we process the spooler.
    #
    #     Processes one item in the spooler. If the spooler item is a generator. Process one generated item.
    #     """
    #     if self.hold():
    #         time.sleep(0.01)
    #         return
    #     if self.spooled_item is None:
    #         return  # Fetch Next.
    #
    #     # We have a spooled item to process.
    #     if self.command(self.spooled_item):
    #         self.spooled_item = None
    #         self.service.spooler.pop()
    #         return
    #
    #     # We are dealing with an iterator/generator
    #     try:
    #         e = next(self.spooled_item)
    #         if not self.command(e):
    #             raise ValueError
    #     except StopIteration:
    #         # The spooled item is finished.
    #         self.spooled_item = None
    #         self.service.spooler.pop()
    #
    # def _fetch_next_item_from_spooler(self):
    #     """
    #     Fetches the next item from the spooler.
    #
    #     :return:
    #     """
    #     element = self.service.spooler.peek()
    #
    #     if self.last_fetch is not None:
    #         self.service.channel("spooler")(
    #             "Time between fetches: %f" % (time.time() - self.last_fetch)
    #         )
    #         self.last_fetch = None
    #
    #     if element is None:
    #         return  # Spooler is empty.
    #
    #     self.last_fetch = time.time()
    #
    #     if isinstance(element, int):
    #         self.spooled_item = (element,)
    #     elif isinstance(element, tuple):
    #         self.spooled_item = element
    #     else:
    #         try:
    #             self.spooled_item = element.generate()
    #         except AttributeError:
    #             try:
    #                 self.spooled_item = element()
    #             except TypeError:
    #                 # This could be a text element, some unrecognized type.
    #                 return
    #
    # def command(self, command, *values):
    #     """Commands are middle language LaserCommandConstants there values are given."""
    #     if isinstance(command, tuple):
    #         values = command[1:]
    #         command = command[0]
    #     if not isinstance(command, int):
    #         return False  # Command type is not recognized.
    #
    #     if command == COMMAND_LASER_OFF:
    #         pass
    #     elif command == COMMAND_LASER_ON:
    #         pass
    #     elif command == COMMAND_LASER_DISABLE:
    #         self.laser_disable()
    #     elif command == COMMAND_LASER_ENABLE:
    #         self.laser_enable()
    #     elif command == COMMAND_CUT:
    #         x, y = values
    #         # self.cut(x, y, 1.0)
    #     elif command == COMMAND_MOVE:
    #         x, y = values
    #         # self.move(x, y)
    #     elif command == COMMAND_JOG:
    #         x, y = values
    #         # self.move(x,y)
    #     elif command == COMMAND_JOG_SWITCH:
    #         x, y = values
    #         # self.move(x, y)
    #     elif command == COMMAND_JOG_FINISH:
    #         x, y = values
    #         # self.move(x, y)
    #     elif command == COMMAND_HOME:
    #         # self.home(*values)
    #         pass
    #     elif command == COMMAND_LOCK:
    #         pass
    #     elif command == COMMAND_UNLOCK:
    #         pass
    #     elif command == COMMAND_PLOT:
    #         self.plot_plot(values[0])
    #     elif command == COMMAND_BLOB:
    #         pass
    #     elif command == COMMAND_PLOT_START:
    #         self.plot_start()
    #     elif command == COMMAND_SET_SPEED:
    #         self.settings.speed = values[0]
    #     elif command == COMMAND_SET_POWER:
    #         self.settings.power = values[0]
    #     elif command == COMMAND_SET_PPI:
    #         self.settings.power = values[0]
    #     elif command == COMMAND_SET_PWM:
    #         self.settings.power = values[0]
    #     elif command == COMMAND_SET_STEP:
    #         self.settings.raster_step = values[0]
    #     elif command == COMMAND_SET_OVERSCAN:
    #         self.settings.overscan = values[0]
    #     elif command == COMMAND_SET_ACCELERATION:
    #         self.settings.acceleration = values[0]
    #     elif command == COMMAND_SET_D_RATIO:
    #         self.settings.dratio = values[0]
    #     elif command == COMMAND_SET_DIRECTION:
    #         pass
    #     elif command == COMMAND_SET_INCREMENTAL:
    #         self.set_incremental()
    #     elif command == COMMAND_SET_ABSOLUTE:
    #         self.set_absolute()
    #     elif command == COMMAND_SET_POSITION:
    #         self.set_position(values[0], values[1])
    #     elif command == COMMAND_MODE_RAPID:
    #         pass
    #     elif command == COMMAND_MODE_PROGRAM:
    #         pass
    #     elif command == COMMAND_MODE_RASTER:
    #         pass
    #     elif command == COMMAND_MODE_FINISHED:
    #         pass
    #     elif command == COMMAND_WAIT:
    #         self.wait(values[0])
    #     elif command == COMMAND_WAIT_FINISH:
    #         self.wait_finish()
    #     elif command == COMMAND_BEEP:
    #         self.service("beep\n")
    #     elif command == COMMAND_FUNCTION:
    #         if len(values) >= 1:
    #             t = values[0]
    #             if callable(t):
    #                 t()
    #     elif command == COMMAND_SIGNAL:
    #         if isinstance(values, str):
    #             self.service.signal(values, None)
    #         elif len(values) >= 2:
    #             self.service.signal(values[0], *values[1:])
    #
    #     return True
    #
    # def realtime_command(self, command, *values):
    #     """Asks for the execution of a realtime command. Unlike the spooled commands these
    #     return False if rejected and something else if able to be performed. These will not
    #     be queued. If rejected. They must be performed in realtime or cancelled.
    #     """
    #     try:
    #         if command == REALTIME_PAUSE:
    #             pass
    #         elif command == REALTIME_RESUME:
    #             pass
    #         elif command == REALTIME_RESET:
    #             pass
    #         elif command == REALTIME_STATUS:
    #             pass
    #     except AttributeError:
    #         pass  # Method doesn't exist.
    #
    # def hold(self):
    #     """
    #     Holds are criteria to use to pause the data interpretation. These halt the production of new data until the
    #     criteria is met. A hold is constant and will always halt the data while true. A temp_hold will be removed
    #     as soon as it does not hold the data.
    #
    #     :return: Whether data interpretation should hold.
    #     """
    #     temp_hold = False
    #     fail_hold = False
    #     for i, hold in enumerate(self.temp_holds):
    #         if not hold():
    #             self.temp_holds[i] = None
    #             fail_hold = True
    #         else:
    #             temp_hold = True
    #     if fail_hold:
    #         self.temp_holds = [hold for hold in self.temp_holds if hold is not None]
    #     if temp_hold:
    #         return True
    #     for hold in self.holds:
    #         if hold():
    #             return True
    #     return False
    #
    # def laser_disable(self, *values):
    #     self.settings.laser_enabled = False
    #
    # def laser_enable(self, *values):
    #     self.settings.laser_enabled = True
    #
    # def plot_plot(self, plot):
    #     """
    #     :param plot:
    #     :return:
    #     """
    #     self.queue.append(plot)
    #
    # def plot_start(self):
    #     self.service.controller.queue_program(self.service.cutcode_to_mark_job(self.queue))
    #
    # def set_power(self, power=1000.0):
    #     self.settings.power = power
    #     if self.settings.power > 1000.0:
    #         self.settings.power = 1000.0
    #     if self.settings.power <= 0:
    #         self.settings.power = 0.0
    #
    # def set_ppi(self, power=1000.0):
    #     self.settings.power = power
    #     if self.settings.power > 1000.0:
    #         self.settings.power = 1000.0
    #     if self.settings.power <= 0:
    #         self.settings.power = 0.0
    #
    # def set_pwm(self, power=1000.0):
    #     self.settings.power = power
    #     if self.settings.power > 1000.0:
    #         self.settings.power = 1000.0
    #     if self.settings.power <= 0:
    #         self.settings.power = 0.0
    #
    # def set_overscan(self, overscan=None):
    #     self.settings.overscan = overscan
    #
    # def set_incremental(self, *values):
    #     self.is_relative = True
    #
    # def set_absolute(self, *values):
    #     self.is_relative = False
    #
    # def set_position(self, x, y):
    #     self.current_x = x
    #     self.current_y = y
    #
    # def wait(self, t):
    #     time.sleep(float(t))
    #
    # def wait_finish(self, *values):
    #     """Adds an additional holding requirement if the pipe has any data."""
    #     self.temp_holds.append(lambda: len(self.output) != 0)
    #
    # def status(self):
    #     parts = list()
    #     parts.append("x=%f" % self.current_x)
    #     parts.append("y=%f" % self.current_y)
    #     parts.append("speed=%f" % self.settings.speed)
    #     parts.append("power=%d" % self.settings.power)
    #     status = ";".join(parts)
    #     self.service.signal("driver;status", status)
    #
