import struct

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

LAYOUT = 0x0238DEC0
OUT = "D:/Downloads/decomp/dqix-sp/names/b6/N3/kraktouch"


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    import os
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "highlight.log"), "w")
    last = [None]

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def lit():
        entries, count = struct.unpack("<IH", con.read(LAYOUT + 4, 6))
        if not (0x02000000 <= entries < 0x02400000) or count > 0x200:
            return None
        raw = con.read(entries, count * 0x30)
        ids = []
        for i in range(count):
            e = raw[i * 0x30:(i + 1) * 0x30]
            if e[0x2A] & 4:
                ids.append(hex(struct.unpack("<h", e[4:6])[0]))
        return tuple(ids)

    def watch(n):
        for _ in range(n):
            F.run(1)
            s = lit()
            if s != last[0]:
                log.write(f"f{con.frames} text ids with +0x2a bit 4: {list(s) if s is not None else 'no layout'}\n")
                last[0] = s
        log.flush()

    F.run(30)
    F.move_to(0, tz=9.12)
    F.move_to(0, tx=1.74)
    F.align(0, tx=1.74)
    F.move_to(0, tz=7.92)
    F.hold(0, ["Up"], 2)
    F.run(4)
    for _ in range(5):
        press(F, "A", 90)
    watch(30)
    shot("1_list")
    log.write(f"f{con.frames} touch (110, 92)\n")
    con.touch(110, 92)
    watch(6)
    con.touch()
    watch(60)
    shot("2_touched")
    log.write(f"f{con.frames} press Down\n")
    F.hold(0, ["Down"], 3)
    watch(60)
    shot("3_down")
    for _ in range(6):
        press(F, "B", 60)
    log.close()
