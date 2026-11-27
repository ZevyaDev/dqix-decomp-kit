import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load("battle")
F1 = load("O1_forced")
START = B.START
KHEG, MELANIE, NATALIA, GARREK = 0, 1, 2, 3
MENU_ORDER = (KHEG, GARREK, NATALIA, MELANIE)
DEAD = 0x1
POISON_FLAG = 0x2
RAGE_BIT = 0x1000
ROUNDS = 10
OUT = os.path.join(kitpaths.SP, "names", "b11", "M6", "wipeout")


def flags(F, index):
    return F1.u32(F, F1.stats(F, index) + 0x14)


def alive(F):
    return [i for i in MENU_ORDER if not flags(F, i) & DEAD]


def weaken(F):
    for i in alive(F):
        st = F1.stats(F, i)
        F1.put(F, st, "<H", 1)
        F1.put(F, st + 0xA, "<H", 0)


def poison(F):
    for i in alive(F):
        st = F1.stats(F, i)
        F1.put(F, st + 0x14, "<I", F1.u32(F, st + 0x14) | POISON_FLAG)
        F1.put(F, st + 0x22, "<H", struct.unpack("<H", F.cons[0].read(st + 0x22, 2))[0] & ~3 | 1)


def enrage(F, target):
    st = F1.stats(F, F1.SLIME)
    F1.put(F, st + 0x18, "<I", F1.u32(F, st + 0x18) | RAGE_BIT)
    F1.put(F, st + 0x7E, "<B", 3)
    F1.put(F, st + 0xA1, "<B", 0)
    F1.put(F, st + 0x2E, "<h", target)


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def log(F, tag):
    con = F.cons[0]
    party = " ".join(f"{i}:{flags(F, i):#x}" for i in MENU_ORDER)
    with open(os.path.join(OUT, "wipeout.log"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"f{con.frames} {tag} battle {B.byte(F, B.BATTLE)} phase {B.byte(F, B.PHASE)} flags {party}\n")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "wipeout.log"), "w").close()
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    for turn in range(ROUNDS):
        B.wait(F, "round", lambda: B.round_over(F) or not alive(F), 4000)
        if B.finished(F) or not alive(F):
            break
        members = alive(F)
        log(F, f"round {turn}")
        enrage(F, members[0])
        poison(F)
        weaken(F)
        B.choose(F)
        for i in members:
            B.choose(F, ("Down", 2), last=i == members[-1])
        for n in range(0, 4000, 4):
            if B.round_over(F) or not alive(F):
                break
            weaken(F)
            if n % 60 == 0:
                shot(F, f"r{turn}")
            F.run(4)
    log(F, "party down")
    for n in range(0, 3600, 30):
        if n % 90 == 0:
            shot(F, "after")
        F.hold(0, ["A"], 3)
        F.run(27)
    log(F, "end")
