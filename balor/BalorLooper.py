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
        self.service.threaded(self.data_sender, thread_name="balor-controller")

    def set_loop(self, job):
        if isinstance(job, Job):
            job = job.serialize()
        self.loop_job = job

    def shutdown(self):
        self._shutdown = True

    def queue_job(self, job):
        if isinstance(job, Job):
            job = job.serialize()
        with self.lock:
            self.job_queue.append(job)

    def data_sender(self):
        queue = []
        connected = False
        while not connected:
            connected = self.connection.open()
            if not connected:
                self.service.signal("pipe;usb_status", "Not Connected.")
                time.sleep(0.5)
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
                time.sleep(0.5) # There is nothing to send.
        # We are shutting down.
        self.connection.close()
        self.service.signal("pipe;usb_status", "Disconnected.")
