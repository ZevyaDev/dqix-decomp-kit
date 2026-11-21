import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "M4", "sevolume")
SOUND_EFFECT_MANAGER = 0x02108760


def shot(F, log, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    c = F.cons[0]
    px = bytes(c.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{c.frames}_{name}.png"))
    volume = int.from_bytes(c.read(SOUND_EFFECT_MANAGER + 0xC8, 4), "little")
    level = c.read(SOUND_EFFECT_MANAGER + 0xCC, 1)[0]
    log.write(f"f{c.frames} {name} volumeLevel {level} volume {volume:#x}\n")


def tap(F, log, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, log, name)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "sevolume.log"), "w", encoding="utf-8") as log:
        F.run(30)
        shot(F, log, "start")
        tap(F, log, "X", 60, "menu")
        tap(F, log, "Right", 20)
        tap(F, log, "Down", 20)
        tap(F, log, "Down", 20, "misc_cursor")
        tap(F, log, "A", 90, "misc_open")
        for _ in range(5):
            tap(F, log, "Down", 20)
        shot(F, log, "volume_cursor")
        tap(F, log, "A", 120, "volume_open")
        tap(F, log, "Down", 30, "effects_row")
        for i in range(3):
            tap(F, log, "Left", 40, f"left{i}")
        for i in range(2):
            tap(F, log, "Right", 40, f"right{i}")
        tap(F, log, "Down", 30, "confirm_row")
        tap(F, log, "A", 90, "confirm")
        tap(F, log, "A", 90, "confirm2")
        F.run(60)
        shot(F, log, "end")
