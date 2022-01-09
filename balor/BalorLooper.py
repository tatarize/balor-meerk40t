import threading
import time

from balor.GalvoConnection import GalvoConnection
from balor.MSBF import Job


class BalorLooper:
    def __init__(self, service):
        self._shutdown = False
        self.loop_job = None
        self.service = service
        self.connection = GalvoConnection(service)
        self._queue = bytearray()
        self.lock = threading.Lock()
        self.connected = False
        self.connecting = False
        self.restart()

    def service_detach(self):
        self.shutdown()

    def restart(self):
        self.service.signal("pipe;usb_status", "Restarting...")
        self._shutdown = False
        self.service.threaded(self.data_sender, thread_name="balor-controller")

    def set_loop(self, job):
        if isinstance(job, Job):
            job = job.serialize()
        assert(isinstance(job, (bytearray, bytes)))
        self.loop_job = [job]

    def unset_loop(self):
        self.loop_job = None

    def shutdown(self):
        self._shutdown = True

    def queue_job(self, job):
        if isinstance(job, Job):
            job = job.serialize()
        with self.lock:
            self._queue += job

    def data_sender(self):
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
        while not self._shutdown:
            with self.lock:
                data = self._queue
                self._queue = bytearray()
            self.connection.send_data(data)
            if self.loop_job is not None:
                data = self.loop_job
                self.connection.send_data(data)
            else:
                time.sleep(1)  # There is nothing to send.
        # We are shutting down.
        self.connection.close()
        self.connected = False
        self.service.signal("pipe;usb_status", "Disconnected.")
