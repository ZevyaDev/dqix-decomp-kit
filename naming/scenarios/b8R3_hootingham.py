import importlib.util
import os
import struct
import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = {"save": "saves/story/066 - Lt. Hootingham-Gore.sav",
         "state": os.path.join(kitpaths.SP, "names", "b8", "R3", "hg.mst")}
GAME_STATE = 0x020F33D8
LAURA, GORE = 0, 0xC1
ROUNDS = int(os.environ.get("B8R3_ROUNDS", "10"))
LOG = os.environ.get("B8R3_LOG")


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def report(F, tag):
    if not LOG:
        return
    parts = []
    for i in (LAURA, 0xC0, GORE, 0xC2):
        o = u32(F, GAME_STATE + 8 + 4 * i)
        if 0x02000000 <= o < 0x02400000:
            st = stats(F, i)
            parts.append(f"{i:#x}: hp {u16(F, st)} +14 {u32(F, st + 0x14):#x} +18 {u32(F, st + 0x18):#x}")
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{tag} f{F.cons[0].frames} " + " | ".join(parts) + "\n")


def heal(F):
    st = stats(F, LAURA)
    if not u32(F, st + 0x14) & 1:
        F.cons[0].write(st, struct.pack("<H", u16(F, st + 4)))


def play(F):
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    for r in range(ROUNDS):
        B.wait(F, "menu", lambda: B.round_over(F), 4000)
        if B.finished(F) or u32(F, stats(F, LAURA) + 0x14) & 1:
            break
        heal(F)
        report(F, f"round {r}")
        B.choose(F)
        B.choose(F, ("Down", 2), last=True)
        for _ in range(0, 4000, 4):
            if B.round_over(F):
                break
            if u16(F, stats(F, LAURA)) < 60:
                heal(F)
            F.run(4)
    report(F, "end")
