import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "R5", "profile_birthday")
GAME_STATE = 0x020F33D8
BLOCK = GAME_STATE + 0x569C
BLOCK_SIZE = 0x7C


def run_path(name):
    path = os.path.join(OUT, name)
    n = 1
    while os.path.exists(path):
        n += 1
        stem, ext = os.path.splitext(name)
        path = os.path.join(OUT, f"{stem}.r{n}{ext}")
    return path


def shot(F, tag, name):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"{tag}_f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def dump(F, log, name):
    block = bytes(F.cons[0].read(BLOCK, BLOCK_SIZE))
    w0, w1 = struct.unpack_from("<II", block, 0)
    log.write(f"f{F.cons[0].frames} {name} year {w0 & 0xfff} month {(w0 >> 12) & 0xf} day {(w0 >> 16) & 0x1f} "
              f"w1 {w1:#010x} block {block.hex()}\n")
    log.flush()


def play(F):
    os.makedirs(OUT, exist_ok=True)
    path = run_path("profile_birthday.log")
    tag = os.path.splitext(os.path.basename(path))[0]
    with open(path, "w", encoding="utf-8", newline="\n") as log:
        def tap(key, wait, name=None):
            F.hold(0, [key], 3)
            F.run(wait)
            if name:
                shot(F, tag, name)
                dump(F, log, name)

        F.run(30)
        dump(F, log, "start")
        tap("X", 40)
        tap("Right", 15)
        tap("Down", 15)
        tap("Down", 15)
        tap("A", 90)
        for _ in range(4):
            tap("Down", 20)
        tap("A", 150, "profile")
        tap("Down", 30)
        tap("A", 90, "birthday")
        tap("Up", 40, "day_up")
        tap("A", 90, "confirmed")
        tap("B", 60, "back1")
        for n in range(3):
            tap("B", 60, f"exit{n}")
