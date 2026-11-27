import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("tyrantula", os.path.join(os.path.dirname(__file__), "b8R3_tyrantula.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

START = T.START
T.ROUNDS = 30
OUT = os.path.join(kitpaths.SP, "names", "b11", "M7", "barrier")
LOG = os.path.join(OUT, "barrier_rounds.log")
B = T.B
WATCH = ((T.LAURA, 0x2, "fire"), (T.SPIDER, 0x4, "ice"))
CAPTURE_FRAMES = 900
POKES = ((T.LAURA, 0x2, 0x6C), (T.SPIDER, 0x4, 0x6D))
LAST_ROUND = 8


def barrier(F, index, bit, duration_offset):
    st = T.stats(F, index)
    con = F.cons[0]
    flags = T.u32(F, st + 0x18) | bit
    con.write(st + 0x18, struct.pack("<I", flags))
    con.write(st + duration_offset, bytes([5]))
    con.write(st + duration_offset + 0x23, bytes([0]))


def report(F, tag):
    con = F.cons[0]
    parts = []
    for i in (T.LAURA, T.SPIDER):
        st = T.stats(F, i)
        b = con.read(st + 0x5C, 0x46)
        parts.append(f"{i:#x}: +18 {T.u32(F, st + 0x18):#x} +6c {b[0x10]} +6d {b[0x11]} +8f {b[0x33]} +90 {b[0x34]}")
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{tag} f{con.frames} " + " | ".join(parts) + "\n")


def shot(F, name):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames}_{name}.png"))


class Watch:
    def __init__(self, F):
        self.F = F
        self.until = {}
        self.had = {name: False for _, _, name in WATCH}

    def step(self):
        F = self.F
        frame = F.cons[0].frames
        for index, bit, name in WATCH:
            on = bool(T.u32(F, T.stats(F, index) + 0x18) & bit)
            if self.had[name] and not on:
                self.until[name] = frame + CAPTURE_FRAMES
                with open(LOG, "a", encoding="utf-8") as fh:
                    fh.write(f"f{frame} {name} bit {bit:#x} cleared on {index:#x}\n")
            self.had[name] = on
        for name, end in list(self.until.items()):
            if frame > end:
                del self.until[name]
            elif frame % 16 < 4:
                shot(F, name)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write("run\n")
    watch = Watch(F)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    for r in range(T.ROUNDS):
        B.wait(F, "menu", lambda: B.round_over(F), 4000)
        if B.finished(F) or T.u32(F, T.stats(F, T.LAURA) + 0x14) & 1:
            break
        T.heal(F)
        if r == 0:
            F.cons[0].write(T.stats(F, T.SPIDER), struct.pack("<H", T.SPIDER_HP))
            for index, bit, duration_offset in POKES:
                barrier(F, index, bit, duration_offset)
        watch.step()
        report(F, f"round {r}")
        if r > LAST_ROUND and not watch.until:
            break
        B.choose(F)
        B.choose(F, last=True)
        for _ in range(0, 4000, 4):
            if B.round_over(F) and not watch.until:
                break
            if T.u16(F, T.stats(F, T.LAURA)) < 40:
                T.heal(F)
            F.run(4)
            watch.step()
    report(F, "end")
