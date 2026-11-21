import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "M5", "dropoff")
PARTY = 0x020F5DDC
KEYS = [("A", 120), ("A", 180), ("Down", 30), ("A", 150), ("A", 150), ("A", 150), ("A", 150), ("A", 150),
        ("A", 150), ("A", 150), ("A", 150), ("A", 150)]


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def log_party(F, tag):
    con = F.cons[0]
    members = con.read(PARTY + 0xF78, 5)
    stored = con.read(PARTY + 0x2C8C, 1)[0]
    ids = [con.read(PARTY + 0xF80 + n * 0x23C, 1)[0] for n in range(stored)]
    names = [con.read(PARTY + 0xF80 + n * 0x23C + 2, 13).split(b"\0")[0] for n in range(stored)]
    with open(os.path.join(OUT, "party.log"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"f{con.frames} {tag} members={list(members[:members[4]])} stored={stored} "
                 f"first_bytes={[hex(b) for b in ids]} names={names}\n")


def play(F):
    import dqix_flows
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "party.log"), "w").close()
    F.run(30)
    log_party(F, "start")
    for _ in range(3):
        if "Patty" in F.go_npc(0, dqix_flows.NPC["Patty"]):
            break
        F.hold(0, ["Down"], 20)
        F.run(20)
    else:
        raise RuntimeError("b10M5_dropoff: Patty did not answer")
    shot(F, "patty")
    for n, (key, wait) in enumerate(KEYS):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(F, f"{n:02d}{key}")
        log_party(F, f"{n:02d}{key}")
