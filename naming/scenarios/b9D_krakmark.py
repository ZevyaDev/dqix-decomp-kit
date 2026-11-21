import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

LAYOUT = 0x0238DEC0
OUT = os.path.join(kitpaths.SP, "names", "b9", "D", "krakmark")


def play(F):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "krakmark.log"), "w")

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def dump(tag):
        windows = struct.unpack("<I", con.read(LAYOUT + 0x30, 4))[0]
        count = con.read(LAYOUT + 0x39, 1)[0]
        parts = []
        if 0x02000000 <= windows < 0x02400000:
            for i in range(count):
                raw = con.read(windows + 0xE0 * i + 0xC4, 2)
                if raw[0] != 0xFF:
                    parts.append(f"id {raw[0]:#04x} +0xc5 {raw[1]:#04x}")
        log.write(f"f{con.frames} {tag}: {'; '.join(parts)}\n")
        log.flush()

    def press(key, wait, tag=None):
        F.hold(0, [key], 3)
        F.run(wait)
        if tag:
            dump(tag)
            shot(tag)

    F.run(30)
    F.move_to(0, tz=9.12)
    F.move_to(0, tx=1.74)
    F.align(0, tx=1.74)
    F.move_to(0, tz=7.92)
    F.hold(0, ["Up"], 2)
    F.run(4)
    for _ in range(5):
        press("A", 90)
    dump("categories")
    for _ in range(4):
        press("Down", 20)
    press("A", 90, "a1_items")
    press("A", 90, "a2_chosen")
    press("A", 90, "a3")
    F.run(240)
    for n in range(6):
        press("A", 90, f"b{n}")
    for n in range(10):
        press("B", 60, f"back{n}")
    F.run(120)
