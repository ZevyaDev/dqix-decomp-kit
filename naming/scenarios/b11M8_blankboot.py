import os

import kitpaths

BLANK = os.path.join(kitpaths.SP, "names", "b11", "M8", "blank.sav")
OUT = os.path.join(kitpaths.SP, "names", "b11", "M8", "shots")

if not os.path.exists(BLANK):
    os.makedirs(os.path.dirname(BLANK), exist_ok=True)
    with open(BLANK, "wb") as f:
        f.write(b"\xff" * 0x80000)

START = {"save": BLANK}


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"blankboot_f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def play(F):
    import dqix_flows
    T = dqix_flows.T
    F.run(T["power_on_to_title"])
    shot(F, "title")
    F.hold(0, ["Start"], 4)
    F.run(T["title_start_to_log_list"] + 200)
    shot(F, "after_start")
    for i in range(3):
        F.hold(0, ["A"], 4)
        F.run(200)
        shot(F, f"a{i}")
