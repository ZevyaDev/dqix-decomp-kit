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
F1 = load("O1_forced")
START = B.START
MELANIE = 1
TACTIC = 0
SLIME_HP = 3000
ROUNDS = 8


def set_tactic(F, index, tactic):
    data = F1.u32(F, F1.obj(F, index) + 0x150)
    F1.put(F, data + 0x94C, "<I", tactic)


def play(F):
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.wait(F, "menu", lambda: B.hand(F) is not None, 900)

    for turn in range(ROUNDS):
        F1.command_round(F, "all_defend" if turn < 2 else "all_attack")
        if turn == 0:
            set_tactic(F, MELANIE, TACTIC)
        if turn < 2:
            F1.put(F, F1.stats(F, F1.SLIME), "<H", SLIME_HP)
        F1.snap(F, f"tactic_round{turn}_commanded")
        for step in range(0, 3000, 60):
            if B.round_over(F):
                break
            F.run(60)
        if not B.round_over(F):
            F1.snap(F, f"tactic_round{turn}_stuck")
            raise RuntimeError(f"O1_tactic: no end of round {turn} after 3000 frames")
        F1.snap(F, f"tactic_round{turn}_over")
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
