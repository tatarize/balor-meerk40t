import wx

from meerk40t.gui.icons import icons8_connected_50, icons8_disconnected_50
from meerk40t.gui.mwindow import MWindow
from meerk40t.kernel import signal_listener

_ = wx.GetTranslation


class BalorController(MWindow):
    def __init__(self, *args, **kwds):
        super().__init__(499, 170, *args, **kwds)
        self.button_device_connect = wx.Button(self, wx.ID_ANY, _("Connection"))
        self.service = self.context.device
        self.text_status = wx.TextCtrl(self, wx.ID_ANY, "")
        self.gauge_buffer = wx.Gauge(self, wx.ID_ANY, 10)
        self.text_buffer_length = wx.TextCtrl(self, wx.ID_ANY, "")
        self.text_buffer_max = wx.TextCtrl(self, wx.ID_ANY, "")

        self.__set_properties()
        self.__do_layout()

        self.Bind(
            wx.EVT_BUTTON, self.on_button_start_connection, self.button_device_connect
        )
        # end wxGlade
        self.max = 0
        self.state = None

    def __set_properties(self):
        # begin wxGlade: Controller.__set_properties
        self.SetTitle(_("Balor-Controller"))
        _icon = wx.NullIcon
        _icon.CopyFromBitmap(icons8_connected_50.GetBitmap())
        self.SetIcon(_icon)
        self.button_device_connect.SetBackgroundColour(wx.Colour(102, 255, 102))
        self.button_device_connect.SetForegroundColour(wx.BLACK)
        self.button_device_connect.SetFont(
            wx.Font(
                12,
                wx.FONTFAMILY_DEFAULT,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
                0,
                "Segoe UI",
            )
        )
        self.button_device_connect.SetToolTip(
            _("Force connection/disconnection from the device.")
        )
        self.button_device_connect.SetBitmap(
            icons8_disconnected_50.GetBitmap(use_theme=False)
        )
        self.text_status.SetToolTip(_("Connection status"))
        self.text_buffer_length.SetMinSize((165, 23))
        self.text_buffer_length.SetToolTip(
            _("Current number of bytes in the write buffer.")
        )
        self.text_buffer_max.SetMinSize((165, 23))
        self.text_buffer_max.SetToolTip(
            _("Current number of bytes in the write buffer.")
        )
        # end wxGlade

    def __do_layout(self):
        # begin wxGlade: Controller.__do_layout
        sizer_1 = wx.BoxSizer(wx.VERTICAL)
        write_buffer = wx.BoxSizer(wx.HORIZONTAL)
        connection_controller = wx.BoxSizer(wx.VERTICAL)
        sizer_15 = wx.BoxSizer(wx.HORIZONTAL)
        connection_controller.Add(self.button_device_connect, 0, wx.EXPAND, 0)
        label_7 = wx.StaticText(self, wx.ID_ANY, _("Status"))
        sizer_15.Add(label_7, 1, 0, 0)
        sizer_15.Add(self.text_status, 11, 0, 0)
        connection_controller.Add(sizer_15, 0, 0, 0)
        sizer_1.Add(connection_controller, 0, wx.EXPAND, 0)
        static_line_2 = wx.StaticLine(self, wx.ID_ANY)
        static_line_2.SetMinSize((483, 5))
        sizer_1.Add(static_line_2, 0, wx.EXPAND, 0)
        sizer_1.Add(self.gauge_buffer, 0, wx.EXPAND, 0)
        label_12 = wx.StaticText(self, wx.ID_ANY, _("Buffer Size: "))
        write_buffer.Add(label_12, 0, 0, 0)
        write_buffer.Add(self.text_buffer_length, 10, 0, 0)
        write_buffer.Add((20, 20), 0, 0, 0)
        label_13 = wx.StaticText(self, wx.ID_ANY, _("Max Buffer Size:"))
        write_buffer.Add(label_13, 0, 0, 0)
        write_buffer.Add(self.text_buffer_max, 10, 0, 0)
        sizer_1.Add(write_buffer, 0, 0, 0)
        self.SetSizer(sizer_1)
        self.Layout()
        # end wxGlade

    def window_open(self):
        self.text_buffer_max.SetValue("0")
        self.text_buffer_length.SetValue("0")
        self.on_network_update()

    @signal_listener("status_update")
    def on_network_update(self, origin=None, status=None, *args):
        if status is not None:
            self.text_status.SetValue(str(status))

    @signal_listener("pipe;usb_status")
    def on_usb_update(self,origin=None, *args):
        try:
            connected = self.context.device.controller.connection.connected
        except AttributeError:
            return
        if connected:
            self.button_device_connect.SetBackgroundColour("#00ff00")
            self.button_device_connect.SetLabel(_("Disconnect"))
            self.button_device_connect.SetBitmap(
                icons8_connected_50.GetBitmap(use_theme=False)
            )
            self.button_device_connect.Enable()
        else:
            self.button_device_connect.SetBackgroundColour("#dfdf00")
            origin, usb_status = self.context.last_signal("pipe;usb_status")
            self.button_device_connect.SetLabel(_("Connect Failed"))
            self.button_device_connect.SetBitmap(
                icons8_disconnected_50.GetBitmap(use_theme=False)
            )
            self.button_device_connect.Enable()

    def on_button_start_connection(self, event):  # wxGlade: Controller.<event_handler>
        try:
            connected = self.context.device.controller.connection.connected
        except AttributeError:
            return
        if connected:
            self.context("usb_disconnect\n")
        else:
            self.context("usb_connect\n")
