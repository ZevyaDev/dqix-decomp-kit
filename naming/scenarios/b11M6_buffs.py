import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load("battle")
F1 = load("O1_forced")
START = B.START
KHEG, MELANIE, NATALIA, GARREK = 0, 1, 2, 3
SLIME_HP = 3000
ASLEEP = 0x10
ROUNDS = 16
SET = os.environ.get("B11M6_SET", "1")
OUT = os.path.join(kitpaths.SP, "names", "b11", "M6", "buffs")
CHARM = (9, 0x71, 6, 0x94, 0x2000)
MIGHT = (12, 0x72, 5, 0x95, 0x4000)

PLANS = {
    "1": [
        [("ability", 6, 2), ("defend",), ("spell", 3, 3), ("spell", 4, 1)],
        [("spell", 2, 1), ("defend",), ("ability", 8, 1), ("defend",)],
    ],
    "2": [
        [("ability", 9, 1), ("defend",), ("spell", 2, 0), ("spell", 1, 3)],
    ],
}
POKES = {"2": [(GARREK, CHARM), (GARREK, MIGHT)]}


def log(F, tag):
    con = F.cons[0]
    lines = [f"{tag} f{con.frames}"]
    for index, name in ((KHEG, "kheg"), (GARREK, "garrek"), (NATALIA, "natalia"), (MELANIE, "melanie")):
        st = F1.stats(F, index)
        timers = con.read(st + 0x6E, 10).hex()
        counters = con.read(st + 0x91, 10).hex()
        lines.append(f"  {name} {st:#x} +0x14 {F1.u32(F, st + 0x14):#010x} +0x18 {F1.u32(F, st + 0x18):#010x} "
                     f"+0x58 {F1.u32(F, st + 0x58):#010x} +0x6e.. {timers} +0x91.. {counters}")
    with open(os.path.join(OUT, f"set{SET}.log"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"set{SET}_f{con.frames:05d}_{tag}.png"))


def pick(F, *moves):
    B.wait(F, "menu", lambda: B.hand(F) is not None, 900)
    for key, rows in moves:
        if key == "page":
            B.press(F, "Right")
            F.run(15)
        else:
            B.move(F, key, rows)
    before = B.hand(F)
    B.press(F, "A")
    B.wait(F, "menu change", lambda: B.moved(before, B.hand(F)), 60, 2)
    for _ in range(40):
        found = B.hand(F)
        if found is not None:
            return found
        F.run(2)
    return None


def command(F, plan):
    kind = plan[0]
    if kind == "defend":
        found = pick(F, ("Down", 2))
    else:
        page, row = plan[1], plan[2]
        pick(F, ("Down", 1) if kind == "spell" else ("Right", 1))
        found = pick(F, *([("page", 0)] * (page - 1)), ("Down", row))
    if found is not None and found[0] > 150:
        found = pick(F)
    return found


def poke(F, index, field):
    shift, timer, duration, counter, flag = field
    st = F1.stats(F, index)
    word = F1.u32(F, st + 0x58) & ~(7 << shift) | (1 << shift)
    F1.put(F, st + 0x58, "<I", word)
    F1.put(F, st + timer, "<B", duration)
    F1.put(F, st + counter, "<B", 0)
    F1.put(F, st + 0x14, "<I", F1.u32(F, st + 0x14) | flag)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, f"set{SET}.log"), "w").close()
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    plans = PLANS[SET]
    for turn in range(ROUNDS):
        B.wait(F, "round", lambda: B.round_over(F), 4000)
        if B.finished(F):
            break
        slime = F1.stats(F, F1.SLIME)
        F1.put(F, slime, "<H", SLIME_HP)
        F1.put(F, slime + 0x14, "<I", F1.u32(F, slime + 0x14) | ASLEEP)
        F1.put(F, slime + 0x5D, "<B", 3)
        F1.put(F, slime + 0x80, "<B", 0)
        log(F, f"round {turn} start")
        B.choose(F)
        orders = plans[turn] if turn < len(plans) else [("defend",)] * 4
        for plan in orders:
            command(F, plan)
        if turn == 0:
            for index, field in POKES.get(SET, []):
                poke(F, index, field)
        log(F, f"round {turn} commanded")
        for n in range(0, 4000, 4):
            if B.round_over(F):
                break
            if n % 48 == 0:
                shot(F, f"r{turn:02d}")
            F.run(4)
    log(F, "end")
    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
