# balor-meerk40t

Provide a plugin to connect Balor with Meerk40t. Balor is a project which reverse engineers the LMC boards typically controlled by EzCad2 and colloquially referred to as EzCad2 boards.

For more information on Balor.
* See the MakerForum - https://forum.makerforums.info/t/about-the-balor-category/84495
* BryceSchroeder's website: https://www.bryce.pw/engraver.html
* Source Code: https://gitlab.com/bryce15/balor


# Install MeerK40t Development Branch

To run balor-meerk40t, you must install the meerk40t 0.8.0 branch (semi-stable) 

`pip install git+https://github.com/meerk40t.meerk40t.git@tatarize-services`

This should install the branch located at:
* https://github.com/meerk40t/meerk40t/tree/tatarize-services

# Install balor-meerk40t

You need to install this plugin:

`pip install git+https://github.com/tatarize.balor-meerk40t.git`

# Windows Driver
Windows, unlike Mac and Linux, will likely require something to allow the program to use pyusb compatible usb drivers. At least for now. The easiest method of doing this would be to follow the instruction for [Zadig.](https://zadig.akeo.ie/) The device uses idVendor=0x9588, idProduct=0x9899. 

# Add device.

In device manager, add a new device. Add in a "balor" device. You can delete the default M2-Nano device that meerk40t installs as a default.

# Console Commands

In addition to the regular interactions with the meerk40t gui (wxMeerk40t) you can issue console commands to control Balor. This is helpful if you would like to contribute to reverse engineering or to run some functionalities that are currently not accessible through the Meerk40t GUI.

Balor interacts with MeerK40t's console commands see: [MeerK40t Features: Console](https://www.youtube.com/watch?v=c_QBZlNvhVo)

* `mark`: Mark converts an `elements` type consisting of paths or shapes into a mark job. It takes extended parameters (see below). If you do not set an option the ones found in config for the Global Defaults will be used.
     * `travel_speed` (`t`)
     * `frequency` (`q`)
     * `power` (`p`),
     * `cut_speed` (`s`)
     * `laser_on_delay` (`n`)
     * `laser_off_delay` (`f`)
     * `polygon_delay` (`n`)
     * `quantization` (`Q`) 
* `light`: Light converts an `elements` type of paths or shapes into a light job. This type of job does not cut. It only moves performs movements using the red light. There are options to travel at slower speeds for the parts of the job that would have been cut.
     * `speed` (`s`): Run at a simulation speed equal to the cut speed.
     * `travel_speed` (`t`)
     * `simulation_speed` (`m`): Use this speed rather than the default cut speed
     * `quantization` (`Q`)
* `loop`: Put the job in the loop idle job event in spooler.
* `spool`: Put the job in the spooler.
* `stop`: Stop the currently running job in balor. This is linked to the No-Light Galvo button in the ribbonbar.
* `usb_connect`: Connect the device
* `usb_disconnect`: Disconnect the device
* `print`: Debug: print the packets to standard out.
* `png`:  Debug: save the image of the job simulation.
     * `filename`: default: "balor.png"
* `debug`: Debug: print the parsed information of the created packets of the job.
* `save`: Debug: save the raw binary data of the job.
     * `filename`: filename to save raw binary `balor.bin` is default. 
* `goto`: sends a goto position in galvos. `goto 0 0` will center the laser.
* `red`: turn red light on
     * `off`: turns the red light off rather than on
* `status`: sends a status check on the board and prints the bits of the reply.
* `lstatus`: sends a status check on the list status.
* `serial_number`: sends a check for board serial number.
* `calibrate`: set the balor calibration file, or unset it.
* `correction`: set the balor correction file. This is a cor file but the formatting isn't fully realized so it's just raw bytes.
* `position`: Debug: give the current position in galvos for the selected area.
* `lens`: Sets the lens/bed size.
     * `lens_size`: lens since in some accepted units eg. `110mm` 
* `box`: Converts the outline selection area into a `elements` type object. This is mostly so that that can be put into the loop. `box light loop` to create the looped selected box.
* `hull`: Displays the hull of the current selected element. This is like a rubberband outline. eg. `hull light loop`
* `ants`: Display marching ants animation of the current selected job.
* `hatch`: Fills the currently selected shape in with a hatch fill.
     * `distance` (`d`)
     * `angle` (`a`): angle can't be used due to an implementation bug.
     * `travel_speed` (`t`)
     * `frequency` (`q`)
     * `power` (`p`),
     * `cut_speed` (`s`)
     * `laser_on_delay` (`n`)
     * `laser_off_delay` (`f`)
     * `polygon_delay` (`n`)

# Notes:
* The galvo positions are the native resolution of the machine. They are from 0x0000 to 0xFFFF with 0x8000 being the center. The positions are absolute so the bed locations cannot exceed the 0xFFFF limit.
