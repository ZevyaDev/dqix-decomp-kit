import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
GAME_STATE = 0x020F33D8
BAG = 0x020F5DDC
FLAGS = 0x02108844 + 0x8C
OUT = os.path.join(kitpaths.SP, "names", "b9", "D", "dqvc")
STEPS = [
    ("A", 90), ("A", 90), ("A", 90), ("A", 90), ("Down", 30), ("A", 150), ("A", 120),
    ("A", 120), ("A", 120), ("A", 120), ("A", 120), ("A", 120), ("A", 120),
    ("Down", 40), ("Down", 40), ("Down", 40), ("Down", 40), ("A", 120), ("A", 120), ("A", 120),
    ("A", 120), ("A", 120), ("A", 120), ("A", 120), ("A", 120),
]


def play(F):
    from PIL import Image
    import dqix_flows
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "dqvc.log"), "w")

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def dump(tag):
        log.write(f"f{con.frames} {tag}\n")
        for index in range(4):
            obj = u32(GAME_STATE + 8 + 4 * index)
            data = u32(obj + 0x150) if 0x02000000 <= obj < 0x02400000 else 0
            if 0x02000000 <= data < 0x02400000:
                held = struct.unpack("<8h", con.read(data + 0x454, 16))
                log.write(f"  object {index} {obj:#x} data {data:#x} +0x454 {[hex(h & 0xFFFF) for h in held]}\n")
        ids = struct.unpack("<152h", con.read(BAG + 0xC, 304))
        counts = struct.unpack("<152b", con.read(BAG + 0x13C, 152))
        bag = [f"{i & 0xFFFF:#x}:{c}" for i, c in zip(ids, counts) if i >= 0]
        log.write(f"  bag {len(bag)} {' '.join(bag)}\n")
        log.write(f"  flags {con.read(FLAGS, 0x234).hex()}\n")
        log.flush()

    F.run(30)
    dump("start")
    if "Sellma" not in F.go_npc(0, dqix_flows.NPC["Sellma"]):
        raise RuntimeError("b9D_dqvc: Sellma did not answer")
    F.run(60)
    for n, (key, wait) in enumerate(STEPS):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(f"s{n:02d}_{key}")
    dump("end")
    log.close()
