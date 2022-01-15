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

class BalorException(Exception): pass
class BalorMachineException(BalorException): pass
class BalorCommunicationException(BalorException): pass
class BalorDataValidityException(BalorException): pass

# fmt: off
DISABLE_LASER          = 0x0002
UNKNOWN_03             = 0x0003 # Corresponding list command is "LaserOnPoint"
                                # Does it refer to the red dot aiming laser?
SET_06                 = 0x0006 # Might set travel/jog speed
SET_PWM_PULSE_WIDTH    = 0x0006
GET_REGISTER           = 0x0007
GET_SERIAL_NUMBER      = 0x0009 # In EzCAD mine is 32012LI43405B, Version 4.02, LMC V4 FIB
ENABLE_LASER           = 0x0004
EXECUTE_LIST           = 0x0005
GET_LIST_STATUS        = 0x000A
GET_XY_POSITION        = 0x000C # Get current galvo position
SET_XY_POSITION        = 0x000D # Travel the galvo xy to specified position
LASER_SIGNAL_OFF       = 0x000E
LASER_SIGNAL_ON        = 0x000F
WRITE_CORRECTION_LINE  = 0x0010
RESET_LIST             = 0x0012
RESTART_LIST           = 0x0013
WRITE_CORRECTION_TABLE = 0x0015
SET_CONTROL_MODE       = 0x0016
SET_DELAY_MODE         = 0x0017
SET_MAX_POLY_DELAY     = 0x0018
SET_END_OF_LIST        = 0x0019
SET_FIRST_PULSE_KILLER = 0x001A
SET_LASER_MODE         = 0x001B
SET_TIMING             = 0x001C
SET_STANDBY            = 0x001D
SET_PWM_HALF_PERIOD    = 0x001E
STOP_EXECUTE           = 0x001F
STOP_LIST              = 0x0020
WRITE_PORT             = 0x0021
WRITE_ANALOG_PORT_1    = 0x0022 # At end of cut, seen writing 0x07FF
WRITE_ANALOG_PORT_2    = 0x0023
WRITE_ANALOG_PORT_X    = 0x0024
READ_PORT              = 0x0025
SET_AXIS_MOTION_PARAM  = 0x0026
SET_AXIS_ORIGIN_PARAM  = 0x0027
GO_TO_AXIS_ORIGIN      = 0x0028
MOVE_AXIS_TO           = 0x0029
GET_AXIS_POSITION      = 0x002A
GET_FLY_WAIT_COUNT     = 0x002B
GET_MARK_COUNT         = 0x002D
SET_FPK_2E             = 0x002E # First pulse killer related, SetFpkParam2
                                # My ezcad lists 40 microseconds as FirstPulseKiller
                                # EzCad sets it 0x0FFB, 1, 0x199, 0x64
IPG_CONFIG_1           = 0x002F
IPG_CONFIG_2           = 0x0030
LOCK_INPUT_PORT        = 0x0031
SET_FIBER_32           = 0x0032 # Unknown fiber laser parameter being set
                                # EzCad sets it: 0x0000, 0x0063, 0x03E8, 0x0019
FIBER_33               = 0x0033 # "IPG (i.e. fiber) Open MO" - MO is probably Master Oscillator
                                # (In BJJCZ documentation, the pin 18 on the IPG connector is 
                                #  called "main oscillator"; on the raycus docs it is "emission enable.")
                                # Seen at end of marking operation with all
                                # zero parameters. My Ezcad has an "open MO delay"
                                # of 8 ms
IPG_OPEN_MO            = 0x0033
GET_FIBER_34           = 0x0034 # Unclear what this means; there is no
                                # corresponding list command. It might be to
                                # get a status register related to the source.
                                # It is called IPG_GETStMO_AP in the dll, and the abbreviations
                                # MO and AP are used for the master oscillator and power amplifier 
                                # signal lines in BJJCZ documentation for the board; LASERST is 
                                # the name given to the error code lines on the IPG connector.
IPG_GET_StMO_AP        = 0x0034
GET_USER_DATA          = 0x0036
ENABLE_Z_2             = 0x0039
GET_FLY_SPEED          = 0x0038
ENABLE_Z               = 0x003A # Probably fiber laser related
SETZDATA               = 0x003B
SET_SPI_SIMMER_CURRENT = 0x003C
IS_LITE_VERSION        = 0x0040
UNKNOWN_41             = 0x0041 # Seen at end of cutting with param 0x0003
GET_MARK_TIME          = 0x0041
SET_FPK_PARAM          = 0x0062  # Probably "first pulse killer" = fpk
# fmt: on


class Sender:
    """This is a simplified control class for the BJJCZ (Golden Orange, 
    Beijing JCZ) LMCV4-FIBER-M and compatible boards. All operations are blocking
    so it should probably run in its own thread for nontrivial applications.
    It does have an .abort() method that it is expected will be called 
    asynchronously from another thread."""
    sleep_time = 0.001

    # We include this "blob" here (the contents of which are all well-understood) to 
    # avoid introducing a dependency on job generation from within the sender.
    # It just consists of the new job command followed by a bunch of NOPs.
    _abort_list_chunk = (
               bytearray([0x51, 0x80] + [0x00]*10)       # New job
             + bytearray(([0x02, 0x80] + [0x00]*10)*255) # NOP
            )

    def __init__(self, machine_index=0, cor_table=None,
            first_pulse_killer=200, pwm_half_period=125,
            standby_param_1=2000, standby_param_2=20, timing_mode=1, delay_mode=1,
            laser_mode=1, control_mode=0, footswitch_callback=None, debug=False, mock=False):
        self._abort_flag = False
        self._aborted_flag = False
        self._machine_index = machine_index
        self._cor_table=cor_table
        self._first_pulse_killer=first_pulse_killer
        self._pwm_half_period=pwm_half_period
        self._standby_param_1=standby_param_1
        self._standby_param_2=standby_param_2
        self._timing_mode = timing_mode
        self._delay_mode=delay_mode
        self._laser_mode=laser_mode
        self._control_mode=control_mode
        self._footswitch_callback = footswitch_callback
        self._debug = debug

        if not mock:
            self._usb_connection = UsbConnection(self._machine_index, debug=debug)
        else:
            self._usb_connection = MockConnection(self._machine_index, debug=debug)

    def open(self):
        self._usb_connection.open()
        self._init_machine()

    def close(self):
        self._shutdown_machine()
        self._usb_connection.close()

    def _send_command(self, *args):
        return self._usb_connection.send_command(*args)

    def _send_correction_entry(self, *args):
        self._usb_connection.send_correction_entry(*args)

    def _send_list_chunk(self, *args):
        self._usb_connection.send_list_chunk(*args)

    def _init_machine(self):
        """Initialize the machine."""
        self.serial_number = self.raw_get_serial_no()
        self.version = self.raw_get_version()
        self.source_condition,_ = self._usb_connection.send_command(GET_FIBER_34)
        
        # Unknown function
        self._send_command(UNKNOWN_03)

        # Load in-machine correction table
        self._send_correction_table(self._cor_table)

        self.raw_enable_laser()
        self.raw_set_control_mode(self._control_mode,0)
        self.raw_set_laser_mode(self._laser_mode, 0)
        self.raw_set_delay_mode(self._delay_mode, 0)
        self.raw_set_timing(self._timing_mode, 0)
        self.raw_set_standby(self._standby_param_1, self._standby_param_2, 0, 0)
        self.raw_set_first_pulse_killer(self._first_pulse_killer, 0)
        self.raw_set_pwm_half_period(self._pwm_half_period, 0)

        # unknown function
        self.raw_set_pwm_pulse_width(125, 0)
        # "IPG_OpenMO" (main oscillator?)
        self.raw_ipg_open_mo(0, 0)
        # Unclear if used for anything
        self._send_command(GET_REGISTER, 0)

        # 0x0FFB is probably a 12 bit rendering of int12 -5
        # Apparently some parameters for the first pulse killer
        self.raw_set_fpk_param_2(0xFFB, 1, 409, 100)

        # Unknown fiber laser related command
        self._send_command(SET_FIBER_32, 0, 99, 1000, 25)

        # Is this appropriate for all laser engraver machines?
        self.raw_write_port(0)

        # Conjecture is that this puts the output port out of a 
        # high impedance state (based on the name in the DLL,
        # ENABLEZ)
        # Based on how it's used, it could also be about latching out
        # some of the data that has been set up.
        self.raw_enable_z()

        # We don't know what this does, since this laser's power is set
        # digitally
        self.raw_write_analog_port_1(0x07FF, 0)
        self.raw_enable_z()

    def _shutdown_machine(self):
        pass

    def _send_correction_table(self, table=None):
        """Send the onboard correction table to the machine."""
        self.raw_write_correction_table(True)
        if table is None:
            blank = bytearray([0]*5)
            for _ in range(65**2):
                self._send_correction_entry(blank)
        else:
            for n in range(65**2):
                self._send_correction_entry(table[n*5:n*5+5])

    def _send_list(self, data):
        """Sends a command list to the machine. Breaks it into 3072 byte
           chunks as needed. Returns False if the sending is aborted,
           True if successful."""

        while len(data) >= 0xC00:
            while not self.is_ready():
                if self._abort_flag:
                    return False
                time.sleep(self.sleep_time)
            self._usb_connection.send_list_chunk(data[:0xC00])
            data = data[0xC00:]

        return True

    def is_ready(self):
        """Returns true if the laser is ready for more data, false otherwise."""
        self.read_port()
        return bool(self._usb_connection.status & 0x20)

    def is_busy(self):
        """Returns true if the machine is busy, false otherwise;
           Note that running a lighting job counts as being busy."""
        self.read_port()
        return bool(self._usb_connection.status & 0x04)

    def execute(self, job_data, loop_count=True,
                callback_finished=None, prefix_job=None):
        """Run a job. loop_count is the number of times to repeat the
           job; if it is True, it repeats until aborted. If there is a job
           already running, it will be aborted and replaced. Optionally,
           calls a callback function when the job is finished.
           Optionally, a "prefix job" can be run before the loop, which will be
           run only once.
           The loop job can either be regular data in multiples of 3072 bytes, or
           it can be a callable that provides data as above on command."""
        if self.is_busy():
            self.abort()
        while self.is_busy():
            time.sleep(self.sleep_time)
            if self._abort_flag:
                self._abort()
                return False

        self.raw_write_port(0x0001)
        self.raw_reset_list()
        self.set_xy(0x8000, 0x8000)

        while loop_count:
            data = prefix_job if prefix_job else (job_data(loop_count) if callable(job_data) else job_data)

            self.raw_reset_list()

            if not self._send_list(data):
                self._abort()
                return False

            self.raw_set_end_of_list()
            self.raw_execute_list()
            self.raw_set_control_mode(1,0)

            while self.is_busy():  # or not self.is_ready():
                # time.sleep(self.sleep_time)
                if self._abort_flag:
                    self._abort()
                    return False

            prefix_job = None
            if loop_count is not True:
                loop_count -= 1

        return True

    def run_job(self, job_data):
        """Run a job once. The function returns when the machine is finished
           executing the job, or when the run is aborted. Returns True if the
           job finished, False otherwise. Any existing job will be aborted."""
        return self.execute(job_data, 1)

    loop_job = execute

    def abort(self):
        """Aborts any job in progress and puts the machine back into an
           idle ready condition."""
        self._aborted_flag = False
        self._abort_flag = True
        
        while not self._aborted_flag:
            time.sleep(self.sleep_time)

        self._abort_flag = False
        self._aborted_flag = False

    def _abort(self):
        self.raw_reset_list()
        self._send_list_chunk(self._abort_list_chunk)

        self.raw_set_end_of_list()
        self.raw_execute_list()

        while self.is_busy():
            time.sleep(self.sleep_time)

        self.set_xy(0x8000, 0x8000)
        self._aborted_flag = True

    def set_footswitch_callback(self, callback_footswitch):
        """Sets the callback function for the footswitch."""
        self._footswitch_callback = callback_footswitch

    def get_condition(self):
        """Returns the 16-bit condition register value (from whatever
           command was run last.)"""
        return self._usb_connection.status

    def read_port(self):
        port, _ = self._send_command(READ_PORT, 0)
        if port & 0x8000 and self._footswitch_callback:
            callback = self._footswitch_callback
            self._footswitch_callback = None
            callback(port)

        return port

    def set_xy(self, x, y):
        """Change the galvo position. If the machine is running a job,
           this will abort the job.""" 
        self._send_command(SET_XY_POSITION, x, y)

    def get_xy(self):
        """Returns the galvo position."""
        return self._send_command(GET_XY_POSITION)

    #############################
    # Raw LMC Interface Commands.
    #############################

    def raw_disable_laser(self):
        """
        No parameters.
        :return:
        """
        return self._send_command(DISABLE_LASER)

    def raw_enable_laser(self):
        """
        No parameters.
        :return:
        """
        return self._send_command(ENABLE_LASER)

    def raw_execute_list(self):
        """
        No parameters.
        :return: value response
        """
        return self._send_command(EXECUTE_LIST)

    def raw_set_pwm_pulse_width(self, s1: int, value: int):
        """
        2 Param: Stack, Value
        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(SET_PWM_PULSE_WIDTH, s1, value)

    def raw_get_version(self):
        """
        No set parameters but 1 is always sent.
        :return: value response
        """
        return self._send_command(GET_REGISTER, 1)

    def raw_get_serial_no(self):
        """
        No parameters

        Reply is presumably a serial number.

        :return: value response
        """
        return self._send_command(GET_SERIAL_NUMBER)

    def raw_get_list_status(self):
        """
        No parameters
        :return:  value response
        """
        return self._send_command(GET_LIST_STATUS)

    def raw_get_xy_position(self):
        """
        No parameters

        The reply to this is the x, y coords and should be parsed.
        :return: value response
        """
        return self._send_command(GET_XY_POSITION)

    def raw_set_xy_position(self, x, y):
        """
        Move to X Y location

        :param x:
        :param y:
        :return: value response
        """
        return self._send_command(SET_XY_POSITION, int(x), int(y))

    def raw_laser_signal_off(self):
        """
        No parameters
        :return: value response
        """
        return self._send_command(LASER_SIGNAL_OFF)

    def raw_laser_signal_on(self):
        """
        No parameters
        :return: value response
        """
        return self._send_command(LASER_SIGNAL_ON)

    def raw_reset_list(self):
        """
        No parameters.
        :return: value response
        """
        return self._send_command(RESET_LIST)

    def raw_restart_list(self):
        """
        No parameters.
        :return: value response
        """
        return self._send_command(RESTART_LIST)

    def raw_write_correction_line(self, p1, p2, p3, p4):
        """
        4 parameters.

        Writes a single line of a correction table. 2 entries.

        dx1, dy1, dx2, dy2

        :param p1:
        :param p2:
        :param p3:
        :param p4:
        :return:
        """
        self._send_command(WRITE_CORRECTION_LINE, p1, p2, p3, p4)

    def raw_write_correction_table(self, p1: bool):
        """
        This function would govern the interactions with the cor table command including sending the 0x10 command sends
        for the entire table.
        :param p1:
        :param table:
        :return: value response
        """
        return self._send_command(WRITE_CORRECTION_TABLE, int(p1))

    def raw_set_control_mode(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(SET_CONTROL_MODE, int(s1), int(value))

    def raw_set_delay_mode(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(SET_DELAY_MODE, int(s1), int(value))

    def raw_set_max_poly_delay(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(SET_MAX_POLY_DELAY, int(s1), int(value))

    def raw_set_end_of_list(self):
        """
        No parameters
        :return: value response
        """
        return self._send_command(SET_END_OF_LIST)

    def raw_set_first_pulse_killer(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(SET_FIRST_PULSE_KILLER, s1, value)

    def raw_set_laser_mode(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(SET_LASER_MODE, s1, value)

    def raw_set_timing(self, s1: int, value: int):
        """
        2 parameters.
        stack, value
        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(SET_TIMING, s1, value)

    def raw_set_standby(self, v1: int, v2: int, v3: int, value: int):
        """
        4 parameters
        variable, variable, variable, value
        :param v1:
        :param v2:
        :param v3:
        :param value:
        :return: value response
        """
        return self._send_command(SET_STANDBY, v1, v2, v3, value)

    def raw_set_pwm_half_period(self, s1: int, value: int):
        """
        2 parameters
        stack, value

        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(SET_PWM_HALF_PERIOD, s1, value)

    def raw_stop_execute(self):
        """
        No parameters.

        :return: value response
        """
        return self._send_command(STOP_EXECUTE)

    def raw_stop_list(self):
        """
        No parameters

        :return: value response
        """
        return self._send_command(STOP_LIST)

    def raw_write_port(self, v1: int = 0, s1: int = 0, value: int = 0):
        """
        3 parameters.
        variable, stack, value

        :param v1:
        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(WRITE_PORT, v1, s1, value)

    def raw_write_analog_port_1(self, s1: int, value: int):
        """
        2 parameters.
        stack, value

        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(WRITE_ANALOG_PORT_1, s1, value)

    def raw_write_analog_port_2(self, s1: int, value: int):
        """
        3 parameters.
        0, stack, value

        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(WRITE_ANALOG_PORT_2, 0, s1, value)

    def raw_write_analog_port_x(self, v1: int, s1: int, value: int):
        """
        3 parameters.
        variable, stack, value

        :param v1:
        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(WRITE_ANALOG_PORT_X, v1, s1, value)

    def raw_read_port(self):
        """
        No parameters

        :return: Status Information
        """
        return self._send_command(READ_PORT)

    def raw_set_axis_motion_param(self, v1: int, s1: int, value: int):
        """
        3 parameters.
        variable, stack, value

        :return: value response
        """
        return self._send_command(SET_AXIS_MOTION_PARAM, v1, s1, value)

    def raw_set_axis_origin_param(self, v1: int, s1: int, value: int):
        """
        3 parameters.
        variable, stack, value

        :return: value response
        """
        return self._send_command(SET_AXIS_ORIGIN_PARAM, v1, s1, value)

    def raw_axis_go_origin(self, v0: int):
        """
        1 parameter
        variable

        :param v0:
        :return: value response
        """
        return self._send_command(GO_TO_AXIS_ORIGIN, v0)

    def raw_move_axis_to(self, axis, coord):
        """
        This typically accepted 1 32 bit int and used bits 1:8 and then 16:24 as parameters.

        :param axis: axis being moved
        :param coord: coordinate being matched
        :return: value response
        """
        return self._send_command(MOVE_AXIS_TO, axis, coord)

    def raw_get_axis_pos(self, s1: int, value: int):
        """
        2 parameters

        stack, value

        :param s1:
        :param value:
        :return: axis position?
        """
        return self._send_command(GET_AXIS_POSITION, s1, value)

    def raw_get_fly_wait_count(self, b1: bool):
        """
        1 parameter
        bool

        :param b1:
        :return: flywaitcount?
        """
        return self._send_command(GET_FLY_WAIT_COUNT, int(b1))

    def raw_get_mark_count(self, p1: bool):
        """
        1 parameter
        bool

        :param p1:
        :return: markcount?
        """
        return self._send_command(GET_MARK_COUNT, int(p1))

    def raw_set_fpk_param_2(self, v1, v2, v3, s1):
        """
        4 parameters
        variable, variable, variable stack

        :param v1:
        :param v2:
        :param v3:
        :param s1:
        :return:  value response
        """
        return self._send_command(SET_FPK_2E, v1, v2, v3, s1)

    def raw_ipg_open_mo(self, s1: int, value: int):
        """
        2 parameters
        stack, value

        :param s1:
        :param value:
        :return: value response
        """
        return self._send_command(IPG_OPEN_MO, s1, value)

    def raw_ipg_get_st_mo_ap(self):
        """
        No parameters

        :return: value response
        """
        return self._send_command(IPG_GET_StMO_AP)

    def raw_enable_z(self):
        """
        No parameters

        :return: value response
        """
        return self._send_command(ENABLE_Z)

    def raw_enable_z_2(self):
        """
        No parameters

        Alternate command. if unknown==0

        :return: value response
        """
        return self._send_command(ENABLE_Z_2)

    def raw_set_z_data(self, v1, s1, v2):
        """
        3 parameters

        variable, stack, variable

        :param v1:
        :param s1:
        :param v2:
        :return: value response
        """
        return self._send_command(SETZDATA, v1, s1, v2)

    def raw_set_spi_simmer_count(self, v1, s1):
        """
        2 parameters
        variable, stack

        :param v1:
        :param s1:
        :return: value response
        """
        return self._send_command(SET_SPI_SIMMER_CURRENT, v1, s1)

    def raw_set_fpk_param(self, v1, v2, v3, s1):
        """
        Probably "first pulse killer" = fpk
        4 parameters
        variable, variable, variable, stack

        :param v1:
        :param v2:
        :param v3:
        :param s1:
        :return: value response
        """
        return self._send_command(SET_FPK_PARAM, v1, v2, v3, s1)

    def raw_is_lite_version(self):
        """
        no parameters.

        Only called for true.

        :return: value response
        """
        return self._send_command(IS_LITE_VERSION, 1)

    def raw_unknown_init_24(self, s1: int, value: int):
        """
        2 parameters

        stack, value

        :param s1:
        :param value:
        :return:
        """
        return self._send_command(WRITE_ANALOG_PORT_X, s1, value)

    def raw_get_fly_speed(self, p1, p2, p3, p4):
        """

        :param p1:
        :param p2:
        :param p3:
        :param p4:
        :return:
        """
        self._send_command(GET_FLY_SPEED, p1, p2, p3, p4)

    def raw_set_ipg_config(self, p1, p2):
        self.raw_ipg_config_1(0, p1, p2)

    def raw_get_ipg_config(self):
        self.raw_ipg_config_1(1, 0, 0)

    def raw_ipg_config_1(self, p1, p2, p3):
        self._send_command(IPG_CONFIG_1, p1, p2, p3)

    def raw_lock_input_port(self, p1):
        """
        p1 varies based on call.

        :param p1:
        :return:
        """
        self._send_command(LOCK_INPUT_PORT, p1)

    def raw_clear_lock_input_port(self):
        self.raw_lock_input_port(0x04)

    def raw_enable_lock_input_port(self):
        self.raw_lock_input_port(0x02)

    def raw_get_lock_input_port(self):
        self.raw_lock_input_port(0x01)

    def raw_get_mark_time(self):
        self._send_command(GET_MARK_TIME, 3)

    def raw_get_user_data(self):
        self._send_command(GET_USER_DATA)


class UsbConnection:
    chunk_size = 12*256
    ep_hodi = 0x01  # endpoint for the "dog," i.e. dongle.
    ep_hido = 0x81  # fortunately it turns out that we can ignore it completely.
    ep_homi = 0x02  # endpoint for host out, machine in. (query status, send ops)
    ep_himo = 0x88  # endpoint for host in, machine out. (receive status reports)

    def __init__(self, machine_index=0, debug=False):
        self.machine_index = machine_index
        self.device = None
        self.status = None
        self._debug = debug

    def open(self):
        devices=list(usb.core.find(find_all=True, idVendor=0x9588, idProduct=0x9899))
        if len(devices) == 0:
            raise BalorMachineException("No compatible engraver machine was found.")

        try:
            device = list(devices)[self.machine_index]
        except IndexError:
            # Can't find device
            raise BalorMachineException("Invalid machine index %d"%self.machine_index)

        # if the permissions are wrong, these will throw usb.core.USBError
        device.set_configuration()
        device.reset()
        self.device = device

    def close(self):
        pass

    def send_correction_entry(self, correction):
        """Send an individual correction table entry to the machine."""
        # This is really a command and should just be issued without reading.
        query = bytearray([0x10] + [0] * 11)
        query[2:2 + 5] = correction
        if self.device.write(self.ep_homi, query, 100) != 12:
            raise BalorCommunicationException("Failed to write correction entry")

    def send_command(self, code, *parameters, read=True):
        """Send a command to the machine and return the response.
           Updates the host condition register as a side effect."""
        query = bytearray([0] * 12)
        query[0] = code & 0x00FF
        query[1] = (code >> 8) & 0x00FF
        for n, parameter in enumerate(parameters):
            query[2 * n + 2] = parameter & 0x00FF
            query[2 * n + 3] = (parameter >> 8) & 0x00FF
        if self.device.write(self.ep_homi, query, 100) != 12:
            raise BalorCommunicationException("Failed to write command")
        if read:
            response = self.device.read(self.ep_himo, 8, 100)
            if len(response) != 8:
                raise BalorCommunicationException("Invalid response")
            self.status = response[6] | (response[7] << 8)
            return response[2] | (response[3] << 8), response[4] | (response[5] << 8)
        else:
            return 0

    def send_list_chunk(self, data):
        """Send a command list chunk to the machine."""
        if len(data) != self.chunk_size:
            raise BalorDataValidityException("Invalid chunk size %d" % len(data))

        sent = self.device.write(self.ep_homi, data, 100)
        if sent != len(data):
            raise BalorCommunicationException("Could not send list chunk")


class MockConnection:
    def __init__(self, machine_index=0, debug=False):
        self.machine_index = machine_index
        self._debug = debug
        self.device = True

    @property
    def status(self):
        import random
        return random.randint(0, 255)

    def open(self):
        self.device = True

    def close(self):
        pass

    def send_correction_entry(self, correction):
        """Send an individual correction table entry to the machine."""
        pass

    def send_command(self, code, *parameters):
        """Send a command to the machine and return the response.
           Updates the host condition register as a side effect."""
        import random
        return random.randint(0, 255)

    def send_list_chunk(self, data):
        """Send a command list chunk to the machine."""
        if len(data) != 0xC00:
            raise BalorDataValidityException("Invalid chunk size %d" % len(data))

