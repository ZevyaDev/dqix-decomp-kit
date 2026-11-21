import os
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b9", "I1", "recruit_new")
PART = [("A", 120), ("A", 180), ("Down", 30), ("Down", 30), ("Down", 30), ("A", 150), ("A", 150), ("A", 150),
        ("Up", 40), ("A", 150), ("A", 150), ("A", 150), ("A", 150), ("A", 150)]
RECRUIT = [("Down", 30), ("Down", 30), ("A", 150), ("A", 150), ("A", 150), ("A", 150), ("A", 150), ("A", 150),
           ("A", 200), ("A", 200), ("A", 200), ("Right", 60), ("A", 200), ("A", 200)]


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def play(F):
    import dqix_flows
    F.run(30)
    for _ in range(3):
        if "Patty" in F.go_npc(0, dqix_flows.NPC["Patty"]):
            break
        F.hold(0, ["Down"], 20)
        F.run(20)
    else:
        raise RuntimeError("b9I1_recruit: Patty did not answer")
    shot(F, "patty")
    for n, (key, wait) in enumerate(PART):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(F, f"p{n:02d}{key}")
    for n, (key, wait) in enumerate(RECRUIT):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(F, f"r{n:02d}{key}")
