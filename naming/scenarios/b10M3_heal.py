import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
GAME_STATE = 0x020F33D8
KHEG, GARREK = 0, 3
HURT_HP = 300
OUT = os.path.join(kitpaths.SP, "names", "b10", "M3", "heal")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def record(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x130)


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames}_{name}.png"))
    with open(os.path.join(OUT, "heal.log"), "a") as log:
        for who, index in (("Kheg", KHEG), ("Garrek", GARREK)):
            r = record(F, index)
            log.write(f"f{con.frames} {name}: {who} record 0x{r:x} +4 {u16(F, r + 4)} +6 {u16(F, r + 6)}\n")


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    F.run(30)
    F.cons[0].write(record(F, GARREK) + 4, struct.pack("<H", HURT_HP))
    shot(F, "hurt")
    tap(F, "X", 60, "menu")
    tap(F, "Right", 20)
    tap(F, "A", 90, "spells_open")
    tap(F, "A", 120, "spells_member")
    tap(F, "Down", 20, "heal_cursor")
    tap(F, "A", 90, "heal_target")
    tap(F, "Down", 20, "garrek_cursor")
    tap(F, "A", 150, "cast")
    for i in range(5):
        tap(F, "A", 60, f"advance{i}")
    for i in range(4):
        tap(F, "B", 40, f"back{i}")
