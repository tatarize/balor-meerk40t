import threading
import time

from balor.GalvoConnection import GalvoConnection


class BalorLooper:
    def __init__(self, service):
        self._shutdown = False
        self.service = service
        self.connection = GalvoConnection(service)

        self._program_queue = []
        self.abort_working_program = False

        self.idle_program = None

        self.process_checks = None

        self.lock = threading.Lock()
        self.connected = False
        self.connecting = False
        self.restart()

    def service_detach(self):
        self.shutdown()

    def restart(self):
        self.service.signal("pipe;usb_status", "Restarting...")
        self._shutdown = False
        self.service.threaded(self.run, thread_name="balor-controller")

    def set_loop(self, job):
        self.idle_program = job

    def unset_loop(self):
        self.idle_program = None

    def shutdown(self):
        self._shutdown = True

    def queue_program(self, job):
        with self.lock:
            # threadsafe
            self._program_queue.append(job)

    def run(self):
        """
        The loop will process any programs queued for execution. When those programs are finished,
        we return to center and execute the idle_program job if one exists. If a new item is added to the
        execution queue, we return to origin and execute the queue.

        A program generates data bursts until finished. No guarantee is given as to knowing when or if this function
        will stop providing data. Data must be packets must be correctly defined serialized jobs in bytes. These can be of
        any length provided by the job.serialize() code, but should be evenly divided by 0xC00.
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
