import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
NATALIA = 2
SPELLS_BLOCKED = 0x100
OUT = os.path.join(kitpaths.SP, "names", "b11", "O2", "fizzled")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def report(F, tag):
    st = stats(F, NATALIA)
    con = F.cons[0]
    with open(os.path.join(OUT, "fizzled.log"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{tag} f{con.frames} natalia stats {st:#x} +0x14 {u32(F, st + 0x14):#x} "
                 f"+0x60 {con.read(st + 0x60, 1)[0]} +0x83 {con.read(st + 0x83, 1)[0]}\n")


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def block_spells(F):
    st = stats(F, NATALIA)
    con = F.cons[0]
    con.write(st + 0x14, struct.pack("<I", u32(F, st + 0x14) | SPELLS_BLOCKED))
    con.write(st + 0x60, bytes([6]))
    con.write(st + 0x83, bytes([0]))


def fizzle_round(F, first):
    B.choose(F)
    B.choose(F, ("Down", 2))
    B.choose(F, ("Down", 2))
    B.choose(F, ("Down", 1))
    if first:
        B.press(F, "Right")
        F.run(20)
        B.choose(F, ("Down", 1))
    else:
        B.choose(F)
    B.choose(F, ("Down", 2), last=True)


def attack_round(F):
    B.choose(F)
    for n in range(4):
        B.choose(F, last=n == 3)


def watch(F, tag):
    for n in range(0, 4000, 4):
        if B.round_over(F):
            break
        if n % 32 == 0:
            shot(F, tag)
        F.run(4)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "fizzled.log"), "w").close()
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.wait(F, "menu", lambda: B.round_over(F), 4000)
    report(F, "round 0 start")
    fizzle_round(F, True)
    watch(F, "r0")
    report(F, "round 0 end")
    if not B.finished(F):
        block_spells(F)
        report(F, "round 1 start, bit 0x100 set as func_020888a4 does")
        fizzle_round(F, False)
        watch(F, "r1")
        report(F, "round 1 end")
    if not B.finished(F):
        attack_round(F)
        watch(F, "attack")
        report(F, "after attack")
    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
    report(F, "end")
