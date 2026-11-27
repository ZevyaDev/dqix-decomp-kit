import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "M5", "recruit_done")
PART = [("A", 120), ("A", 180), ("Down", 30), ("Down", 30), ("Down", 30), ("A", 150), ("A", 150), ("A", 150),
        ("Up", 40), ("A", 150), ("A", 150), ("A", 150), ("A", 150), ("A", 150)]
FINISH = [("Start", 90), ("A", 200), ("A", 200), ("A", 200), ("A", 200), ("A", 200), ("A", 200), ("A", 200),
          ("A", 200), ("A", 200)]


def recruit(vocation_downs):
    return [("Down", 30), ("Down", 30), ("A", 150), ("A", 150)] + [("Down", 30)] * vocation_downs + [
        ("A", 150), ("A", 150), ("A", 150), ("A", 150), ("A", 200), ("A", 200), ("A", 200), ("Right", 60),
        ("A", 200), ("A", 200)]


def shot(F, out, run, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(out, f"r{run}_f{con.frames:05d}_{tag}.png"))


def create(F, out, vocation_downs):
    import dqix_flows
    os.makedirs(out, exist_ok=True)
    run = 1
    while any(n.startswith(f"r{run}_") for n in os.listdir(out)):
        run += 1
    F.run(30)
    for _ in range(3):
        if "Patty" in F.go_npc(0, dqix_flows.NPC["Patty"]):
            break
        F.hold(0, ["Down"], 20)
        F.run(20)
    else:
        raise RuntimeError("b12M5_recruit_done: Patty did not answer")
    for key, wait in PART + recruit(vocation_downs):
        F.hold(0, [key], 3)
        F.run(wait)
    shot(F, out, run, "name")
    for n, (key, wait) in enumerate(FINISH):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(F, out, run, f"s{n:02d}{key}")


def play(F):
    create(F, OUT, 0)
