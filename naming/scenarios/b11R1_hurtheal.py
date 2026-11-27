import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
MENU_ORDER = (("Kheg", 0), ("Garrek", 3), ("Natalia", 2), ("Melanie", 1))
ROUNDS = 16
OUT = os.path.join(kitpaths.SP, "names", "b11", "R1", "hurtheal")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def obj(F, index):
    return u32(F, GAME_STATE + 8 + 4 * index)


def record(F, index):
    return u32(F, obj(F, index) + 0x130)


def hp(F, index):
    return u16(F, record(F, index) + 4)


def log(F, line):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "hurtheal.log"), "a") as fh:
        fh.write(f"f{F.cons[0].frames} {line}\n")


def party(F, tag):
    parts = []
    for name, index in MENU_ORDER:
        r = record(F, index)
        cur = u32(F, obj(F, index) + 0x138)
        parts.append(f"{name} record 0x{r:x} +4 {u16(F, r + 4)} +6 {u16(F, r + 6)} stats+0 {u16(F, cur)}")
    log(F, f"{tag}: " + " | ".join(parts))


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames}_{name}.png"))
    party(F, name)


def buff_round(F, marks):
    B.choose(F)
    B.choose(F, ("Down", 2))
    B.choose(F, ("Down", 2))
    B.choose(F, ("Down", 2))
    B.choose(F, ("Down", 1))
    B.wait(F, "spell list", lambda: B.hand(F) is not None, 120, 2)
    if "buff" not in marks:
        B.move(F, "Down", 3)
        marks["buff"] = B.hand(F)[1]
    else:
        for _ in range(8):
            y = B.hand(F)[1]
            if abs(y - marks["buff"]) < 4:
                break
            B.move(F, "Down" if y < marks["buff"] else "Up")
    log(F, f"spell cursor y {B.hand(F)[1]:.1f}")
    B.choose(F)
    B.wait(F, "target list", lambda: B.hand(F) is not None, 120, 2)
    if "target" not in marks:
        marks["target"] = B.hand(F)[1]
    else:
        for _ in range(8):
            y = B.hand(F)[1]
            if abs(y - marks["target"]) < 4:
                break
            B.move(F, "Down" if y < marks["target"] else "Up")
    B.choose(F, last=True)


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def play(F):
    start = {index: hp(F, index) for _, index in MENU_ORDER}
    party(F, "start")
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)

    hurt = None
    marks = {}
    for r in range(ROUNDS):
        B.wait(F, "end of round", lambda: B.round_over(F), 3000)
        if B.finished(F):
            break
        party(F, f"round {r}")
        hurt = next((name for name, index in MENU_ORDER
                     if u16(F, u32(F, obj(F, index) + 0x138)) < start[index]), None)
        if hurt:
            shot(F, f"hurt_{hurt}")
            break
        buff_round(F, marks)
    for _ in range(B.ATTACK_TURNS):
        B.wait(F, "end of round", lambda: B.round_over(F), 3000)
        if B.finished(F):
            break
        B.attack_turn(F)

    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
    B.wait(F, "field", lambda: B.byte(F, B.BATTLE) == 0, 600)
    F.run(120)
    shot(F, "field")

    target = next((pos for pos, (_, index) in enumerate(MENU_ORDER) if hp(F, index) < start[index]), None)
    log(F, f"hurt member menu position {target}")
    if target is None:
        return
    tap(F, "X", 60, "menu")
    tap(F, "Right", 20)
    tap(F, "A", 90, "spells_open")
    tap(F, "A", 120, "spells_member")
    tap(F, "Down", 20, "heal_cursor")
    tap(F, "A", 90, "heal_target")
    for _ in range(target):
        tap(F, "Down", 20)
    shot(F, "target_cursor")
    tap(F, "A", 150, "cast")
    for i in range(5):
        tap(F, "A", 60, f"advance{i}")
    for i in range(4):
        tap(F, "B", 40, f"back{i}")
