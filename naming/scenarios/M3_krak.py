import struct

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

LAYOUT = 0x0238DEC0
OUT = "D:/Downloads/decomp/dqix-sp/names/b7/M3/krak"


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    import os
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "krak.log"), "w")

    def u16(a):
        return struct.unpack("<H", con.read(a, 2))[0]

    def s16(a):
        return struct.unpack("<h", con.read(a, 2))[0]

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def text(a):
        raw = con.read(a, 64)
        return raw.split(b"\0")[0].decode("latin-1")

    def dump():
        layers = u32(LAYOUT + 0x2C)
        count = con.read(LAYOUT + 0x38, 1)[0]
        log.write(f"f{con.frames} layout +0x2c = {layers:#x}, +0x38 = {count}\n")
        for i in range(count):
            a = layers + i * 0x20
            log.write(f"  layer {a:#x}: +0x14 = {u32(a + 0x14):#x}, +0x1c = {con.read(a + 0x1C, 1)[0]:#04x}\n")
        entries, tcount = u32(LAYOUT + 4), s16(LAYOUT + 8)
        strlist = u32(LAYOUT)
        sl_entries, sl_count = u32(strlist), s16(strlist + 4)
        strings = {}
        for i in range(sl_count):
            sid, ptr = struct.unpack("<hxxI", con.read(sl_entries + i * 8, 8))
            strings[sid] = ptr
        log.write(f"  string list {strlist:#x}: {sl_count} entries at {sl_entries:#x}\n")
        for i in range(tcount):
            e = entries + i * 0x30
            tid = s16(e + 4)
            if tid in (0x56, 0x57, 0x58):
                sid = s16(e + 0xE)
                s = text(strings[sid]) if sid in strings else None
                log.write(f"  text {tid:#x} at {e:#x}: +0xe = {sid:#x} -> {s!r}, +0x2a = {con.read(e + 0x2A, 1)[0]:#04x}\n")
        for sid in (0x2B, 0x2C, 0x2E):
            if sid in strings:
                log.write(f"  string {sid:#x} = {text(strings[sid])!r}\n")
        wentries, wcount = u32(LAYOUT + 0xC), s16(LAYOUT + 0x10)
        for i in range(wcount):
            e = wentries + i * 0x18
            wid = s16(e + 8)
            if wid in (0, 1, 0xD):
                x, y, w, h = struct.unpack("<4h", con.read(e + 0xA, 8))
                log.write(f"  window entry {wid:#x} at {e:#x}: x {x} y {y} w {w} h {h}, +0x15 = {con.read(e + 0x15, 1)[0]:#04x}\n")
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
    F.run(30)
    dump()
    shot("1_list")
    log.write(f"f{con.frames} hold Down 80 frames\n")
    F.hold(0, ["Down"], 80)
    F.run(30)
    shot("2_held_down")
    log.write(f"f{con.frames} touch (110, 92)\n")
    con.touch(110, 92)
    F.run(6)
    con.touch()
    F.run(60)
    shot("3_touch_inside")
    log.write(f"f{con.frames} touch (20, 150)\n")
    con.touch(20, 150)
    F.run(6)
    con.touch()
    F.run(90)
    shot("4_touch_outside")
    for _ in range(6):
        press(F, "B", 60)
    log.close()
