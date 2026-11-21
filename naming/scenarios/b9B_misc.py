import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b9", "B", "shots")


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


def touch(F, x, y, wait, name=None):
    F.cons[0].touch(x, y)
    F.run(6)
    F.cons[0].touch()
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    F.run(30)
    tap(F, "X", 60)
    tap(F, "Right", 20)
    tap(F, "Down", 20)
    tap(F, "Down", 20)
    tap(F, "A", 90, "misc_open")
    tap(F, "Down", 20)
    tap(F, "A", 150, "tactics_open")
    tap(F, "Down", 30, "tactics_down1")
    tap(F, "Down", 30, "tactics_down2")
    tap(F, "B", 90, "tactics_back")
    for _ in range(4):
        tap(F, "Down", 20)
    tap(F, "A", 150, "volume_open")
    touch(F, 166, 141, 60, "volume_touch1")
    touch(F, 134, 155, 60, "volume_touch2")
    for _ in range(4):
        tap(F, "B", 60)
    shot(F, "closed")
