import importlib.util
import os

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load("battle")
F1 = load("O1_forced")
BUFFS = load("b11M6_buffs")
START = B.START
KHEG, MELANIE, NATALIA, GARREK = 0, 1, 2, 3
SLIME_HP = 3000
ASLEEP = 0x10
ROUNDS = 18
HOLY_IMPREGNABLE = ("ability", 7, 0)
FIRE_FOURCE = ("ability", 11, 1)
FROST_FOURCE_FROM_FIRE_FOURCE = ("ability", 1, 1)
PLANS = [
    [HOLY_IMPREGNABLE, ("defend",), FIRE_FOURCE, ("defend",)],
    [("defend",), ("defend",), FROST_FOURCE_FROM_FIRE_FOURCE, ("defend",)],
]


def fresh(path):
    run, n = path, 1
    while os.path.exists(run):
        n += 1
        run = f"{path}.r{n}"
    return run


OUT = fresh(os.path.join(kitpaths.SP, "names", "b12", "M4", "fource"))


def log(F, tag):
    con = F.cons[0]
    lines = [f"{tag} f{con.frames}"]
    for index, name in ((KHEG, "kheg"), (GARREK, "garrek"), (NATALIA, "natalia"), (MELANIE, "melanie")):
        st = F1.stats(F, index)
        field = F1.u16(F, st + 0x22)
        lines.append(f"  {name} {st:#x} +0x18 {F1.u32(F, st + 0x18):#010x} +0x22 {field:#06x} "
                     f"(bits 9-11 {(field >> 9) & 7}) +0x6a {con.read(st + 0x6A, 1)[0]} "
                     f"+0x6b {con.read(st + 0x6B, 1)[0]} +0x8d {con.read(st + 0x8D, 1)[0]} "
                     f"+0x8e {con.read(st + 0x8E, 1)[0]}")
    with open(os.path.join(OUT, "fource.log"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def menu_up(F, frames):
    for _ in range(0, frames, 4):
        if B.hand(F) is not None:
            return True
        F.run(4)
    return B.hand(F) is not None


def play(F):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "fource.log"), "w").close()
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
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
        orders = PLANS[turn] if turn < len(PLANS) else [("defend",)] * 4
        for plan in orders:
            if not menu_up(F, 150):
                break
            BUFFS.command(F, plan)
        log(F, f"round {turn} commanded")
        for n in range(0, 4000, 4):
            if B.round_over(F):
                break
            if n % 60 == 0:
                shot(F, f"r{turn:02d}")
            F.run(4)
    log(F, "end")
    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
