import importlib.util
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load("battle")
START = B.START
GAME_STATE = 0x020F33D8
ACTION_TABLES = 0x02108E10
ACTION_ENTRY = 0x3C
ATTACK_ID = 1
TARGET_SELECTOR = 2
SLIME = 0xC0
NATALIA = 2
STATUS_BIT = 0x200
FAMILY = 3
DEFEND_ROUNDS = 1


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def obj(F, index):
    return u32(F, GAME_STATE + 8 + 4 * index)


def find_action(F, ident):
    for base in (ACTION_TABLES, ACTION_TABLES + 0xC):
        head, entries = struct.unpack("<II", F.cons[0].read(base, 8))
        for i in range(head & 0xFFF):
            rec = entries + i * ACTION_ENTRY
            if u32(F, rec + 4) & 0xFFF == ident:
                return rec
    raise RuntimeError(f"N5a_traits: action {ident:#x} not found")


def poke(F):
    con = F.cons[0]
    attack = find_action(F, ATTACK_ID)
    con.write(attack + 0xC, struct.pack("<H", TARGET_SELECTOR))
    stats = u32(F, obj(F, NATALIA) + 0x138)
    con.write(stats + 0x14, struct.pack("<I", u32(F, stats + 0x14) | STATUS_BIT))
    record = u32(F, obj(F, SLIME) + 0x144)
    kind = (u16(F, record + 0xA) & ~(0xF << 7)) | (FAMILY << 7)
    con.write(record + 0xA, struct.pack("<H", kind))


def defend_round(F):
    B.choose(F)
    for member in range(4):
        B.choose(F, ("Down", 2), last=member == 3)


def play(F):
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.wait(F, "menu", lambda: B.hand(F) is not None, 900)
    poke(F)

    defend_round(F)
    for turn in range(DEFEND_ROUNDS + B.ATTACK_TURNS):
        B.wait(F, "end of round", lambda: B.round_over(F), 3000)
        if B.finished(F):
            break
        if turn < DEFEND_ROUNDS - 1:
            defend_round(F)
        else:
            B.attack_turn(F)

    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
    B.wait(F, "field", lambda: B.byte(F, B.BATTLE) == 0, 600)
    F.run(120)
