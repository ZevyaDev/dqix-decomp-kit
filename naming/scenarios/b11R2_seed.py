import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
GAME_STATE = 0x020F33D8
OUT = os.path.join(kitpaths.SP, "names", "b11", "R2", "seed")


def fields(words):
    out = []
    for w in words:
        out += [w & 0x3FF, (w >> 10) & 0x3FF, (w >> 20) & 0x3FF]
    return out


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
            os.path.join(OUT, f"f{con.frames:05d}_{name}.png"))

    def tap(key, wait, name):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(name)

    def dump(tag):
        log.write(f"f{con.frames} {tag}\n")
        for index in range(4):
            obj = u32(GAME_STATE + 8 + 4 * index)
            data = u32(obj + 0x150) if 0x02000000 <= obj < 0x02400000 else 0
            if not 0x02000000 <= data < 0x02400000:
                continue
            vocation = u32(data + 0x950)
            entries = struct.unpack("<39I", con.read(data + 0x850, 13 * 12))
            nonzero = [(e, fields(entries[e * 3:e * 3 + 3])) for e in range(13) if any(entries[e * 3:e * 3 + 3])]
            stats = fields(struct.unpack("<3I", con.read(data, 12)))
            level = fields(struct.unpack("<3I", con.read(data + 0x91C, 12)))
            log.write(f"  object {index} data {data:#x} vocation {vocation} stats {stats} "
                      f"levelStats {level} +0x850 nonzero {nonzero}\n")
        log.flush()

    F.run(30)
    dump("start")
    tap("X", 60, "menu")
    tap("A", 120, "items")
    tap("A", 180, "everyday")
    for n in range(5):
        tap("Down", 30, f"down{n}")
    F.run(120)
    tap("A", 120, "bag_a1")
    tap("A", 120, "bag_a2")
    for n in range(9):
        tap("Right", 40, f"page{n + 2:02d}")
    tap("A", 90, "item_menu")
    tap("A", 120, "use")
    dump("before_target")
    tap("A", 120, "target")
    for n in range(4):
        tap("A", 90, f"msg{n}")
    dump("after")
    for n in range(4):
        tap("B", 60, f"back{n}")
    dump("end")
    log.close()
