import importlib.util
import os
import struct
import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = {"save": "D:/Downloads/dqvc/work/saves/github_playinful_dq9-tools/033 - Tyrantula.sav",
         "state": os.path.join(kitpaths.SP, "names", "b8", "R3", "tyb.mst")}
GAME_STATE = 0x020F33D8
LAURA, SPIDER = 0, 0xC0
SPIDER_HP = 549
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
    for i in (LAURA, SPIDER):
        st = stats(F, i)
        parts.append(f"{i:#x}: hp {u16(F, st)}/{u16(F, st + 4)} +14 {u32(F, st + 0x14):#x} +18 {u32(F, st + 0x18):#x} "
                     f"+2e {struct.unpack('<h', F.cons[0].read(st + 0x2E, 2))[0]} +7e {F.cons[0].read(st + 0x7E, 1)[0]}")
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
        if r == 0:
            F.cons[0].write(stats(F, SPIDER), struct.pack("<H", SPIDER_HP))
        report(F, f"round {r}")
        B.choose(F)
        B.choose(F, last=True)
        for _ in range(0, 4000, 4):
            if B.round_over(F):
                break
            if u16(F, stats(F, LAURA)) < 40:
                heal(F)
            F.run(4)
    report(F, "end")
