import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b8", "O1", "shots")


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"misc_f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    F.run(30)
    tap(F, "X", 60, "menu")
    tap(F, "Right", 20)
    tap(F, "Down", 20)
    tap(F, "Down", 20, "misc_cursor")
    tap(F, "A", 90, "misc_open")
    tap(F, "Down", 20)
    tap(F, "Down", 20, "skill_cursor")
    tap(F, "A", 150, "skill_open")
    tap(F, "A", 200, "skill_member")
    F.hold(0, ["Right"], 1000)
    F.run(30)
    shot(F, "hold_right")
    for _ in range(5):
        tap(F, "Down", 20)
    shot(F, "confirm_cursor")
    for i in range(30):
        tap(F, "A", 150, f"after_a{i}")
