from . import Machine
import importlib
import usb.core
import usb.util
import time

class BJJCZ_LMCV4_FIBER_M(Machine.Machine):
    packet_size=3072
    VID = 0x9588
    PID = 0x9899
    ep_hodi  = 0x01 # endpoint for the "dog," i.e. dongle.
    ep_hido  = 0x81 # fortunately it turns out that we can ignore it completely.
    ep_homi = 0x02 # endpoint for host out, machine in. (query status, send ops)
    ep_himo = 0x88 # endpoint for host in, machine out. (receive status reports)
    
    def __init__(self, index=0):
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


    def light(self, cycles=4, delay=1, substitution_generator=None, noend=False):
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

