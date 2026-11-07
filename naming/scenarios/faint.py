import importlib.util
import os
import struct

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
KHEG, MELANIE, NATALIA, GARREK = 0, 1, 2, 3
SLIME = 0xC0
MENU_ORDER = (KHEG, GARREK, NATALIA, MELANIE)
WEAK = (GARREK, NATALIA)
DEAD, ASLEEP = 0x1, 0x10
ROUNDS = 14


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def flags(F, index):
    return u32(F, stats(F, index) + 0x14)


def weaken(F):
    for i in WEAK:
        if not flags(F, i) & DEAD:
            st = stats(F, i)
            F.cons[0].write(st, struct.pack("<H", 1))
            F.cons[0].write(st + 0xA, struct.pack("<H", 0))


def fainted(F):
    return any(flags(F, i) & DEAD for i in MENU_ORDER)


def command_round(F, snooze, attack):
    B.choose(F)
    alive = [i for i in MENU_ORDER if not flags(F, i) & DEAD]
    for i in alive:
        last = i == alive[-1]
        if attack:
            B.choose(F, last=last)
        elif snooze and i == MELANIE:
            B.choose(F, ("Down", 1))
            B.choose(F, ("Down", 0 if snooze > 1 else 2), last=last)
        else:
            B.choose(F, ("Down", 2), last=last)


def play(F):
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.wait(F, "menu", lambda: B.hand(F) is not None, 900)

    snoozes = 0
    for _ in range(ROUNDS):
        asleep = flags(F, SLIME) & ASLEEP
        if fainted(F) and not flags(F, MELANIE) & DEAD and not asleep:
            snoozes += 1
        command_round(F, snoozes, fainted(F) and asleep)
        for _ in range(0, 3000, 4):
            if not fainted(F):
                weaken(F)
            if B.round_over(F):
                break
            F.run(4)
        else:
            raise RuntimeError("faint: no end of round after 3000 frames")
        if B.finished(F):
            break
    else:
        raise RuntimeError(f"faint: battle not over after {ROUNDS} rounds "
                           f"(fainted {fainted(F)}, slime flags {flags(F, SLIME):#x})")
    if not fainted(F):
        raise RuntimeError("faint: nobody fainted")

    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
    B.wait(F, "field", lambda: B.byte(F, B.BATTLE) == 0, 600)
    F.run(60)
