import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
OUT = os.path.join(kitpaths.SP, "names", "b11", "O2", "spellpages")


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{F.cons[0].frames:05d}_{name}.png"))


def pages(F, who, count):
    F.run(20)
    shot(F, f"{who}_page1")
    for page in range(2, count + 1):
        B.press(F, "Right")
        F.run(20)
        shot(F, f"{who}_page{page}")


def play(F):
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.wait(F, "menu", lambda: B.round_over(F), 4000)
    B.choose(F)
    B.choose(F, ("Down", 1))
    pages(F, "kheg", 4)
    B.press(F, "B")
    F.run(30)
    B.choose(F, ("Down", 1))
    B.choose(F, ("Down", 2))
    B.choose(F, ("Down", 1))
    pages(F, "natalia", 4)
