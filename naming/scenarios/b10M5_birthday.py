import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "M5", "birthday")


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


DATE_SLOT = 0x027E3588
LOG = os.path.join(OUT, "date_slot.log")


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)
        words = struct.unpack("<4i", F.cons[0].read(DATE_SLOT, 16))
        with open(LOG, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"f{F.cons[0].frames} {name} {DATE_SLOT:#x}: {words}\n")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    open(LOG, "w").close()
    F.run(30)
    tap(F, "X", 40)
    tap(F, "Right", 15)
    tap(F, "Down", 15)
    tap(F, "Down", 15)
    tap(F, "A", 90)
    for _ in range(4):
        tap(F, "Down", 20)
    tap(F, "A", 150, "profile")
    tap(F, "Down", 30)
    tap(F, "A", 90, "birthday")
    tap(F, "Up", 40, "day_up")
    tap(F, "Right", 30, "month_cursor")
    tap(F, "Up", 40, "month_up")
    tap(F, "Right", 30, "year_cursor")
    for n in range(3):
        tap(F, "Up", 40, f"year_up{n}")
    for n in range(3):
        tap(F, "Down", 40, f"year_down{n}")
    tap(F, "B", 60, "profile_back")
    for n in range(3):
        tap(F, "B", 60, f"exit{n}")
