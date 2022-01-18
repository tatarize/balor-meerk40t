from . import Machine
import importlib
import usb.core
import usb.util
import time
import sys

import threading
class BJJCZ_LMCV4_FIBER_M_LightingHelper:
    def __init__(self, machine):
        self.machine = machine
        self.ready = False
        self.running = False
        self.thread = threading.Thread(
                target=self.loop, args=(), daemon=True)
        self.pattern = []
        self.lock = threading.Lock()    
        self.last_07_report = [0]*8
        self.last_19_status_report = [0]*8
        self.last_status_report = [0]*8
        self.thread.start()
        

    def set_pattern(self, pattern):
        self.pattern = pattern

    def get_last_status_report(self):
        self.lock.acquire()
        sr = self.last_status_report
        sr7 = self.last_07_report
        sr19 = self.last_19_status_report
        self.lock.release()
        return sr, sr7, sr19

    def send_pattern(self, packet):

        # one of these does the resetting (or some combination does)
        self.machine.send_query_status(0x0021, 0x0100) # writeport
        reply = self.machine.get_status_report()
        #print ("21 REPLY:", ' '.join(['%02X'%x for x in reply]), file=sys.stderr)
        self.machine.send_query_status(0x0007, 0x0100) # getversion
        reply = self.machine.get_status_report()
        #print ("07-1 REPLY:", ' '.join(['%02X'%x for x in reply]), file=sys.stderr)
        self.machine.send_query_status(0x0012) # reset list
        reply = self.machine.get_status_report()
        #print ("12 REPLY:", ' '.join(['%02X'%x for x in reply]), file=sys.stderr)
        self.machine.send_query_status(0x000C) # get position xy
        reply = self.machine.get_status_report()
        #print ("0C REPLY:", ' '.join(['%02X'%x for x in reply]), file=sys.stderr)
        
        # Seems to do the travel
        #self.machine.send_query_status(0x000D, 0x8001, 0x8001)
        #reply = self.machine.get_status_report()
        #print ("0D REPLY:", ' '.join(['%02X'%x for x in reply]), file=sys.stderr)

        #for _ in range(52):
        #    self.machine.send_query_status(0x0025)
        #    reply = self.machine.get_status_report()


        #print ("**Sending pattern of len", len(packet), ":", ' '.join(['%02X'%x for x in packet]), file=sys.stderr)
        self.machine.send_raw(packet)
        self.machine.send_query_status(0x19) # set end of list
        self.last_19_status_report = self.machine.get_status_report()
        self.machine.wait_for_rv_bits(query=0x25, wait_high=0x20)

        # Probably this means "run program."
        self.machine.send_query_status(0x0005) # executelist 
        reply = self.machine.get_status_report()
        #print ("05 REPLY:", ' '.join(['%02X'%x for x  in reply]), file=sys.stderr)


    def loop(self):
        while 1:
            self.machine.lock.acquire()
            self.machine.send_query_status(0x25)
            last_status_report = self.machine.get_status_report()
            self.machine.lock.release()

            self.machine.lock.acquire()
            self.machine.send_query_status(0x07)
            last_07_status_report = self.machine.get_status_report()
            self.machine.lock.release()

            ready = last_07_status_report[6]&0x20
            running = last_07_status_report[6]&4
            self.ready = ready
            self.running = running

            if ready and not running and self.pattern:
                self.send_pattern(self.pattern)
                self.pattern = []

            self.lock.acquire()
            self.last_status_report = last_status_report
            self.last_07_report = last_07_status_report
            self.lock.release()

            time.sleep(0.01)


class BJJCZ_LMCV4_FIBER_M(Machine.Machine):
    packet_size=3072
    VID = 0x9588
    PID = 0x9899
    ep_hodi  = 0x01 # endpoint for the "dog," i.e. dongle.
    ep_hido  = 0x81 # fortunately it turns out that we can ignore it completely.
    ep_homi = 0x02 # endpoint for host out, machine in. (query status, send ops)
    ep_himo = 0x88 # endpoint for host in, machine out. (receive status reports)
    
    def __init__(self, index=0):
        self.lock = threading.Lock()            
        self.lighting_helper = None
        # If this isn't working, please insert ASCII art of an obscene gesture 
        # of your choice directed at python's importing mechanisms.
        from . import BJJCZ_LMCV4_FIBER_M_blobs 
        self.sequences = BJJCZ_LMCV4_FIBER_M_blobs
        # tell me how great python is at metaprogramming again, please
        #self.sequences = importlib.import_module(self.__class__.__name__+"_blobs", '.')
        
        self.device = self.connect_device(index)
        self.send_sequence(self.sequences.init)
        # We sacrifice this time at the altar of the Unknown Race Condition.
        time.sleep(0.1)

    def send_query_status(self, query_code=0x0025, parameter=0x0000, parameter2=0x0000):
        query = bytearray([0]*12)
        query[0] = query_code&0xFF
        query[1] = query_code>>8
        query[2] = (parameter&0xFF)
        query[3] = (parameter&0xFF00)>>8
        query[4] = parameter2&0xFF
        query[5] = (parameter2&0xFF00)>>8
        #print ("Sent query status", ' '.join(['%02X'%x for x in query]), file=sys.stderr)
        assert self.device.write(self.ep_homi, query, 100) == len(query)

    def send_raw(self, packet):
        assert self.device.write(self.ep_homi, packet, 100) == len(packet)

    def get_status_report(self):
        return self.device.read(self.ep_himo, 8, 100)

    def connect_device(self, index=0):
        devices=usb.core.find(find_all=True, idVendor=0x9588, idProduct=0x9899)
        device = list(devices)[index]
        self.manufacturer = usb.util.get_string(device, device.iManufacturer)
        self.product = usb.util.get_string(device, device.iProduct)
        device.set_configuration() # It only has one.
        if self.verbosity: print ("Connected to", self.manufacturer, self.product)
        device.reset()
        return device
    
    def send_sequence(self, sequence, substitutions=[], substitution_generator=None):
        #print ("Sending Sequence...")
        for n,(direction, endpoint, data) in enumerate(sequence):
            if substitution_generator and n in substitutions: data = substitution_generator(data)
            if direction: # Read
                reply = self.device.read(endpoint, len(data), 1000)
                if bytes(reply) != bytes(data) and self.verbosity:
                     print (" REFR:", ' '.join(['%02X'%x for x in data]))
                     print ("      ", ' '.join(['||' if x==y else 'XX' for x,y in zip(data,reply)]))
                     print ("  GOT:", ' '.join(['%02X'%x for x in reply]))
                elif self.verbosity > 1:
                     print ("LASER:", ' '.join(['%02X'%x for x in reply]))
            else:
                if self.verbosity > 1:
                    print(" HOST:",  ' '.join(['%02X'%x for x in data]))
                assert self.device.write(endpoint, data, 1000) == len(data)
            if self.verbosity > 1: print ("")
        #print ("Sequence complete.")

    def start_lighting_thread(self):
        self.lighting_helper = BJJCZ_LMCV4_FIBER_M_LightingHelper(self)

        return self.lighting_helper

    def light(self, cycles=4, delay=1, substitution_generator=None, noend=False):
        self.lock.acquire()
        if self.verbosity: print ("Starting lighting")
        self.send_sequence(self.sequences.start, 
                substitutions=self.sequences.start_overwrites,
                substitution_generator=substitution_generator)

        for _ in range(cycles):
            if self.verbosity: print ("Run lighting")
            self.send_sequence(self.sequences.run, 
                    substitutions=self.sequences.run_overwrites,
                    substitution_generator=substitution_generator)

        if self.verbosity: print ("Ending lighting")
        if not noend: self.send_sequence(self.sequences.end)
        self.lock.release()
    # Sequence
    # prefix: 0a6e-a89
    # (data)
    # 19, 7
    # (Data)
    # a96-aa1   19, 05, 07
    # (Data)
    # Then read 19,16 (0aa4-aab)

    # Then read 0x07 0x00 0x01 until 6 goes from 24 to 20
    # then c220-c243
    #./pickle2py.py mark_prefix.pickle:mark_prefix mark_suffix.pickle:mark_suffix >>
    # ../../balor/BJJCZ_LMCV4_FIBER_M_blobs.py 
    # ./pickle2py.py separator.pickle:mark_packet_separator >> ../../balor/BJJCZ_LMCV4_FIBER_M_blobs.py
    def mark(self, data):
        assert not len(data) % self.packet_size
        self.lock.acquire()
        if self.verbosity: print ("Mark prefix")
        self.send_sequence(self.sequences.mark_prefix)
        count = self.wait_for_rv_bits(0x07, 0x20)
        if self.verbosity: print ("Waited %d cycles for laser to be ready."%count)

        i = 0
        while i < len(data):
            packet = data[i:i+self.packet_size]
            if self.verbosity: print ("SENDING PACKET HERE %d:%d"%(i, i+self.packet_size))
            i += self.packet_size
            assert self.device.write(self.ep_homi, packet, 1000) == self.packet_size
            
            if i == len(data):
                if self.verbosity: print ("End data separator")
                self.send_sequence(self.sequences.mark_data_end)
            else:
                if self.verbosity: print ("Mark packet separator")
                self.send_sequence(self.sequences.mark_packet_separator)
            count = self.wait_for_rv_bits(0x07, 0x20)
            if self.verbosity: print ("Waited %d cycles for laser to be ready for next packet."%count)

                

        # Now, wait for the reply to 7 0 1, byte[6] to go from 24 to 20
        # which apparently means we are done?
        # FIXME: I bet there is something to do when writing a really big
        # file and the buffer gets full.

        count = self.wait_for_rv_bits(0x07, 0x20, 0x04)        
        #state = None
        #i = 0
        #while state != 0x20:
        #    assert self.device.write(self.ep_homi,
        #            bytearray([0x07, 0x00, 0x01]+9*[0]), 1000) == 12
        #    reply = self.device.read(self.ep_himo, 8, 1000)
        #    state = reply[6]
        #    i += 1
        #    if self.verbosity and not i%2500: 
        #        print ("Still operating at %d, state="%i, ' '.join(['%02X'%x for x in reply]))
        if self.verbosity: print ("Waited %d cycles for laser to be done."%count)
        if self.verbosity: print ("Mark suffix")
        self.send_sequence(self.sequences.mark_suffix)
        self.lock.release()

    def wait_for_rv_bits(self, query=0x07, wait_high=0x20, wait_low=0):
        count = 0
        state = None
        while state is None or (state&wait_low) or not (state&wait_high):
            assert self.device.write(self.ep_homi,
                bytearray([query, 0x00, 0x01]+9*[0]), 1000) == 12
            reply = self.device.read(self.ep_himo, 8, 1000)
            state = reply[6]
            count += 1
            # Might want to add a delay I guess
        return count

    def close(self):
        if self.verbosity: print ("Disconnecting from laser.")
        self.send_sequence(self.sequences.quit)
        if self.verbosity: print ("Closing USB device.")
        usb.util.dispose_resources(self.device)
        self.device = None

