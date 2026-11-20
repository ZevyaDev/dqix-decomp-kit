import os
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b8", "M4", "patty_add")
KEYS = [("A", 120), ("A", 180), ("Down", 30), ("A", 120), ("A", 120), ("A", 120), ("A", 120), ("A", 120),
        ("A", 120), ("A", 150), ("A", 120), ("A", 120), ("A", 120), ("A", 120), ("A", 120)]


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


RECORDS = 0x020F384C
STRIDE = 0x964


def log_records(F, tag):
    import struct
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "mem.log"), "a") as fh:
        for n in range(4):
            rec = RECORDS + n * STRIDE
            vocation = struct.unpack("<I", F.cons[0].read(rec + 0x950, 4))[0]
            taken = struct.unpack("<H", F.cons[0].read(rec + 0x954, 2))[0]
            fh.write(f"f{F.cons[0].frames} {tag} record {rec:#x} +0x950 {vocation} +0x954 {taken:#06x}\n")


def play(F):
    import dqix_flows
    F.run(30)
    log_records(F, "start")
    for _ in range(3):
        if "Patty" in F.go_npc(0, dqix_flows.NPC["Patty"]):
            break
        F.hold(0, ["Down"], 20)
        F.run(20)
    else:
        raise RuntimeError("b8M4_patty_add: Patty did not answer")
    shot(F, "patty")
    for n, (key, wait) in enumerate(KEYS):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(F, f"{n:02d}{key}")
    log_records(F, "end")
