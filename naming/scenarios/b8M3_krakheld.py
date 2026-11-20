import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

GAME_STATE = 0x020F33D8
OUT = os.path.join(kitpaths.SP, "names", "b8", "M3", "krakheld")


def play(F):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "krakheld.log"), "w")

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
        log.flush()

    def press(key, wait, tag=None):
        F.hold(0, [key], 3)
        F.run(wait)
        if tag:
            dump(tag)
            shot(tag)

    F.run(30)
    dump("start")
    F.move_to(0, tz=9.12)
    F.move_to(0, tx=1.74)
    F.align(0, tx=1.74)
    F.move_to(0, tz=7.92)
    F.hold(0, ["Up"], 2)
    F.run(4)
    for _ in range(5):
        press("A", 90)
    for _ in range(4):
        press("Down", 20)
    press("A", 90)
    press("A", 90)
    press("A", 90)
    F.run(240)
    for n in range(6):
        press("A", 90, f"a{n}")
    for _ in range(10):
        press("B", 60)
    F.run(120)
    for _ in range(4):
        press("B", 60)
    F.run(120)
    dump("field")
    press("X", 60, "menu")
    press("A", 90, "items")
    press("A", 90, "everyday")
    press("Down", 30, "items_down1")
    press("Down", 30, "items_down2")
    press("Down", 30, "items_down3")
    for _ in range(5):
        press("B", 30)
    log.close()
