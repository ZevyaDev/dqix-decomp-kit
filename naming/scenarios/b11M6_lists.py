import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
OUT = os.path.join(kitpaths.SP, "names", "b11", "M6", "lists")
SPELL_PAGES = 6
ABILITY_PAGES = 16


def shot(F, tag):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"{tag}.png"))


def tap(F, key, settle=20):
    F.hold(0, [key], 3)
    F.run(settle)


def pages(F, tag, count):
    for _ in range(60):
        if B.hand(F) is not None:
            break
        F.run(2)
    else:
        shot(F, f"{tag}_none")
        return
    F.run(10)
    for n in range(count):
        shot(F, f"{tag}_p{n:02d}")
        tap(F, "Right")


def back_to_member_menu(F):
    for _ in range(4):
        tap(F, "B", 30)
        if B.hand(F) is not None:
            break
    B.wait(F, "member menu", lambda: B.hand(F) is not None, 120, 2)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    for _ in range(120):
        if B.byte(F, B.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
    B.choose(F)
    B.choose(F, ("Down", 2))
    for member in ("garrek", "natalia", "melanie"):
        B.wait(F, "member menu", lambda: B.hand(F) is not None, 300, 2)
        F.run(10)
        shot(F, f"{member}_menu")
        tap(F, "Down")
        tap(F, "A", 30)
        pages(F, f"{member}_spells", SPELL_PAGES)
        back_to_member_menu(F)
        tap(F, "Up")
        tap(F, "Right")
        tap(F, "A", 30)
        pages(F, f"{member}_abilities", ABILITY_PAGES)
        back_to_member_menu(F)
        tap(F, "Left")
        tap(F, "Down")
        shot(F, f"{member}_before_defend")
        tap(F, "Down")
        tap(F, "A", 30)
    B.wait(F, "end of round", lambda: B.round_over(F), 4000)
    shot(F, "round_over")
