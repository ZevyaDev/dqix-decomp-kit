import importlib.util
import os
import struct
import kitpaths

_spec = importlib.util.spec_from_file_location("C5_krakpot", os.path.join(os.path.dirname(__file__), "C5_krakpot.py"))
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)

START = K.START
BAG = 0x020F5DDC
ITEM = 0x55F0
LOG = os.path.join(kitpaths.SP, "names", "b8", "M5", "b8M5_krakpot_mem.log")


def bag_line(F):
    ids_ptr, counts_ptr, slots = struct.unpack("<IIh", F.cons[0].read(BAG, 10))
    ids = struct.unpack(f"<{slots}h", F.cons[0].read(ids_ptr, 2 * slots))
    counts = struct.unpack(f"<{slots}b", F.cons[0].read(counts_ptr, slots))
    filled = sum(1 for c in counts if c != 0)
    held = [(i, c) for i, c in zip(ids, counts) if i == ITEM]
    return f"slots {slots} filled {filled} item {ITEM:#x} {held}"


def play(F):
    with open(LOG, "w", encoding="utf-8") as log:
        log.write(f"f{F.cons[0].frames} start {bag_line(F)}\n")
        K.play(F)
        log.write(f"f{F.cons[0].frames} end {bag_line(F)}\n")
