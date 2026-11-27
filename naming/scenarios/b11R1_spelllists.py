import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "R1", "spelllists")


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames}_{name}.png"))


def press(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    F.run(30)
    press(F, "X", 60)
    press(F, "Right", 20)
    press(F, "A", 90)
    for member in range(4):
        press(F, "A", 120, f"member{member}_page1")
        press(F, "Right", 40, f"member{member}_page2")
        press(F, "B", 40)
        press(F, "Down", 20)
