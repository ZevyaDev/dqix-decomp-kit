import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("b9F_krak_touchno", os.path.join(os.path.dirname(__file__), "b9F_krak_touchno.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

START = T.START
WINDOW = T.WINDOW
NO = T.NO
YES = (232, 88)
OBJ_PALETTE = (0x05000200, 0x05000600)
DISPCNT = (0x04000000, 0x04001000)
OUT = os.path.join(kitpaths.SP, "names", "b10", "R1b")
LOG = os.path.join(OUT, "yesno_palette.log")


def u16(con, addr):
    return struct.unpack("<H", con.read(addr, 2))[0]


def u32(con, addr):
    return struct.unpack("<I", con.read(addr, 4))[0]


def state(F):
    con = F.cons[0]
    cursor, choice, default, touched = struct.unpack("<bbbB", con.read(WINDOW + 0x14, 4))
    window = u32(con, WINDOW + 0x10)
    line = f"cursorIndex {cursor} choice {choice} +0x16 {default} +0x17 {touched}"
    if not 0x02000000 <= window < 0x02400000:
        return line + " window none"
    record = u32(con, window + 4)
    flags = con.read(record + 0x3F, 1)[0]
    screen = con.read(record + 0x3E, 1)[0]
    rect = tuple(con.read(record + 0x38, 4))
    base = OBJ_PALETTE[1 if screen else 0] + 0x1C0
    line += (f" window {window:#x} +0x22 {u16(con, window + 0x22):#06x} +0x24 {u16(con, window + 0x24):#06x}"
             f" record {record:#x} +0x3e {screen} +0x3f {flags:#04x} rect {rect}"
             f" objPalette14[9] {u16(con, base + 9 * 2):#06x} objPalette14[11] {u16(con, base + 11 * 2):#06x}")
    display = tuple(con.read(window + 0x28, 3))
    dispcnt = u32(con, DISPCNT[1 if screen else 0])
    line += f" displayWindow {display} dispcnt[13:15] {(dispcnt >> 13) & 7:#x}"
    return line


def shot(F, name):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"yesno_f{con.frames}_{name}.png"))


def note(F, log, name):
    log.write(f"f{F.cons[0].frames} {name}: {state(F)}\n")
    shot(F, name)


def tap(F, point):
    con = F.cons[0]
    con.touch(*point)
    F.run(4)
    con.touch()
    F.run(60)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as log:
        T.to_prompt(F)
        F.run(30)
        note(F, log, "open")
        tap(F, NO)
        note(F, log, "touched_no")
        T.K.press(F, "Up", 30)
        note(F, log, "up")
        tap(F, YES)
        note(F, log, "touched_yes")
        T.K.press(F, "B", 60)
        note(F, log, "cancelled")
        for _ in range(6):
            T.K.press(F, "B", 60)
