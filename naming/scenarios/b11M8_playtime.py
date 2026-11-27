import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
GAME_STATE = 0x020F33D8
RECORDS = GAME_STATE + 0x7540
OUT = os.path.join(kitpaths.SP, "names", "b11", "M8")
LOG = os.path.join(OUT, "playtime_mem.log")


def times(F):
    out = []
    for offset in (0, 4):
        hours, minutes, seconds = struct.unpack("<HBB", F.cons[0].read(RECORDS + offset, 4))
        out.append(f"+{offset:#x} {hours}:{minutes:02d}:{seconds:02d}")
    return " ".join(out)


def press(F, key, wait, log=None, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if log:
        log.write(f"f{F.cons[0].frames} {name or key} {times(F)}\n")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as log:
        F.run(30)
        log.write(f"f{F.cons[0].frames} start {times(F)}\n")
        press(F, "X", 40)
        press(F, "Right", 15)
        press(F, "Down", 15)
        press(F, "Down", 15)
        press(F, "A", 90, log, "misc")
        for _ in range(6):
            press(F, "Down", 20)
        for n in range(6):
            press(F, "A", 150, log, f"a{n}")
        F.run(300)
        log.write(f"f{F.cons[0].frames} end {times(F)}\n")
