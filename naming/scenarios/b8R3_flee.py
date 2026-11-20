import importlib.util
import os
import struct

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
SLIME = 0xC0
ROUNDS = 16
LOG = os.environ.get("B8R3_LOG")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def report(F, tag):
    if not LOG:
        return
    o = u32(F, GAME_STATE + 8 + 4 * SLIME)
    line = f"{tag} f{F.cons[0].frames} battle {B.byte(F, B.BATTLE)} phase {B.byte(F, B.PHASE)}"
    if 0x02000000 <= o < 0x02400000:
        st = u32(F, o + 0x138)
        line += f" slime hp {struct.unpack('<H', F.cons[0].read(st, 2))[0]} +14 {u32(F, st + 0x14):#x} +18 {u32(F, st + 0x18):#x}"
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def play(F):
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    for r in range(ROUNDS):
        B.wait(F, "menu or end", lambda: B.round_over(F) or B.byte(F, B.BATTLE) == 0, 4000)
        report(F, f"round {r}")
        if B.finished(F) or B.byte(F, B.BATTLE) == 0:
            break
        B.choose(F)
        for member in range(4):
            B.choose(F, ("Down", 2), last=member == 3)
        for _ in range(0, 4000, 4):
            if B.round_over(F) or B.byte(F, B.BATTLE) == 0:
                break
            F.run(4)
    report(F, "after rounds")
    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
    B.wait(F, "field", lambda: B.byte(F, B.BATTLE) == 0, 900)
    report(F, "field")
    F.run(60)
