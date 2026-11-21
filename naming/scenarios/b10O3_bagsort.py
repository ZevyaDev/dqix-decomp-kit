import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "O3", "shots")
GAME_STATE = 0x020F33D8


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"bag_f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    F.run(30)
    tap(F, "X", 60, "menu")
    tap(F, "A", 120, "items")
    tap(F, "A", 180, "everyday")
    for n in range(5):
        tap(F, "Down", 30, f"down{n}")
    for n in range(4):
        tap(F, "Select", 120, f"sort{n + 1}")
    tap(F, "A", 120, "bag_open")
    for n in range(4):
        tap(F, "B", 40, f"b{n}")
