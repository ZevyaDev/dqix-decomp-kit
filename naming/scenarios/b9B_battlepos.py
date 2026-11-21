import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
COMBATANTS = (0, 1, 2, 3, 0xC0)
EVERY = 100
LOG = os.path.join(kitpaths.SP, "names", "b9", "B", "battlepos_mem.log")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def dump(F, out):
    frame = F.cons[0].frames
    for index in COMBATANTS:
        obj = u32(F, GAME_STATE + 8 + 4 * index)
        if not 0x02000000 <= obj < 0x02400000:
            continue
        pos = struct.unpack("<3i", F.cons[0].read(obj + 0x44, 12))
        state = u32(F, obj + 0x13C)
        if not 0x02000000 <= state < 0x02400000:
            out.write(f"f{frame} obj {index:#x} {obj:#x} state {state:#x} pos {pos}\n")
            continue
        rec = struct.unpack("<7i", F.cons[0].read(state, 28))
        out.write(f"f{frame} obj {index:#x} {obj:#x} state {state:#x} +4 {rec[1:4]} +0x10 {rec[4:7]} pos {pos}\n")


def play(F):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    out = open(LOG, "w")
    run = F.run
    mark = [0]

    def watched(frames):
        run(frames)
        if F.cons[0].frames - mark[0] >= EVERY:
            mark[0] = F.cons[0].frames
            dump(F, out)

    F.run = watched
    try:
        B.play(F)
    finally:
        F.run = run
        out.close()
