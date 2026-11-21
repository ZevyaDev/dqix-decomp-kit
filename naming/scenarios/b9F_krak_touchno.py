import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("C5_krakpot", os.path.join(os.path.dirname(__file__), "C5_krakpot.py"))
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)

START = K.START
WINDOW = 0x0239040C
NO = (232, 104)
LOG = os.path.join(kitpaths.SP, "names", "b9", "F", "b9F_krak_touchno.log")


def window_state(F):
    con = F.cons[0]
    record = struct.unpack("<I", con.read(WINDOW + 0xC, 4))[0]
    if not 0x02000000 <= record < 0x02400000:
        return None
    flags = con.read(record + 0x3F, 1)[0]
    cursor, choice, _, touched = struct.unpack("<bbbB", con.read(WINDOW + 0x14, 4))
    return flags, cursor, choice, touched


def to_prompt(F):
    F.run(30)
    F.move_to(0, tz=9.12)
    F.move_to(0, tx=1.74)
    F.align(0, tx=1.74)
    F.move_to(0, tz=7.92)
    F.hold(0, ["Up"], 2)
    F.run(4)
    for _ in range(5):
        K.press(F, "A", 90)
    for _ in range(4):
        K.press(F, "Down", 20)
    for _ in range(3):
        K.press(F, "A", 90)
    for _ in range(600):
        s = window_state(F)
        if s and s[0] & 1:
            return
        F.run(1)
    raise RuntimeError("b9F_krak_touchno: the Yes/No window never opened")


def tap(F, log, point):
    con = F.cons[0]
    log.write(f"f{con.frames} touch {point} before {window_state(F)}\n")
    con.touch(*point)
    F.run(4)
    con.touch()
    log.write(f"f{con.frames} released {window_state(F)}\n")
    F.run(60)
    log.write(f"f{con.frames} after 60 {window_state(F)}\n")


def play(F):
    with open(LOG, "w", encoding="utf-8") as log:
        to_prompt(F)
        log.write(f"f{F.cons[0].frames} open {window_state(F)}\n")
        F.run(30)
        tap(F, log, NO)
        tap(F, log, NO)
        F.run(240)
        log.write(f"f{F.cons[0].frames} end {window_state(F)}\n")
        for _ in range(6):
            K.press(F, "B", 60)
