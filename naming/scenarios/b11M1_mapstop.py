import os

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/grotto.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "M1", "mapstop")
GAME_STATE = 0x020F33D8
GROTTO = GAME_STATE + 0x63E4
MAPS = GAME_STATE + 0x64F4


def shot(F, name):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"f{F.cons[0].frames:05d}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def note(F, out, tag):
    con = F.cons[0]
    count = con.read(MAPS, 1)[0]
    marked = [i for i in range(count) if con.read(MAPS + 2 + i * 0x1C, 1)[0] & 0x20]
    head = con.read(GROTTO, 2)
    out.write(f"f{con.frames} {tag} grotto+0 {head[0]} grotto+1 {head[1]} maps {count} bit0x20 {marked}\n")


def tap(F, out, key, wait, name):
    F.hold(0, [key], 3)
    F.run(wait)
    shot(F, name)
    note(F, out, name)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "mapstop.log"), "w") as out:
        F.run(30)
        note(F, out, "start")
        tap(F, out, "X", 60, "menu")
        tap(F, out, "A", 120, "items")
        tap(F, out, "Down", 30, "down0")
        tap(F, out, "Down", 30, "down1")
        tap(F, out, "A", 200, "maps")
        tap(F, out, "A", 150, "question")
        tap(F, out, "Down", 40, "toyes")
        tap(F, out, "A", 120, "yes")
        tap(F, out, "A", 90, "closed")
        for n in range(4):
            tap(F, out, "B", 80, f"back{n}")
        F.run(200)
        shot(F, "field")
        note(F, out, "field")
