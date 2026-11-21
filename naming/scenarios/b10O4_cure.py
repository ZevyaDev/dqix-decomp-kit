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
MELANIE = 1
NATALIA = 2
TACTIC = 3
SLIME_HP = 3000
ROUNDS = 4
AI = 0x027E2420
LISTS = 14
OUT = os.path.join(kitpaths.SP, "names", "dyn", "probe", "b10O4_cure")


def set_tactic(F, index, tactic):
    data = F1.u32(F, F1.obj(F, index) + 0x150)
    F1.put(F, data + 0x94C, "<I", tactic)


def run_suffix():
    if not os.path.exists(os.path.join(OUT, "ai_lists.log")):
        return ""
    run = 2
    while os.path.exists(os.path.join(OUT, f"ai_lists.r{run}.log")):
        run += 1
    return f".r{run}"


SUFFIX = [""]


def snap(F, tag):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"{tag}{SUFFIX[0]}.png"))


def lists(F):
    con = F.cons[0]
    head = struct.unpack("<IhBB", con.read(AI, 8))
    raw = con.read(AI + 0x3A8, LISTS * 0x30)
    out = []
    for i in range(LISTS):
        rows = []
        for j in range(4):
            action, item, flag, score, cost, group, target = struct.unpack_from("<HbBfHBB", raw, i * 0x30 + j * 0xC)
            if action:
                rows.append(f"{action:#x}/{item}/{flag} {score:.3f} cost {cost} group {group:#x} target {target:#x}")
        if rows:
            out.append(f"  +{0x3a8 + i * 0x30:#x}: " + "; ".join(rows))
    tail = struct.unpack("<III", con.read(AI + 0x648, 12))
    return head, out, tail


def watch(F, lines, frames, turn):
    last = None
    for step in range(frames):
        F.run(1)
        if turn <= 1 and step % 20 == 0:
            snap(F, f"round{turn}_f{F.cons[0].frames:04d}")
        head, out, tail = lists(F)
        now = (head, tuple(out), tail)
        if now != last and head[1] == MELANIE:
            lines.append(f"f{F.cons[0].frames}: ai {head} +0x648 {tail[0]:#x} +0x64c {tail[1]:#x} +0x650 {tail[2]}")
            lines.extend(out)
            last = now
        if B.round_over(F):
            return


def play(F):
    os.makedirs(OUT, exist_ok=True)
    SUFFIX[0] = run_suffix()
    lines = []
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.wait(F, "menu", lambda: B.hand(F) is not None, 900)

    for turn in range(ROUNDS):
        F1.command_round(F, "all_defend")
        if turn == 0:
            set_tactic(F, MELANIE, TACTIC)
            F1.paralyse(F, NATALIA)
        F1.put(F, F1.stats(F, F1.SLIME), "<H", SLIME_HP)
        snap(F, f"round{turn}_commanded")
        lines.append(f"round {turn} commanded f{F.cons[0].frames}")
        watch(F, lines, 3000, turn)
        snap(F, f"round{turn}_over")
        if B.finished(F):
            break

    with open(os.path.join(OUT, f"ai_lists{SUFFIX[0]}.log"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    for _ in range(40):
        if B.byte(F, B.BATTLE) == 0:
            break
        if B.byte(F, B.PHASE) == B.WON:
            B.press(F, "A")
        F.run(30)
