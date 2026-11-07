import importlib.util
import os
import struct

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
GARREK = 3
POISONED = 0x2
DEFEND_ROUNDS = 3
LOG = "D:/Downloads/decomp/dqix-sp/names/b7/M4/M4_venom_mem.log"


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def describe(F, st):
    return (f"stats {st:#x} +0x14 {u32(F, st + 0x14):#x} +0x22 {u16(F, st + 0x22):#x} "
            f"hp {u16(F, st)} maxhp {u16(F, st + 4)}")


def play(F):
    with open(LOG, "w", encoding="utf-8") as log:
        for _ in range(120):
            if B.byte(F, B.BATTLE):
                break
            F.hold(0, ["Left"], 4)
        B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
        B.wait(F, "menu", lambda: B.hand(F) is not None, 900)
        st = stats(F, GARREK)
        log.write(f"f{F.cons[0].frames} before {describe(F, st)}\n")
        F.cons[0].write(st + 0x14, struct.pack("<I", u32(F, st + 0x14) | POISONED))
        F.cons[0].write(st + 0x22, struct.pack("<H", (u16(F, st + 0x22) & ~3) | 2))
        log.write(f"f{F.cons[0].frames} poked {describe(F, st)}\n")
        for _ in range(DEFEND_ROUNDS):
            B.choose(F)
            for member in range(4):
                B.choose(F, ("Down", 2), last=member == 3)
            B.wait(F, "end of round", lambda: B.round_over(F), 3000)
            log.write(f"f{F.cons[0].frames} defended {describe(F, st)}\n")
            if B.finished(F):
                break
        for _ in range(8):
            if B.finished(F):
                break
            B.attack_turn(F)
            B.wait(F, "end of round", lambda: B.round_over(F), 3000)
            log.write(f"f{F.cons[0].frames} round {describe(F, st)}\n")
            if B.finished(F):
                break
        for _ in range(60):
            if B.byte(F, B.BATTLE) == 0:
                break
            if B.byte(F, B.PHASE) == B.WON:
                B.press(F, "A")
            F.run(30)
        log.write(f"f{F.cons[0].frames} battle byte {B.byte(F, B.BATTLE)} {describe(F, st)}\n")
        F.run(60)
