import os

import kitpaths

START = {"save": "saves/story/018 - Ragin' Contagion.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "M8", "shots")


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"quickboot_f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
    shot(F, "after_boot")
    for i in range(6):
        F.hold(0, ["A"], 4)
        F.run(200)
        shot(F, f"a{i}")
