import numpy as np
from datetime import datetime
from svgelements import Path
from balor.sender import Sender


digits = [
    Path('M25.97 -7.15C26.13 -2.03 21.72 0.09 20.79 0.0C20.79 0.0 11.42 0.0 11.42 0.0C5.47 -0.22 5.0 -4.62 5.0 -4.62C5.0 -4.62 5.49 -27.98 5.49 -27.98C5.94 -32.96 13.25 -32.97 13.25 -32.97C13.25 -32.97 21.87 -32.92 21.87 -32.92C22.61 -33.01 26.14 -31.69 25.95 -28.39C25.95 -28.39 25.97 -7.15 25.97 -7.15'),
    Path('M7.56 -29.79C7.56 -29.79 16.98 -33.52 16.98 -33.52C16.98 -33.52 16.7 -0.13 16.7 -0.13M7.7 0.0C7.7 0.0 25.16 0.0 25.16 0.0'),
    Path('M4.47 -32.99C4.47 -32.99 17.79 -33.36 17.79 -33.36C17.74 -33.43 28.19 -33.55 25.51 -21.61C24.67 -17.89 9.94 -4.96 4.19 0.0C4.19 0.0 25.49 0.0 25.49 0.0'),
    Path('M6.15 -32.27C6.15 -32.27 15.76 -33.18 20.15 -32.65C22.68 -32.34 25.9 -31.39 26.05 -26.99C26.13 -24.53 25.38 -20.2 25.01 -19.33C23.39 -15.4 8.99 -16.66 8.85 -16.19C8.85 -16.19 22.23 -16.28 23.97 -14.55C26.77 -11.78 26.0 -3.73 23.89 -1.99C22.83 -1.11 18.36 -0.04 13.91 0.0C9.24 0.04 4.71 -0.36 4.71 -0.36'),
    Path('M18.54 -33.85C18.54 -33.85 3.94 -10.1 3.94 -10.1C3.94 -10.1 28.59 -10.29 28.59 -10.29M23.65 -23.36C23.65 -23.36 23.0 0.0 23.0 0.0'),
    Path('M24.11 -33.05C24.11 -33.05 7.41 -33.05 7.41 -33.05C7.41 -33.05 6.03 -16.17 6.03 -16.17C6.03 -16.17 8.76 -18.3 12.21 -18.93C14.45 -19.17 17.36 -19.12 19.72 -18.66C19.72 -18.66 24.82 -18.48 24.74 -12.35C24.74 -12.35 25.15 -7.44 24.34 -4.53C23.65 -1.99 22.45 -0.18 18.12 0.0C18.12 0.0 4.66 -0.8 4.66 -0.8'),
    Path('M25.87 -33.19C25.87 -33.19 17.83 -33.98 14.59 -33.63C11.97 -33.35 9.31 -33.1 8.04 -29.99C7.09 -27.67 3.07 -19.35 7.14 -2.41C7.45 -1.11 9.07 -0.05 11.65 0.0C13.32 0.03 17.57 0.15 20.45 0.0C23.03 -0.14 25.07 -1.01 25.38 -3.3C25.94 -8.6 27.87 -17.7 20.02 -18.22C17.61 -18.37 15.42 -18.13 12.89 -18.08C11.24 -18.05 5.51 -17.11 5.51 -17.11'),
    Path('M5.38 -33.18C5.38 -33.18 25.8 -33.18 25.8 -33.18C25.8 -33.18 12.4 0.0 12.4 0.0'),
    Path('M22.8 -18.53C23.58 -18.19 25.79 -20.92 25.46 -21.61C25.46 -21.61 25.18 -29.97 25.18 -29.97C24.62 -32.8 20.57 -33.3 20.57 -33.3C20.57 -33.3 11.9 -33.3 11.9 -33.3C11.9 -33.3 6.21 -33.49 5.93 -29.03C5.93 -29.03 6.11 -21.24 6.11 -21.24C6.11 -21.24 6.6 -18.09 8.99 -17.72C13.06 -17.66 19.52 -16.89 20.64 -16.52C22.23 -16.0 25.01 -15.93 25.33 -12.91C25.33 -12.91 25.29 -5.09 25.29 -5.09C25.29 -5.09 24.44 -0.31 21.04 0.0C21.04 0.0 11.05 0.0 11.05 0.0C11.05 0.0 6.08 -0.06 5.38 -4.34C5.38 -4.34 5.58 -11.81 5.58 -11.81C6.79 -18.24 15.08 -15.84 22.8 -18.53C22.8 -18.53 22.8 -18.53 22.8 -18.53'),
    Path('M25.71 -16.62C25.71 -16.62 10.38 -15.37 10.38 -15.37C6.35 -15.55 5.63 -19.64 5.63 -19.64C5.67 -23.28 5.26 -27.3 5.75 -30.57C6.91 -33.68 10.65 -33.5 10.65 -33.5C10.65 -33.5 18.76 -33.54 18.76 -33.54C19.56 -33.48 23.63 -32.53 24.39 -28.61C24.39 -28.61 26.31 -21.24 25.73 -15.55C24.6 -9.05 25.26 -0.52 18.42 0.0C16.46 0.17 7.48 -0.04 5.52 -0.62'),
    Path('M6.87 -23.86C6.87 -23.86 7.91 -23.86 7.91 -23.86C8.34 -23.86 8.67 -23.51 8.66 -23.08C8.66 -23.08 8.6 -21.71 8.6 -21.71C8.58 -21.28 8.22 -20.94 7.79 -20.94C7.79 -20.94 6.75 -20.94 6.75 -20.94C6.32 -20.94 5.99 -21.28 6.01 -21.71C6.01 -21.71 6.07 -23.08 6.07 -23.08C6.08 -23.51 6.44 -23.86 6.87 -23.86C6.87 -23.86 6.87 -23.86 6.87 -23.86M6.42 -2.92C6.42 -2.92 7.46 -2.92 7.46 -2.92C7.89 -2.92 8.23 -2.58 8.24 -2.15C8.24 -2.15 8.22 -0.77 8.22 -0.77C8.23 -0.35 7.88 0.0 7.45 0.0C7.45 0.0 6.41 0.0 6.41 0.0C5.98 0.0 5.64 -0.35 5.63 -0.77C5.63 -0.77 5.65 -2.15 5.65 -2.15C5.64 -2.58 5.99 -2.92 6.42 -2.92C6.42 -2.92 6.42 -2.92 6.42 -2.92'),
    ]

v = np.linspace(0, 1, 500)
points = {
    '0': digits[0].npoint(v),
    '1': digits[1].npoint(v),
    '2': digits[2].npoint(v),
    '3': digits[3].npoint(v),
    '4': digits[4].npoint(v),
    '5': digits[5].npoint(v),
    '6': digits[6].npoint(v),
    '7': digits[7].npoint(v),
    '8': digits[8].npoint(v),
    '9': digits[9].npoint(v),
    ':': digits[10].npoint(v),
}

for p in points:
    q = points[p]
    qm = min(q[:,0])
    qx = max(q[:,0])
    q[:, 0] -= (qm + qx) / 2.0
    qm = min(q[:, 1])
    qx = max(q[:, 1])
    q[:, 1] -= (qm + qx) / 2.0

# sender = Sender()
sender = Sender()
sender.open()

desired_width = 10000


def tick(cmds, loop_index):
    cmds.clear()
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    job.set_travel_speed(8000)
    total_width = 0
    for digit in current_time:
        pts = points[digit]
        total_width += max(pts[0,:]) - min(pts[0,:])
    scaling = desired_width / total_width
    start = 0x8000 - (desired_width / 2)
    for digit in current_time:
        pts = points[digit]
        typeset_digit = pts
        cmds.light(int(typeset_digit[0][0]*scaling + start), int(typeset_digit[0][1]*scaling + 0x8000), False)

        for pt in typeset_digit:
            cmds.light(int(pt[0]*scaling + start) , int(pt[1]*scaling + 0x8000), True)
        typeset_max_x = max(typeset_digit[:, 0]) - min(typeset_digit[:, 0])
        start += typeset_max_x * scaling
    cmds.light_off()
        # print(start)

    # from balor.MSBF import CommandList
    # c = CommandList()
    # for packet in cmds.packet_generator():
    #     c.add_packet(packet)
    # c.set_scale_x = 1.0
    # c.set_scale_y = 1.0
    # for operation in c:
    #     print(operation.text_debug(show_tracking=True))
    #
    # from PIL import Image, ImageDraw
    # im = Image.new('RGB', (0xFFF, 0xFFF), color=0)
    # cmds.plot(ImageDraw.Draw(im), 0xFFF, show_travels=True)
    # im.save('{time}.png'.format(time=current_time.replace(':', ';'), format='png'))


job = sender.job(tick=tick)
try:
    job.execute(1000)
except KeyboardInterrupt as e:
    print("Interrupted, quitting", e)
sender.close()

sender.close()


