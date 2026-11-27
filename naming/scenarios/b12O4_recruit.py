import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "O4", "recruit")
PART = [("A", 120), ("A", 180), ("Down", 30), ("Down", 30), ("Down", 30), ("A", 150), ("A", 150), ("A", 150),
        ("Up", 40), ("A", 150), ("A", 150), ("A", 150), ("A", 150), ("A", 150)]
RECRUIT = [("Down", 30), ("Down", 30), ("A", 150), ("A", 150), ("A", 150), ("A", 150), ("A", 150), ("A", 150),
           ("A", 200), ("A", 200), ("A", 200), ("Right", 60), ("A", 200), ("A", 200)]
BACK = [("B", 120), ("B", 120)]


def run_dir():
    path = OUT
    n = 2
    while os.path.exists(path):
        path = f"{OUT}.r{n}"
        n += 1
    os.makedirs(path)
    return path


def shot(F, out, tag):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(out, f"f{F.cons[0].frames:05d}_{tag}.png"))


def play(F):
    import dqix_flows
    out = run_dir()
    F.run(30)
    for _ in range(3):
        if "Patty" in F.go_npc(0, dqix_flows.NPC["Patty"]):
            break
        F.hold(0, ["Down"], 20)
        F.run(20)
    else:
        raise RuntimeError("b12O4_recruit: Patty did not answer")
    for key, wait in PART:
        F.hold(0, [key], 3)
        F.run(wait)
    for n, (key, wait) in enumerate(RECRUIT + BACK):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(F, out, f"{n:02d}{key}")
