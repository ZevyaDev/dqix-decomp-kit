import os
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
SHOTS = os.path.join(kitpaths.SP, "names", "b8", "M5", "accolade_shots")


def shot(F, name):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(SHOTS, f"f{F.cons[0].frames}_{name}.png"))


def press(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    os.makedirs(SHOTS, exist_ok=True)
    F.run(30)
    press(F, "X", 40)
    press(F, "Right", 15)
    press(F, "Down", 15)
    press(F, "A", 150, "records")
    for _ in range(4):
        press(F, "Down", 20)
    press(F, "A", 200, "accolades")
    press(F, "A", 150, "pick")
    press(F, "Right", 60, "right")
    press(F, "Down", 60, "down")
    press(F, "A", 150, "pick2")
    for n in range(5):
        press(F, "B", 60, f"b{n}")
