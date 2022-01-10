import usb.core
import usb.util
from usb.backend.libusb1 import LIBUSB_ERROR_ACCESS, LIBUSB_ERROR_NOT_FOUND

packet_size = 3072  # 0xC00, 12 x 256
VID = 0x9588
PID = 0x9899

ep_hodi = 0x01  # endpoint for the "dog," i.e. dongle.
ep_hido = 0x81  # fortunately it turns out that we can ignore it completely.
ep_homi = 0x02  # endpoint for host out, machine in. (query status, send ops)
ep_himo = 0x88  # endpoint for host in, machine out. (receive status reports)


class GalvoUsb:
    """
    GalvoUSB performs all the USB interactions and functions with the USB device.

    This class should not have any information about what it's sending other than commands like write_command being
    12 bytes long and write_block being 0xC00.

    It's apparently fickle and trying to provide more robust support lead to failures to connect.
    """
    def __init__(self, channel=None):
        self.device = None
        self.manufacturer = None
        self.product = None
        self.channel = channel
        self.backend_error_code = None

    def write_command(self, query):
        device = self.device
        length = device.write(ep_homi, query, 100)
        #print ("usb-sending query", ' '.join(['%02X'%x for x in query]), length ==len(query))
        if length != len(query):
            pass  # Perform error check.

    def read_reply(self):
        device = self.device
        reply = device.read(ep_himo, 8, 100)
        #print ("usb-got reply", ' '.join(['%02X'%x for x in reply]))
        return reply

    def write_block(self, packet):
        device = self.device
        #print ('usb-attempting block write')
        length = device.write(ep_homi, packet, 100)
        ##print ('usb-writing block', len(packet), length)
        if length != len(packet):
            pass  # Perform error Check
        return

    def canned_read(self, *args):
        device = self.device
        return device.read(*args)

    def canned_write(self, *args):
        device = self.device
        device.write(*args)

    def connect(self):
        """
        This is exactly the original code sequence because it would fail to connect sometimes. Fragile.
        :return:
        """
        if self.channel:
            self.channel("Connecting...")
        devices=usb.core.find(find_all=True, idVendor=0x9588, idProduct=0x9899)
        device = list(devices)[0]
        self.manufacturer = usb.util.get_string(device, device.iManufacturer)
        self.product = usb.util.get_string(device, device.iProduct)
        device.set_configuration()  # It only has one.
        device.reset()
        self.device = device
        if self.channel:
            self.channel("Connected...")
        return device

    def disconnect(self):
        device = self.device
        if self.channel:
            self.channel("Attempting disconnection from USB.")
        if device is not None:
            try:
                # self.disconnect_detach(device, interface)
                # self.unclaim_interface(device, interface)
                self.disconnect_dispose(device)
                self.disconnect_reset(device)
                if self.channel:
                    self.channel("USB Disconnection Successful.")
            except ConnectionError:
                pass

    ##################
    # USB LOW LEVEL
    ##################

    def find_device(self, index=0):
        if self.channel:
            self.channel("Finding devices.")
        try:
            devices = list(usb.core.find(idVendor=VID, idProduct=PID, find_all=True))
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code
            if self.channel:
                self.channel(str(e))
            raise ConnectionRefusedError
        if len(devices) == 0:
            if self.channel:
                self.channel("Devices Not Found.")
            raise ConnectionRefusedError
        for d in devices:
            if self.channel:
                self.channel("Device detected:")
                string = str(d)
                string = string.replace("\n", "\n\t")
                self.channel(string)
        try:
            device = devices[index]
        except IndexError:
            if self.backend_error_code == LIBUSB_ERROR_ACCESS:
                self.channel("Your OS does not give you permissions to access USB.")
                raise PermissionError
            elif self.backend_error_code == LIBUSB_ERROR_NOT_FOUND:
                if self.channel:
                    self.channel(
                        "Devices were found. But something else was connected to them."
                    )
            else:
                if self.channel:
                    self.channel(
                        "Devices were found but they were rejected for unknown reasons"
                    )
            raise ConnectionRefusedError
        return device

    def detach_kernel(self, device, interface):
        try:
            if device.is_kernel_driver_active(interface.bInterfaceNumber):
                try:
                    if self.channel:
                        self.channel("Attempting to detach kernel.")
                    device.detach_kernel_driver(interface.bInterfaceNumber)
                    if self.channel:
                        self.channel("Kernel detach: Success.")
                except usb.core.USBError as e:
                    self.backend_error_code = e.backend_error_code
                    if self.channel:
                        self.channel(str(e))
                        self.channel("Kernel detach: Failed.")
                    raise ConnectionRefusedError
        except NotImplementedError:
            if self.channel:
                self.channel("Kernel detach: Not Implemented.")
            # Driver does not permit kernel detaching.
            # Non-fatal error.

    def get_active_config(self, device):
        if self.channel:
            self.channel("Getting Active Config")
        try:
            interface = device.get_active_configuration()[(0, 0)]
            if self.channel:
                self.channel("Active Config: Success.")
            return interface
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code
            if self.channel:
                self.channel(str(e))
                self.channel("Active Config: Failed.")
            raise ConnectionRefusedError

    def set_config(self, device):
        if self.channel:
            self.channel("Config Set")
        try:
            device.set_configuration()
            if self.channel:
                self.channel("Config Set: Success")
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code
            if self.channel:
                self.channel(str(e))
                self.channel(
                    "Config Set: Fail\n(Hint: may recover if you change where the USB is plugged in.)"
                )

    def claim_interface(self, device, interface):
        try:
            if self.channel:
                self.channel("Attempting to claim interface.")
            usb.util.claim_interface(device, interface)
            if self.channel:
                self.channel("Interface claim: Success")
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code
            if self.channel:
                self.channel(str(e))
                self.channel("Interface claim: Failed. (Interface is in use.)")
            raise ConnectionRefusedError
            # Already in use. This is critical.

    def disconnect_detach(self, device, interface):
        try:
            if self.channel:
                self.channel("Attempting kernel attach")
            device.attach_kernel_driver(interface.bInterfaceNumber)
            if self.channel:
                self.channel("Kernel attach: Success.")
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code
            if self.channel:
                self.channel(str(e))
                self.channel("Kernel attach: Fail.")
            # Continue and hope it is non-critical.
        except NotImplementedError:
            if self.channel:
                self.channel("Kernel attach: Fail.")

    def unclaim_interface(self, device, interface):
        try:
            if self.channel:
                self.channel("Attempting to release interface.")
            usb.util.release_interface(device, interface)
            if self.channel:
                self.channel("Interface released.")
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code
            if self.channel:
                self.channel(str(e))
                self.channel("Interface did not exist.")

    def disconnect_dispose(self, device):
        try:
            if self.channel:
                self.channel("Attempting to dispose resources.")
            usb.util.dispose_resources(device)
            if self.channel:
                self.channel("Dispose Resources: Success")
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code
            if self.channel:
                self.channel(str(e))
                self.channel("Dispose Resources: Fail")

    def disconnect_reset(self, device):
        try:
            if self.channel:
                self.channel("Attempting USB reset.")
            device.reset()
            if self.channel:
                self.channel("USB connection reset.")
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code
            if self.channel:
                self.channel(str(e))
                self.channel("USB connection did not exist.")
