import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
GAME_STATE = 0x020F33D8
BITS = GAME_STATE + 0x104 + 0x7400
OUT = os.path.join(kitpaths.SP, "names", "b10", "M6", "accolades")


def shot(F, name):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{F.cons[0].frames}_{name}.png"))


def press(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def dump(F, log, tag):
    words = struct.unpack("<15I", F.cons[0].read(BITS, 0x3C))
    ids = [i for i in range(0x1E0) if words[i // 32] & (1 << (i % 32))]
    log.write(f"f{F.cons[0].frames} {tag}: {BITS:#x} words {' '.join(f'{w:08x}' for w in words)}\n")
    log.write(f"  {len(ids)} bits set; first ids {ids[:16]}; last ids {ids[-8:]}\n")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "bits.log"), "w", encoding="utf-8") as log:
        dump(F, log, "start")
        F.run(30)
        press(F, "X", 40)
        press(F, "Right", 15)
        press(F, "Down", 15)
        press(F, "A", 150, "records")
        for _ in range(4):
            press(F, "Down", 20)
        press(F, "A", 200, "accolades")
        dump(F, log, "list open")
        press(F, "Left", 60, "left")
        press(F, "Left", 60, "left2")
        press(F, "R", 60, "r")
        press(F, "L", 60, "l")
        press(F, "L", 60, "l2")
        for n in range(4):
            press(F, "B", 60)
        dump(F, log, "end")
