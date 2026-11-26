import os
import struct

import kitpaths

START = {"save": "saves/story/011 - Arrival in Stornway.sav"}
GAME_STATE = 0x020F33D8
OUT = os.path.join(kitpaths.SP, "names", "b9", "A", "shots")


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"{name}_f{F.cons[0].frames}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def tap(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def records(F, tag):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
    for _ in range(3):
        tap(F, "B", 60)
    value = struct.unpack("<i", F.cons[0].read(GAME_STATE + 0x5CBC, 4))[0]
    print(f"{tag}: f{F.cons[0].frames} GameState+0x5cbc = {value:#x}")
    tap(F, "X", 60)
    tap(F, "Right", 20)
    tap(F, "Down", 20)
    shot(F, f"{tag}_menu")
    tap(F, "A", 400)
    shot(F, f"{tag}_records")
    F.run(200)
    shot(F, f"{tag}_records_later")


def play(F):
    records(F, "s011")
