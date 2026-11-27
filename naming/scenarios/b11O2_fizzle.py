import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
SLIME = 0xC0
SPELLS_BLOCKED = 0x100
EXTRA_FIZZLES = 1
MAX_ROUNDS = 16
OUT = os.path.join(kitpaths.SP, "names", "b11", "O2", "fizzle")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def blocked(F):
    return u32(F, stats(F, SLIME) + 0x14) & SPELLS_BLOCKED


def report(F, tag):
    st = stats(F, SLIME)
    con = F.cons[0]
    with open(os.path.join(OUT, "fizzle.log"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{tag} f{con.frames} slime stats {st:#x} +0x14 {u32(F, st + 0x14):#x} +0x60 {con.read(st + 0x60, 1)[0]}\n")


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def fizzle_round(F, first):
    B.choose(F)
    B.choose(F, ("Down", 2))
    B.choose(F, ("Down", 2))
    if first:
        B.choose(F, ("Down", 1))
        B.press(F, "Right")
        F.run(20)
        B.choose(F, ("Down", 1))
    else:
        B.choose(F, ("Down", 1))
        F.run(10)
        shot(F, "spell_list")
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
    open(os.path.join(OUT, "fizzle.log"), "w").close()
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.wait(F, "menu", lambda: B.round_over(F), 4000)
    extra = 0
    for r in range(MAX_ROUNDS):
        if B.finished(F):
            break
        report(F, f"round {r} start")
        was_blocked = blocked(F)
        fizzle_round(F, r == 0)
        watch(F, f"r{r}")
        report(F, f"round {r} end")
        if was_blocked:
            extra += 1
            if extra >= EXTRA_FIZZLES:
                break
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
