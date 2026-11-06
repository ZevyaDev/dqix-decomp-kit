import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load("battle")
START = B.START
DEFEND_ROUNDS = 3


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
