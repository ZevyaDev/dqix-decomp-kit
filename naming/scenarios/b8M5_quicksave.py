import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
GAME_STATE = 0x020F33D8
RECORDS = GAME_STATE + 0x7540
OUT = os.path.join(kitpaths.SP, "names", "b8", "M5")
LOG = OUT + "/b8M5_quicksave_mem.log"
SHOTS = OUT + "/quicksave_shots"


def times(F):
    out = []
    for offset in (0, 4, 0x68, 0x6C):
        hours, minutes, seconds = struct.unpack("<HBB", F.cons[0].read(RECORDS + offset, 4))
        out.append(f"+{offset:#x} {hours}:{minutes:02d}:{seconds:02d}")
    main_ts, alt_ts = struct.unpack("<QQ", F.cons[0].read(GAME_STATE + 0x3E8, 16))
    maps = F.cons[0].read(GAME_STATE + 0x64F4, 2)
    return " ".join(out) + f" mainTimestamp {main_ts:#x} altTimestamp {alt_ts:#x} maps+0 {maps[0]} maps+1 {maps[1]}"


def shot(F, name):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(SHOTS, f"f{F.cons[0].frames}_{name}.png"))


def press(F, key, wait, log=None, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)
    if log:
        log.write(f"f{F.cons[0].frames} {name or key} {times(F)}\n")


def play(F):
    os.makedirs(SHOTS, exist_ok=True)
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
        shot(F, "cursor")
        for n in range(6):
            press(F, "A", 150, log, f"a{n}")
        F.run(300)
        shot(F, "end")
        log.write(f"f{F.cons[0].frames} end {times(F)}\n")
