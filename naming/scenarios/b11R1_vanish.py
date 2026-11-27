import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/field_battle.mst"}
GAME_STATE = 0x020F33D8
KHEG = 0
OUT = os.path.join(kitpaths.SP, "names", "b11", "R1", "vanish")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames}_{name}.png"))
    kheg = u32(F, GAME_STATE + 8 + 4 * KHEG)
    record = u32(F, kheg + 0x130)
    with open(os.path.join(OUT, "vanish.log"), "a") as log:
        log.write(f"f{con.frames} {name}: Kheg 0x{kheg:x} record 0x{record:x} +4 {u16(F, record + 4)} "
                  f"+6 {u16(F, record + 6)}\n")


def press(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    F.run(2)
    shot(F, "start")
    press(F, "X", 60, "menu")
    press(F, "Right", 20)
    press(F, "A", 90)
    press(F, "A", 120, "spells_member")
    press(F, "Right", 40)
    for _ in range(3):
        press(F, "Down", 25)
    shot(F, "vanish_cursor")
    press(F, "A", 150, "cast")
    for i in range(5):
        press(F, "A", 60, f"advance{i}")
    for i in range(4):
        press(F, "B", 40, f"back{i}")
    F.run(120)
    shot(F, "field")
