import os

import kitpaths

START = {"save": "states/guest.sav", "state": "states/inn.1.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "M1", "krakpot_ayla")


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"f{F.cons[0].frames:05d}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def press(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    F.run(30)
    shot(F, "start")
    F.move_to(0, tz=9.12)
    F.move_to(0, tx=1.74)
    F.align(0, tx=1.74)
    F.move_to(0, tz=7.92)
    F.hold(0, ["Up"], 2)
    F.run(4)
    shot(F, "at_pot")
    for n in range(5):
        press(F, "A", 90, f"talk{n}")
    for _ in range(4):
        press(F, "Down", 20)
    press(F, "A", 90, "pick0")
    press(F, "A", 90, "pick1")
    press(F, "A", 90, "pick2")
    F.run(240)
    shot(F, "list")
    for n in range(6):
        press(F, "A", 90, f"a{n}")
    for _ in range(10):
        press(F, "B", 60)
    F.run(120)
    shot(F, "end")
