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
KHEG, MELANIE, NATALIA, GARREK = 0, 1, 2, 3
SLIME = 0xC0
TENSION_BIT = 0x800000
STATUS_BIT_8 = 0x8
TARGET_LOCK_BIT = 0x1000
ROUNDS = 6
DEBUG = os.environ.get("O1_DEBUG")


def snap(F, tag):
    if not DEBUG:
        return
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(DEBUG, f"{tag}.png"))


def log(F, tag):
    if not DEBUG:
        return
    slime = obj(F, SLIME)
    st = stats(F, SLIME)
    record = u32(F, slime + 0x144)
    lines = [f"{tag}: slime {slime:#x} id {u16(F, slime + 2):#x} record {record:#x} "
             f"+0xa {u16(F, record + 0xA):#06x} (bits 0-6 = {u16(F, record + 0xA) & 0x7F}) "
             f"stats +0x14 {u32(F, st + 0x14):#x} +0x18 {u32(F, st + 0x18):#x} "
             f"+0x24 {F.cons[0].read(st + 0x24, 1)[0]} +0x2e {struct.unpack('<h', F.cons[0].read(st + 0x2E, 2))[0]}"]
    for index in (KHEG, MELANIE, NATALIA, GARREK):
        o = obj(F, index)
        data = u32(F, o + 0x150)
        vocation = u32(F, data + 0x950)
        st = stats(F, index)
        lines.append(f"  member {index}: object {o:#x} data {data:#x} vocation {vocation} "
                     f"level {u16(F, data + 0x16C + 2 * vocation)} stats +0x14 {u32(F, st + 0x14):#x} "
                     f"+0x24 {F.cons[0].read(st + 0x24, 1)[0]} hp {u16(F, st)}")
    with open(os.path.join(DEBUG, "O1_forced_mem.log"), "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def put(F, addr, fmt, value):
    F.cons[0].write(addr, struct.pack(fmt, value))


def obj(F, index):
    return u32(F, GAME_STATE + 8 + 4 * index)


def stats(F, index):
    return u32(F, obj(F, index) + 0x138)


def find_action(F, ident):
    for base in (ACTION_TABLES, ACTION_TABLES + 0xC):
        head, entries = struct.unpack("<II", F.cons[0].read(base, 8))
        for i in range(head & 0xFFF):
            rec = entries + i * ACTION_ENTRY
            if u32(F, rec + 4) & 0xFFF == ident:
                return rec
    raise RuntimeError(f"O1_forced: action {ident:#x} not found")


def tension(F, index, level):
    st = stats(F, index)
    put(F, st + 0x14, "<I", u32(F, st + 0x14) | TENSION_BIT)
    put(F, st + 0x24, "<B", level)


def poke(F):
    put(F, find_action(F, ATTACK_ID) + 0xC, "<H", TARGET_SELECTOR)
    tension(F, KHEG, 2)
    tension(F, SLIME, 2)
    st = stats(F, SLIME)
    put(F, st + 0x18, "<I", u32(F, st + 0x18) | TARGET_LOCK_BIT)
    put(F, st + 0x7E, "<B", 3)
    put(F, st + 0xA1, "<B", 0)
    put(F, st + 0x2E, "<h", GARREK)


def paralyse(F, index):
    st = stats(F, index)
    put(F, st + 0x14, "<I", u32(F, st + 0x14) | STATUS_BIT_8)
    put(F, st + 0x5C, "<B", 3)
    put(F, st + 0x7F, "<B", 0)


def command_round(F, plan):
    B.choose(F)
    if plan == "kheg_attacks":
        B.choose(F)
        B.choose(F)
    key = None if plan == "all_attack" else ("Down", 2)
    while True:
        if key:
            B.choose(F, key, last=True)
        else:
            B.choose(F, last=True)
        for _ in range(20):
            if B.hand(F) is not None:
                break
            F.run(4)
        else:
            return


PLANS = ("all_defend", "all_defend", "kheg_attacks")


def play(F):
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.wait(F, "menu", lambda: B.hand(F) is not None, 900)
    poke(F)

    snap(F, "poked")
    log(F, "poked")
    for turn in range(ROUNDS):
        if turn:
            tension(F, SLIME, 2)
        plan = PLANS[turn] if turn < len(PLANS) else "all_attack"
        if plan == "kheg_attacks":
            tension(F, KHEG, 2)
        command_round(F, plan)
        if turn == 0:
            paralyse(F, NATALIA)
        snap(F, f"round{turn}_commanded")
        log(F, f"round{turn}_commanded")
        for step in range(0, 3000, 30):
            if B.round_over(F):
                break
            F.run(30)
            snap(F, f"round{turn}_f{step:04d}")
        if not B.round_over(F):
            raise RuntimeError(f"O1_forced: no end of round {turn} after 3000 frames")
        if B.finished(F):
            break

    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
    B.wait(F, "field", lambda: B.byte(F, B.BATTLE) == 0, 600)
    F.run(120)
