import os

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/field_battle.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "R1", "mapdiscard")


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
    F.run(2)
    press(F, "X", 60, "menu")
    press(F, "A", 90, "items")
    press(F, "Down", 20)
    press(F, "Down", 20, "maps_cursor")
    press(F, "A", 200, "maps")
    press(F, "A", 90, "map_actions")
    press(F, "Down", 20, "discard_cursor")
    press(F, "A", 150, "discard")
    press(F, "Down", 30, "no_cursor")
    press(F, "A", 120, "no")
    for i in range(5):
        press(F, "B", 40, f"back{i}")
