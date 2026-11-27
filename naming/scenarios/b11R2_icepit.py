import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/grotto.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "R2", "icepit")
ZONE = 0x020FB3F0
REGULAR = (40001, 41100)


def zone(F):
    return struct.unpack("<H", F.cons[0].read(ZONE, 2))[0]


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"f{F.cons[0].frames:05d}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "icepit.log"), "w")
    F.run(30)
    tap(F, "X", 60)
    tap(F, "A", 120)
    tap(F, "Down", 30)
    tap(F, "Down", 30)
    tap(F, "A", 200, "maps")
    for n in range(3):
        tap(F, "Right", 60)
    for n in range(5):
        tap(F, "Down", 20)
    shot(F, "icepit_row")
    tap(F, "A", 90, "map_choice")
    tap(F, "A", 120, "sets_out")
    for n in range(6):
        tap(F, "B", 60, f"close{n}")
    log.write(f"f{F.cons[0].frames} zone {zone(F)} pos {F.pos(0)}\n")
    F.run(60)
    F.hold(0, ["Up"], 40)
    F.hold(0, ["A"], 4)
    for _ in range(60):
        if REGULAR[0] <= zone(F) <= REGULAR[1]:
            break
        F.run(10)
    F.run(200)
    shot(F, "inside")
    log.write(f"f{F.cons[0].frames} zone {zone(F)} pos {F.pos(0)}\n")
    for key, frames in (("Down", 60), ("Left", 90), ("Down", 90), ("Right", 120), ("Down", 90), ("Left", 120)):
        F.hold(0, [key], frames)
        log.write(f"f{F.cons[0].frames} {key} {frames} zone {zone(F)} pos {F.pos(0)}\n")
        shot(F, f"walk_{key}")
    log.close()
