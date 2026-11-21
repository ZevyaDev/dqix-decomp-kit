import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
GARREK = 3
POISON_FLAG = 0x2
TARGET_ROWS = 1
OUT = os.path.join(kitpaths.SP, "names", "b9", "E", "squelch")


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def describe(F, st):
    return f"stats {st:#x} +0x14 {u32(F, st + 0x14):#x} +0x22 {u16(F, st + 0x22):#x} hp {u16(F, st)}"


def shot(F, log, out, name):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(out, f"f{F.cons[0].frames}_{name}.png"))
    log.write(f"f{F.cons[0].frames} {name}\n")


def run(F, out, target_rows):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "squelch_mem.log"), "w", encoding="utf-8") as log:
        for _ in range(120):
            if B.byte(F, B.BATTLE):
                break
            F.hold(0, ["Left"], 4)
        B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
        B.wait(F, "menu", lambda: B.hand(F) is not None, 900)
        st = stats(F, GARREK)
        log.write(f"f{F.cons[0].frames} before {describe(F, st)}\n")
        F.cons[0].write(st + 0x14, struct.pack("<I", u32(F, st + 0x14) | POISON_FLAG))
        F.cons[0].write(st + 0x22, struct.pack("<H", (u16(F, st + 0x22) & ~3) | 1))
        log.write(f"f{F.cons[0].frames} poked {describe(F, st)}\n")
        B.choose(F)
        for _ in range(3):
            B.choose(F, ("Down", 2))
        B.choose(F, ("Down", 1))
        B.choose(F, ("Down", 1))
        shot(F, log, out, "target")
        B.choose(F, *([("Down", target_rows)] if target_rows else []), last=True)
        for k in range(10):
            F.run(45)
            shot(F, log, out, f"msg{k}")
        B.wait(F, "end of round", lambda: B.round_over(F), 3000)
        log.write(f"f{F.cons[0].frames} round over {describe(F, st)}\n")
        shot(F, log, out, "end")


def play(F):
    run(F, OUT, TARGET_ROWS)
