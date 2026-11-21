import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("N5b_dqvc", os.path.join(HERE, "N5b_dqvc.py"))
BASE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BASE)

START = BASE.START
GAME_STATE = 0x020F33D8
MELANIE, NATALIA, GARREK = 1, 2, 3
LOG = os.path.join(kitpaths.SP, "names", "b10", "M7", "dqvc_hp")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def member(F, index):
    return u32(F, GAME_STATE + 8 + 4 * index)


def status(F, index):
    return u32(F, member(F, index) + 0x130)


def hp(F, index):
    return struct.unpack("<H", F.cons[0].read(status(F, index) + 4, 2))[0]


def max_hp(F, index):
    return struct.unpack("<H", F.cons[0].read(u32(F, member(F, index) + 0x134) + 0x30, 2))[0]


def play(F):
    run = 1
    while os.path.exists(f"{LOG}.{run}.log"):
        run += 1
    with open(f"{LOG}.{run}.log", "w", encoding="utf-8", newline="\n") as log:
        F.run(10)
        for index in range(4):
            log.write(f"f{F.cons[0].frames} before: member {index} hp {hp(F, index)} max {max_hp(F, index)}\n")
        targets = {MELANIE: max_hp(F, MELANIE) // 5, NATALIA: 1, GARREK: 0}
        for index, value in targets.items():
            F.cons[0].write(status(F, index) + 4, struct.pack("<H", value))
        s = status(F, GARREK)
        F.cons[0].write(s, struct.pack("<I", u32(F, s) | 1))
        for index in range(4):
            log.write(f"f{F.cons[0].frames} written: member {index} hp {hp(F, index)} max {max_hp(F, index)}\n")
        BASE.play(F)
        for index in range(4):
            log.write(f"f{F.cons[0].frames} end: member {index} hp {hp(F, index)} max {max_hp(F, index)}\n")
