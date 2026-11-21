import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

LAYOUT = 0x0238DEC0
OUT = os.path.join(kitpaths.SP, "names", "b10", "M4", "krakpage")
WATCH = (0x29, 0x37, 0x38)


def play(F):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "krakpage.log"), "w")

    def s16(a):
        return struct.unpack("<h", con.read(a, 2))[0]

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def cstr(a):
        if not 0x02000000 <= a < 0x02400000:
            return None
        return con.read(a, 48).split(b"\0")[0].decode("latin-1")

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def dump(tag):
        log.write(f"f{con.frames} dump {tag}\n")
        entries, count = u32(LAYOUT + 4), s16(LAYOUT + 8)
        if not 0x02000000 <= entries < 0x02400000:
            log.flush()
            return
        for i in range(count):
            e = entries + i * 0x30
            tid = s16(e + 4)
            if tid in WATCH:
                word = u32(e)
                log.write(f"  text {tid:#x}: +0 {word:#x} {cstr(word)!r} +0x2a {con.read(e + 0x2A, 1)[0]:#04x}\n")
        log.flush()

    def text_state():
        entries, count = u32(LAYOUT + 4), s16(LAYOUT + 8)
        if not 0x02000000 <= entries < 0x02400000:
            return None
        for i in range(count):
            e = entries + i * 0x30
            if s16(e + 4) == 0x38:
                return con.read(e + 0x2A, 1)[0], cstr(u32(entries + (i - 1) * 0x30))
        return None

    def held(key, frames, tag):
        last = text_state()
        log.write(f"f{con.frames} hold {key} start: text 0x38 +0x2a / text 0x37 {last}\n")
        con.set_keys([key])
        for _ in range(frames):
            F.run(1)
            now = text_state()
            if now != last:
                log.write(f"f{con.frames} text 0x38 +0x2a / text 0x37 {now}\n")
                last = now
        con.set_keys([])
        F.run(60)
        dump(tag)
        shot(tag)

    def press(key, wait, tag=None, frames=3):
        if frames > 3:
            held(key, frames, tag)
            return
        F.hold(0, [key], frames)
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
    for _ in range(4):
        press("Down", 20)
    press("A", 90, "page1")
    press("Right", 30, "right_column")
    press("Right", 60, "held_right", frames=60)
    press("Left", 60, "held_left", frames=60)
    press("Right", 30, "right_column2")
    press("Right", 60, "held_right2", frames=60)
    for _ in range(6):
        press("B", 60)
    F.run(60)
    log.close()
