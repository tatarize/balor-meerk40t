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
        self.job_queue = []
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
        self.loop_job = [job]

    def unset_loop(self):
        self.loop_job = None

    def shutdown(self):
        self._shutdown = True

    def queue_job(self, job):
        if isinstance(job, Job):
            job = job.serialize()
        with self.lock:
            self.job_queue.append(job)

    def data_sender(self):
        queue = []
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
        while not self._shutdown:
            self.service.signal("pipe;usb_status", "Connected")
            if self.job_queue:
                with self.lock:
                    queue.extend(self.job_queue)
                    self.job_queue.clear()
                for q in queue:
                    self.connection.send_packet(q)
                continue
            if self.loop_job is not None:
                for q in self.loop_job:
                    self.connection.send_packet(q)
            else:
                time.sleep(1)  # There is nothing to send.
        # We are shutting down.
        self.connection.close()
        self.connected = False
        self.service.signal("pipe;usb_status", "Disconnected.")
