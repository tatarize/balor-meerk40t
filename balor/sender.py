# Balor Galvo Laser Control Module
# Copyright (C) 2021-2022 Gnostic Instruments, Inc.
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import usb.core
import usb.util
import time
import sys
import threading

# TODO: compatibility with ezcad .cor files
# TODO: threading (currently it isn't just for testing purposes)
# TODO: should init always be blocking or should it happen in the laser thread?


class BalorException(Exception): pass
class BalorMachineException(BalorException): pass
class BalorCommunicationException(BalorException): pass
class BalorDataValidityException(BalorException): pass

UNKNOWN_03             = 0x0003 # Corresponding list command is "LaserOnPoint"
                                # Does it refer to the red dot aiming laser?
SET_06                 = 0x0006 # Might set travel/jog speed
GET_REGISTER           = 0x0007
GET_SERIAL_NUMBER      = 0x0009 # In EzCAD mine is 32012LI43405B, Version 4.02, LMC V4 FIB
ENABLE_LASER           = 0x0004
EXECUTE_LIST           = 0x0005
GET_XY_POSITION        = 0x000C # Get current galvo position
SET_XY_POSITION        = 0x000D # Travel the galvo xy to specified position
RESET_LIST             = 0x0012
RESTART_LIST           = 0x0013
WRITE_CORRECTION_TABLE = 0x0015
SET_CONTROL_MODE       = 0x0016
SET_DELAY_MODE         = 0x0017
SET_END_OF_LIST        = 0x0019
SET_FIRST_PULSE_KILLER = 0x001A
SET_LASER_MODE         = 0x001B
SET_TIMING             = 0x001C
SET_STANDBY            = 0x001D
SET_PWM_HALF_PERIOD    = 0x001E
WRITE_PORT             = 0x0021
WRITE_ANALOG_PORT      = 0x0022 # At end of cut, seen writing 0x07FF
READ_PORT              = 0x0025
SET_FPK_2E             = 0x002E # First pulse killer related, SetFpkParam2
                                # My ezcad lists 40 microseconds as FirstPulseKiller
                                # EzCad sets it 0x0FFB, 1, 0x199, 0x64
SET_FIBER_32           = 0x0032 # Unknown fiber laser parameter being set
                                # EzCad sets it: 0x0000, 0x0063, 0x03E8, 0x0019
FIBER_33               = 0x0033 # "IPG (i.e. fiber) Open MO" - MO is probably Master Oscillator
                                # (In BJJCZ documentation, the pin 18 on the IPG connector is 
                                #  called "main oscillator"; on the raycus docs it is "emission enable.")
                                # Seen at end of marking operation with all
                                # zero parameters. My Ezcad has an "open MO delay"
                                # of 8 ms
GET_FIBER_34           = 0x0034 # Unclear what this means; there is no
                                # corresponding list command. It might be to
                                # get a status register related to the source.
                                # It is called IPG_GETStMO_AP in the dll, and the abbreviations
                                # MO and AP are used for the master oscillator and power amplifier 
                                # signal lines in BJJCZ documentation for the board; LASERST is 
                                # the name given to the error code lines on the IPG connector.
ENABLE_Z               = 0x003A # Probably fiber laser related
UNKNOWN_41             = 0x0041 # Seen at end of cutting with param 0x0003

class Sender:
    """This is a simplified control class for the BJJCZ (Golden Orange, 
    Beijing JCZ) LMCV4-FIBER-M and compatible boards. It always runs
    machine operations in their own thread, so machine operations are
    non-blocking."""
    ep_hodi  = 0x01 # endpoint for the "dog," i.e. dongle.
    ep_hido  = 0x81 # fortunately it turns out that we can ignore it completely.
    ep_homi = 0x02 # endpoint for host out, machine in. (query status, send ops)
    ep_himo = 0x88 # endpoint for host in, machine out. (receive status reports)
    chunk_size = 12*256

    def __init__(self, machine_index=0, cor_table=None):
        # Lock for controlling access to the USB device.
        self._usb_lock = threading.Lock()

        # Lock for controlling access to the current job.
        self._job_lock = threading.Lock()

        self._condition_register = 0xFFFF
        
        self._device = self._connect_device(machine_index)
        self._init_machine(cor_table)


    def _connect_device(self, machine_index=0):
        devices=list(usb.core.find(find_all=True, idVendor=0x9588, idProduct=0x9899))
        if len(devices) == 0:
            raise BalorMachineException("No compatible engraver machine was found.")

        try:
            device = list(devices)[machine_index]
        except IndexError:
            # Can't find device
            raise BalorMachineException("Invalid machine index %d"%machine_index)

        # if the permissions are wrong, these will throw usb.core.USBError
        device.set_configuration()
        device.reset()

        return device

    def _init_machine(self, cor_table=None):
        """Initialize the machine."""
        self.serial_number = self._send_command(GET_SERIAL_NUMBER)
        self.version = self._send_command(GET_REGISTER, 0x0001)
        self.source_condition,_ = self._send_command(GET_FIBER_34)
        
        # Unknown function
        self._send_command(UNKNOWN_03)

        # Load in-machine correction table
        self._send_correction_table(cor_table)

        self._send_command(ENABLE_LASER)
        self._send_command(SET_CONTROL_MODE, 0)
        self._send_command(SET_LASER_MODE, 1)
        self._send_command(SET_DELAY_MODE, 1)
        self._send_command(SET_TIMING, 1)
        self._send_command(SET_STANDBY, 2000, 20)
        self._send_command(SET_FIRST_PULSE_KILLER, 200)
        self._send_command(SET_PWM_HALF_PERIOD, 125)

        # unknown function
        self._send_command(SET_06, 125)
        # "IPG_OpenMO" (main oscillator?)
        self._send_command(FIBER_33)
        # Unclear if used for anything
        self._send_command(GET_REGISTER, 0)

        # 0x0FFB is probably a 12 bit rendering of int12 -5
        # Apparently some parameters for the first pulse killer
        self._send_command(SET_FPK_2E, 0x0FFB, 1, 409, 100)

        # Unknown fiber laser related command
        self._send_command(SET_FIBER_32, 0, 99, 1000, 25)

        # Is this appropriate for all laser engraver machines?
        self._send_command(WRITE_PORT, 0)
        # Conjecture is that this puts the output port out of a 
        # high impedance state (based on the name in the DLL,
        # ENABLEZ), but who knows, maybe it has to do with the Z
        # axis? Need to get some ezcad captures from the rotary in use.
        # Based on how it's used, it could also be about latching out
        # some of the data that has been set up.
        self._send_command(ENABLE_Z)

        self._send_command(WRITE_ANALOG_PORT, 0x07FF)
        self._send_command(ENABLE_Z)

        


    def _send_correction_table(self, table=None):
        """Send the onboard correction table to the machine."""
        self._send_command(WRITE_CORRECTION_TABLE, 0x0001)
        if table is None:
            blank = bytearray([0]*5)
            for _ in range(65**2):
                self._send_correction_entry(blank)
        else:
            for n in range(65**2):
                self._send_correction_entry(table[n*5:n*5+5])

    def _send_correction_entry(self, correction):
        """Send an individual correction table entry to the machine."""
        query = bytearray([0x10] + [0]*11)
        query[2:2+5] = correction
        if self._device.write(self.ep_homi, query, 100) != 12:
            raise BalorCommunicationException("Failed to write correction entry")



    def _send_command(self, code, *parameters):
        """Send a command to the machine and return the response.
           Updates the host condition register as a side effect."""
        query = bytearray([0]*12)
        query[0] = code & 0x00FF
        query[1] = (code >> 8) & 0x00FF
        for n, parameter in enumerate(parameters):
            query[2*n+2]   = parameter & 0x00FF 
            query[2*n+3] = (parameter >> 8) & 0x00FF
        if self._device.write(self.ep_homi, query, 100) != 12:
            raise BalorCommunicationException("Failed to write command")

        response = self._device.read(self.ep_himo, 8, 100)
        if len(response) != 8:
            raise BalorCommunicationException("Invalid response")
        self._condition_register = response[6]|(response[7]<<8)
        return response[2]|(response[3]<<8), response[4]|(response[5]<<8)
        

    def _send_list_chunk(self, data):
        """Send a command list chunk to the machine."""
        if len(data) != self.chunk_size:
            raise BalorDataValidityException("Invalid chunk size %d"%len(data))

        sent = self._device.write(self.ep_homi, data, 100)
        if sent != len(data):
            raise BalorCommunicationException("Could not send list chunk")

    def _send_list(self, data):
        """Sends a command list to the machine. Breaks it into 3072 byte 
           chunks as needed."""

        while len(data) >= self.chunk_size:
            while not self.is_ready(): pass # FIXME Super blocky; fix this for threaded version
            self._send_list_chunk(data[:self.chunk_size])
            data = data[self.chunk_size:]
    
    def is_ready(self):
        """Returns true if the laser is ready for more data, false otherwise."""
        self._send_command(READ_PORT, 0)
        return bool(self._condition_register & 0x20)

    def is_busy(self):
        """Returns true if the machine is busy, false otherwise;
           Note that running a lighting job counts as being busy."""
        #FIXME acquire lock
        self._send_command(READ_PORT, 0)
        return bool(self._condition_register & 0x04)

    def run_job(self, job_data, callback_finished=None):
        """Run a job once. Optionally, call a callback function when
           the job has finished. If a job is already running, it will
           be aborted and replaced."""

        if self.is_busy(): self.abort()

        self._send_command(WRITE_PORT, 0x001)
        self._send_command(RESET_LIST)
        self.set_xy(0x8000, 0x8000)

        self._send_list(job_data)

        self._send_command(SET_END_OF_LIST)
        self._send_command(EXECUTE_LIST)
        self._send_command(SET_CONTROL_MODE, 1)

    
    def loop_job(self, job_header, job_body, loop_count=0, 
            callback_finished=None):
        """Run a job repetitively. job_header is commands to run only once,
           e.g. to set up travel speed or other parameters; job_body is 
           commands to loop. loop_count is the number of times to repeat the
           job; if it is zero, it repeats until aborted. If there is a job
           already running, it will be aborted and replaced. Optionally,
           calls a callback function when the job is finished."""

    def abort(self):
        """Aborts any job in progress and puts the machine back into an
           idle condition."""

    def set_footswitch_callback(self, callback_footswitch):
        """Sets the callback function for the footswitch."""

    def get_condition(self):
        """Returns the 16-bit condition register value (from whatever
           command was run last.)"""
        return self._condition_register

    #def set_axis_origin(self, which_axis):
    #    """Define the current position of the axis as the origin."""
    #
    #def move_axis(self, which_axis, steps, direction):
    #    """Move the an attached non-galvo (e.g. rotary or Z) axis."""
    #   pass

    def set_xy(self, x, y):
        """Change the galvo position. If the machine is running a job,
           this will abort the job.""" 
        self._send_command(SET_XY_POSITION, x, y)

    def get_xy(self):
        """Returns the galvo position."""
        return self._send_command(GET_XY_POSITION)
    
