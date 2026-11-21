import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
KHEG, SLIME = 0, 0xC0
ASLEEP = 0x10
PSYCHE_UP_PAGE = 10
SUPER_HIGH = 4
ATTACK_AT = int(os.environ.get("B9H_STAGE", str(SUPER_HIGH)))
PSYCHE_ROUNDS = 8
LOG = os.path.join(kitpaths.SP, "names", "b9", "H", f"b9H_psyche_stats_stage{ATTACK_AT}.log")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def stage(F):
    return F.cons[0].read(stats(F, KHEG) + 0x24, 1)[0]


def slime_asleep(F):
    return u32(F, stats(F, SLIME) + 0x14) & ASLEEP


def report(F, tag):
    st = stats(F, KHEG)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{tag} f{F.cons[0].frames} kheg stats {st:#x} +0x14 {u32(F, st + 0x14):#x} +0x24 {stage(F)} "
                 f"slime +0x14 {u32(F, stats(F, SLIME) + 0x14):#x}\n")


def command_round(F, kheg_psyches, first, snoozes):
    B.choose(F)
    if kheg_psyches and first:
        B.choose(F, ("Right", 1))
        B.choose(F, *[("page", 0)] * (PSYCHE_UP_PAGE - 1))
    elif kheg_psyches:
        B.choose(F, ("Right", 1))
        B.choose(F)
    else:
        B.choose(F)
    B.choose(F, ("Down", 2))
    B.choose(F, ("Down", 2))
    if snoozes:
        B.choose(F, ("Down", 1))
        B.choose(F, ("Down", 0 if snoozes > 1 else 2), last=True)
    else:
        B.choose(F, ("Down", 2), last=True)


def play(F):
    open(LOG, "w").close()
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    rounds = snoozes = 0
    while True:
        B.wait(F, "menu", lambda: B.round_over(F), 4000)
        if B.finished(F):
            break
        report(F, f"round {rounds}")
        psyche = rounds < PSYCHE_ROUNDS and stage(F) < ATTACK_AT
        snooze = psyche and not slime_asleep(F)
        snoozes += snooze
        command_round(F, psyche, rounds == 0, snoozes if snooze else 0)
        rounds += 1
        if not psyche:
            B.wait(F, "end of round", lambda: B.round_over(F), 4000)
            report(F, "after attack")
            break
    report(F, f"battle over phase {B.byte(F, B.PHASE)}")
    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
    F.run(60)
