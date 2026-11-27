import os

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/grotto.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "R2", "mappages")


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
    F.run(30)
    tap(F, "X", 60, "menu")
    tap(F, "A", 120, "items")
    tap(F, "Down", 30, "down0")
    tap(F, "Down", 30, "down1")
    tap(F, "A", 200, "maps")
    for n in range(12):
        tap(F, "Right", 60, f"page{n + 2:02d}")
