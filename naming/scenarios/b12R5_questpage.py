import importlib.util
import os

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Q = load("quests")
START = Q.START
OUT = os.path.join(kitpaths.SP, "names", "b12", "R5", "questpage")


def run_tag():
    tag = "questpage"
    n = 1
    while os.path.exists(os.path.join(OUT, f"{tag}.log")):
        n += 1
        tag = f"questpage.r{n}"
    return tag


def snap(F, tag, log, name):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"{tag}_f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)
    log.write(f"f{F.cons[0].frames} {name} {os.path.basename(path)}\n")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    tag = run_tag()
    with open(os.path.join(OUT, f"{tag}.log"), "w", encoding="utf-8", newline="\n") as log:
        F.run(30)
        Q.press(F, "X", 60)
        Q.press(F, "Right", 20)
        Q.press(F, "Down", 20)
        Q.press(F, "A", 200)
        for _ in range(5):
            Q.press(F, "Down", 30)
        Q.press(F, "A", 200)
        Q.press(F, "A", 150)
        snap(F, tag, log, "opened")
        for n in range(2):
            Q.press(F, "Right", 60)
            snap(F, tag, log, f"right{n}")
        Q.press(F, "Left", 60)
        snap(F, tag, log, "left")
        Q.press(F, "R", 60)
        snap(F, tag, log, "r_button")
        Q.press(F, "L", 60)
        snap(F, tag, log, "l_button")
        for _ in range(4):
            Q.press(F, "B", 60)
