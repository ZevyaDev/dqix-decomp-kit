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
CONFUSED = 0x20
ROUNDS = 8
OUT = os.path.join(kitpaths.SP, "names", "b10", "M5", "confuse")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def report(F, tag):
    st = stats(F, SLIME)
    con = F.cons[0]
    with open(os.path.join(OUT, "confuse.log"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{tag} f{con.frames} slime stats {st:#x} +0x14 {u32(F, st + 0x14):#x} "
                 f"+0x5e {con.read(st + 0x5E, 1)[0]} +0x81 {con.read(st + 0x81, 1)[0]}\n")


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def confuse(F):
    st = stats(F, SLIME)
    con = F.cons[0]
    con.write(st + 0x14, struct.pack("<I", u32(F, st + 0x14) | CONFUSED))
    con.write(st + 0x18, struct.pack("<I", u32(F, st + 0x18) & ~0x20))
    con.write(st + 0x21, bytes([0]))
    con.write(st + 0x5E, bytes([3]))
    con.write(st + 0x81, bytes([0]))


def defend_round(F):
    B.choose(F)
    for n in range(4):
        B.choose(F, ("Down", 2), last=n == 3)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "confuse.log"), "w").close()
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.wait(F, "menu", lambda: B.round_over(F), 4000)
    confuse(F)
    report(F, "forced")
    for r in range(ROUNDS):
        if B.finished(F):
            break
        report(F, f"round {r}")
        defend_round(F)
        for n in range(0, 4000, 4):
            if B.round_over(F):
                break
            if n % 32 == 0:
                shot(F, f"r{r}")
            F.run(4)
        if not u32(F, stats(F, SLIME) + 0x14) & CONFUSED:
            report(F, f"cleared after round {r}")
            break
    report(F, "end")
