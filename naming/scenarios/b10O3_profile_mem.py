import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "O3", "shots")
PROFILE_MENU = 0x02388BAC
WINDOW_MANAGER = PROFILE_MENU + 0xAC


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"profmem_f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def dump(F, tag):
    con = F.cons[0]
    mode = con.read(PROFILE_MENU + 0x1371, 1)[0]
    touch = struct.unpack("<5i", con.read(WINDOW_MANAGER + 0x4, 0x14))
    key = struct.unpack("<5i", con.read(WINDOW_MANAGER + 0x54, 0x14))
    enabled = tuple(con.read(WINDOW_MANAGER + 0x94, 2))
    print(f"{tag}: f{con.frames} mode(+0x1371) {mode} touch cursor count/pages/columns/rows/rowMajor {touch} "
          f"key cursor {key} touch/key enabled(+0x94/+0x95) {enabled}")


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)
        dump(F, name)


def play(F):
    F.run(30)
    tap(F, "X", 40)
    tap(F, "Right", 15)
    tap(F, "Down", 15)
    tap(F, "Down", 15)
    tap(F, "A", 90, "misc")
    for _ in range(4):
        tap(F, "Down", 20)
    tap(F, "A", 150, "profile")
    tap(F, "A", 90, "location")
    tap(F, "A", 90, "countries")
    tap(F, "B", 60, "location_back")
    tap(F, "B", 60, "profile_back1")
    tap(F, "Down", 30)
    tap(F, "A", 90, "birthday")
    tap(F, "B", 60, "profile_back2")
    tap(F, "Down", 30, "title_cursor")
    tap(F, "A", 90, "title")
    tap(F, "A", 90, "occupations")
    tap(F, "B", 60, "title_back1")
    tap(F, "Down", 30, "title_down")
    tap(F, "A", 90, "accolades")
    tap(F, "B", 60, "title_back2")
    tap(F, "B", 60, "profile_back3")
    tap(F, "Down", 30, "speech_cursor")
    tap(F, "A", 90, "speech")
    tap(F, "B", 60, "profile_back4")
    tap(F, "Down", 30, "greeting_cursor")
    tap(F, "A", 90, "greeting")
    tap(F, "B", 60, "profile_back5")
    for n in range(3):
        tap(F, "B", 60, f"exit{n}")
