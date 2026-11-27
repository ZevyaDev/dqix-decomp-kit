import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "M1", "patty_slots")
KEYS = [("A", 120), ("A", 180), ("Down", 30), ("A", 120), ("A", 120), ("A", 120), ("A", 120), ("A", 120),
        ("A", 120), ("A", 150), ("A", 120), ("A", 120), ("A", 120), ("A", 120), ("A", 120)]
RECORDS = 0x020F384C
STRIDE = 0x964


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def log_owners(F, out, tag):
    owners = []
    for n in range(4):
        rec = RECORDS + n * STRIDE
        owners.append(f"{rec:#x}:{struct.unpack('<h', F.cons[0].read(rec + 0x568, 2))[0]}")
    out.write(f"f{F.cons[0].frames} {tag} +0x568 " + " ".join(owners) + "\n")


def play(F):
    import dqix_flows
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "owners.log"), "w") as out:
        F.run(30)
        log_owners(F, out, "start")
        for _ in range(3):
            if "Patty" in F.go_npc(0, dqix_flows.NPC["Patty"]):
                break
            F.hold(0, ["Down"], 20)
            F.run(20)
        else:
            raise RuntimeError("b11M1_patty_slots: Patty did not answer")
        shot(F, "patty")
        for n, (key, wait) in enumerate(KEYS):
            F.hold(0, [key], 3)
            F.run(wait)
            log_owners(F, out, f"{n:02d}{key}")
            shot(F, f"{n:02d}{key}")
