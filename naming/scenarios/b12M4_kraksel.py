import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
LAYOUT = 0x0238DEC0
FIRST = 0x29
LAST = 0x38


def fresh(path):
    run, n = path, 1
    while os.path.exists(run):
        n += 1
        run = f"{path}.r{n}"
    return run


OUT = fresh(os.path.join(kitpaths.SP, "names", "b12", "M4", "kraksel"))


def play(F):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "kraksel.log"), "w", encoding="utf-8", newline="\n")

    def s16(a):
        return struct.unpack("<h", con.read(a, 2))[0]

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def cstr(a):
        if not 0x02000000 <= a < 0x02400000:
            return None
        return con.read(a, 48).split(b"\0")[0].decode("latin-1")

    def entry(tid):
        entries, count = u32(LAYOUT + 4), s16(LAYOUT + 8)
        for i in range(count):
            e = entries + i * 0x30
            if s16(e + 4) == tid:
                return e
        return None

    def cursor():
        return s16(LAYOUT + 0x36)

    def state(tag):
        cur = cursor()
        e = entry(cur)
        last = entry(LAST)
        log.write(f"f{con.frames} {tag}: cursor text {cur:#x} {cstr(u32(e)) if e else None!r}; "
                  f"text 0x38 +0x2a {con.read(last + 0x2A, 1)[0]:#04x} {cstr(u32(last))!r}; "
                  f"text 0x37 {cstr(u32(entry(0x37)))!r}\n")
        log.flush()

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"f{con.frames:05d}_{name}.png"))

    def press(key, wait=24, tag=None):
        F.hold(0, [key], 3)
        F.run(wait)
        if tag:
            state(tag)
            shot(tag)

    def walk_to(target, tag):
        for _ in range(24):
            cur = cursor()
            if cur == target:
                break
            row, col = divmod(cur - FIRST, 2)
            trow, tcol = divmod(target - FIRST, 2)
            if row < trow:
                press("Down")
            elif row > trow:
                press("Up")
            elif col < tcol:
                press("Right")
            else:
                press("Left")
        state(f"{tag} at target {target:#x}")
        shot(f"{tag}_at")

    F.run(30)
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
    press("A", 90, "page1")
    walk_to(0x36, "page1")
    press("Down", 30, "page1_down")
    press("Up", 30, "page1_up")
    press("Right", 60, "flip")
    walk_to(0x36, "page2")
    press("Down", 30, "page2_down")
    press("Down", 30, "page2_down2")
    for _ in range(6):
        press("B", 60)
    F.run(60)
    log.close()
