import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
GAME_STATE = 0x020F33D8
PARTY = 0x020F5DDC
OUT = os.path.join(kitpaths.SP, "names", "b10", "R1a", "seed")
STEPS = [("X", 60), ("A", 60), ("A", 60), ("Down", 20), ("Down", 20), ("Down", 20), ("Down", 20), ("A", 60)] + \
    [("R", 30)] * 14


def play(F):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "seed.log"), "w")

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
                vocation = u32(data + 0x950)
                words = struct.unpack("<39I", con.read(data + 0x850, 13 * 12))
                fields = []
                for entry in range(13):
                    vals = []
                    for w in words[entry * 3:entry * 3 + 3]:
                        vals += [w & 0x3FF, (w >> 10) & 0x3FF, (w >> 20) & 0x3FF]
                    if any(vals):
                        fields.append((entry, vals))
                log.write(f"  object {index} data {data:#x} vocation {vocation} +0x850 nonzero {fields}\n")
        log.flush()

    F.run(30)
    dump("start")
    for n, (key, wait) in enumerate(STEPS):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(f"m{n:02d}_{key}")
    dump("end")
    log.close()
