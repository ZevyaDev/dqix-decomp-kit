import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b7", "M5", "shots")


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"skills2_f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    F.run(30)
    tap(F, "X", 60, "menu")
    tap(F, "Right", 20, "right")
    tap(F, "A", 90, "spells_open")
    tap(F, "A", 120, "spells_member")
    tap(F, "A", 120, "spells_pick")
    tap(F, "Right", 60, "spells_right")
    tap(F, "R", 60, "spells_r")
    for i in range(4):
        tap(F, "B", 40, f"spells_back{i}")
    tap(F, "X", 60, "menu2")
    tap(F, "Down", 20)
    tap(F, "Down", 20, "attr_cursor")
    tap(F, "A", 90, "attr_open")
    tap(F, "A", 120, "attr_member")
    for i in range(4):
        tap(F, "Right", 60, f"attr_right{i}")
    for i in range(3):
        tap(F, "R", 60, f"attr_r{i}")
