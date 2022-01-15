#!/usr/bin/env python3
import balor
import sys, argparse, os, io, pickle

parser = argparse.ArgumentParser(description='''
Debugging tool for Beijing JCZ Technology laser engraver command streams.
This program can extract bytestreams from pcap files or take one or more
raw binary files containing the bytestream, and output text describing the
contents of the file, or plot a raster image depicting the intended output
approximately (no lens effects or nonlinearity is simulated.)''',
epilog='''
NOTE: This software is EXPERIMENTAL and has only been tested with a
single machine. There are many different laser engraving machines 
and the fact that they look the same, or even have the same markings,
is not proof that they are really the same.''')
parser.add_argument('-m', '--machine', 
        help=("specify which machine protocol to use. Valid machines: "
            +', '.join([x.__name__ for x in balor.all_known_machines])), 
        default="BJJCZ_LMCV4_FIBER_M")

parser.add_argument('-f', '--file', 
    help="file to load, in the machine-specific binary format (default stdin)",
    default=None)

parser.add_argument('-o', '--output', 
    help="Specify the output file. (default stdout)",
    default=None)

parser.add_argument('-t', '--type',
    help="Specify the output type (txt, pickle, png). (default txt)",
    default="txt")

parser.add_argument('-s', '--size',
        help="Set the size of the cutting field, in mm",
        default=None, type=float)

parser.add_argument('-r', '--resolution',
        help="For image output, how many pixels on a side?",
        default=1024, type=int)

args = parser.parse_args()

#################
# This is probably specific to USB Pcap on Windows
def parse_pcap_packet(packet):
    data = packet[27:]
    endpoint = packet[21]&0x7F
    direction = packet[21]&0xF0
    return endpoint, direction, data

#################

if args.file is None:
    input_file = io.BytesIO(sys.stdin.buffer.read())
    magic_number = input_file.read(1)
    input_file.seek(0)
    input_format = 'pcap' if magic_number[0] == 0xD4 else 'raw'
else:
    input_file = open(args.file,'rb')
    input_format = os.path.splitext(args.file)[-1]


if args.output is None:
    output_format = args.type
    if output_format == 'txt':
        output_file = sys.stdout
    else:
        output_file = sys.stdout.buffer
else:
    output_file = open(args.output, 'wb')
    output_format = os.path.splitext(args.output)[-1][1:]

if not input_format: input_format = 'raw'


input_data = []
if input_format == 'pcap':
    import dpkt
    for ts, buf in dpkt.pcap.Reader(input_file):
        endpoint, direction, data = parse_pcap_packet(buf)
        if not (endpoint == 2 and direction == 0 and len(data) == 3072): 
            continue
        input_data.append((ts, endpoint, direction, data))
else:
    while True:
        packet = input_file.read(3072)
        if not packet: break
        if len(packet) < 3072:
            print("WARNING: excess bytes < 1 whole packet.",
                    file=sys.stderr)
            #sys.exit(-1)
            packet += b'\0'*(3072-len(packet))
            print("\t(The errant packet has been zero-padded to size.)",
                    file=sys.stderr)
        input_data.append((0.0, 2, 0, packet))

import balor.MSBF
job = balor.MSBF.JobFactory(args.machine)

if args.size:
    job.set_scale(float(args.size)/0x10000,float(args.size)/0x10000,
            unit='mm')
    if output_format == 'txt':
        print ("SCALE:", job.get_scale(), file=output_file)


for n, (timestamp, endpoint, _, packet) in enumerate(input_data):
    if output_format == 'txt':
        print ("PACKET: %d at time %.2f, sent to endpoint %d: %d bytes"%(
            n, timestamp,  endpoint, len(packet)), 
            file=output_file)
    job.add_packet(packet, tracking="%4d"%(n))
if output_format == 'png':
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (args.resolution,args.resolution), color=0)
    #print ("Graphical output not implemented yet, sorry.", file=sys.stderr)
    job.plot(ImageDraw.Draw(im), args.resolution)
    im.save(output_file,format='png')
    sys.exit(-2)
elif output_format == 'pickle':
    pickle.dump(job, output_file)
else: # txt
    for operation in job:
        print (operation.text_debug(show_tracking=True), file=output_file)


    




