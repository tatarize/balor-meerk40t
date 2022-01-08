#!/usr/bin/env python3
import balor
import sys, argparse
import time
parser = argparse.ArgumentParser(description='''
Interface with a Beijing JCZ Technology laser engraver.
This program uploads a file in the machine-specific binary format of
the particular laser engraving/marking/cutting machine and executes
it on the hardware. The machine-specific binary file will have been
prepared previously with accompanying converters.''',
epilog='''
NOTE: This software is EXPERIMENTAL and has only been tested with a
single machine. There are many different laser engraving machines 
and the fact that they look the same, or even have the same markings,
is not proof that they are really the same. IT COULD DAMAGE YOUR
MACHINE. Also, there is almost no error checking and if you feed this 
program garbage data there is no telling what will happen when it is
sent to the engraver. There is NO WARRANTY. And what happens when you
screw up and upload a data file made for lighting as a mark operation, 
or the other way around? I don't know, but IT MIGHT BE BAD! This is
without getting into the fact that the core purpose of this program is
causing a machine to emit pulses of light that can turn
metal into plasma and all the potential hazards associated with that,
which which you, as the owner of such a machine, should already be
very familiar.''')

parser.add_argument('-m', '--machine', help="specify which machine interface to use. Valid machines: "+', '.join([x.__name__ for x in balor.all_known_machines]), default="BJJCZ_LMCV4_FIBER_M")
parser.add_argument('-i', '--index', help="specify which machine to use, if there is more than one", type=int, default=0)
parser.add_argument('-f', '--file', help="filename to load, in the machine-specific binary format (default stdin)", default=None)
parser.add_argument('-o', '--operation', help="choose operational mode", default="light", choices=["mark", "light"])
parser.add_argument('-r', '--repeat', type=int, help="how many times to repeat the pattern (default no repeats if marking, 100 if lighting)", default=None)
parser.add_argument('-v', '--verbose', type=int, help="verbosity level", default=0)

args = parser.parse_args()

if args.file is None:
    data = sys.stdin.buffer.read()
else:
    data = open(args.file,'rb').read()

Machine_class = None
for Candidate in balor.all_known_machines:
    if Candidate.__name__ == args.machine:
        Machine_class = Candidate
        break

if Machine_class is None:
    print ("I don't know about a machine called `%s'."%args.machine, file=sys.stderr)
    sys.exit(-1)

machine = Machine_class(args.index)
machine.set_verbosity(args.verbose)
if len(data)%machine.packet_size:
    print("The input file is not an even multiple of %d bytes long."%machine.packet_size, file=sys.stderr)
    sys.exit(-2)


class InputRepeater:
    def __init__(self, data, packet_size=machine.packet_size):
        self.data = data
        self.i = 0
        self.packet_size = packet_size
        assert not len(self.data) % packet_size
    def generate(self, old_data):
        data = self.data[self.i:self.i+self.packet_size]
        assert len(data) == len(old_data)
        self.i += self.packet_size
        if self.i == len(self.data): self.i = 0
        return data


if args.operation == 'light':
    repeats = args.repeat if args.repeat else 100
    input_repeating_generator = InputRepeater(data)
    machine.light(repeats, substitution_generator=input_repeating_generator.generate)

elif args.operation == 'mark':
    #time.sleep(0.1) # 
    machine.mark(data) #print ("Marking not implemented yet.", file=sys.stderr)

machine.close()
