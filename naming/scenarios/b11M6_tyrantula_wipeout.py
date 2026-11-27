import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = {"save": "saves/story/033 - Tyrantula.sav",
         "state": os.path.join(kitpaths.SP, "names", "b8", "R3", "tyb.mst")}
GAME_STATE = 0x020F33D8
PARTY = 0x020F5DDC
LAURA = 0
DEAD = 0x1
ROUNDS = 6
OUT = os.path.join(kitpaths.SP, "names", "b11", "M6", "tyrantula")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def dead(F):
    return u32(F, stats(F, LAURA) + 0x14) & DEAD


def weaken(F):
    if not dead(F):
        st = stats(F, LAURA)
        F.cons[0].write(st, struct.pack("<H", 1))
        F.cons[0].write(st + 0xA, struct.pack("<H", 0))


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def log(F, tag):
    con = F.cons[0]
    members = con.read(PARTY + 0xF78, 5)
    with open(os.path.join(OUT, "tyrantula.log"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"f{con.frames} {tag} battle {B.byte(F, B.BATTLE)} phase {B.byte(F, B.PHASE)} "
                 f"party {list(members[:members[4]])} laura +0x14 {u32(F, stats(F, LAURA) + 0x14):#x}\n")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "tyrantula.log"), "w").close()
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    for r in range(ROUNDS):
        B.wait(F, "menu", lambda: B.round_over(F) or dead(F), 4000)
        if B.finished(F) or dead(F):
            break
        log(F, f"round {r}")
        weaken(F)
        B.choose(F)
        B.choose(F, ("Down", 2), last=True)
        for n in range(0, 4000, 4):
            if B.round_over(F) or dead(F):
                break
            weaken(F)
            if n % 60 == 0:
                shot(F, f"r{r}")
            F.run(4)
    log(F, "down")
    for n in range(0, 3600, 30):
        if n % 90 == 0:
            shot(F, "after")
        F.hold(0, ["A"], 3)
        F.run(27)
    log(F, "end")
