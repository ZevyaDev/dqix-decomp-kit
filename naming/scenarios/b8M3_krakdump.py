import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

LAYOUT = 0x0238DEC0
OUT = os.path.join(kitpaths.SP, "names", "b8", "M3", "krakdump")
WATCH = (2, 8, 9, 0xD)


def play(F):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "krakdump.log"), "w")

    def u8(a):
        return con.read(a, 1)[0]

    def s16(a):
        return struct.unpack("<h", con.read(a, 2))[0]

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def ram(a):
        return 0x02000000 <= a < 0x02400000

    def cstr(a):
        if not ram(a):
            return None
        return con.read(a, 48).split(b"\0")[0].decode("latin-1")

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def dump(tag):
        log.write(f"f{con.frames} dump {tag}\n")
        strlist = u32(LAYOUT)
        entries, tcount = u32(LAYOUT + 4), s16(LAYOUT + 8)
        wentries, wcount = u32(LAYOUT + 0xC), s16(LAYOUT + 0x10)
        windows, wincount = u32(LAYOUT + 0x30), u8(LAYOUT + 0x39)
        log.write(f"  layout +0 {strlist:#x} +4 {entries:#x}/{tcount} +0xc {wentries:#x}/{wcount} "
                  f"+0x30 {windows:#x} +0x39 {wincount}\n")
        if not ram(strlist) or not ram(entries) or not ram(wentries):
            log.flush()
            return
        strings = {}
        sl_entries, sl_count = u32(strlist), s16(strlist + 4)
        for i in range(max(0, min(sl_count, 0x200))):
            sid, ptr = struct.unpack("<hxxI", con.read(sl_entries + i * 8, 8))
            strings[sid] = ptr
        if ram(windows):
            for i in range(wincount):
                w = windows + i * 0xE0
                log.write(f"  window {i} at {w:#x}: +0 {u32(w):#x} +0x9c {u32(w + 0x9C)} "
                          f"+0xc4 {u8(w + 0xC4):#x} +0xc5 {u8(w + 0xC5):#x}\n")
        by_addr = {}
        texts = {}
        for i in range(tcount):
            e = entries + i * 0x30
            by_addr[e] = s16(e + 4)
            texts[s16(e + 4)] = e
        for i in range(wcount):
            we = wentries + i * 0x18
            wid = s16(we + 8)
            if wid not in WATCH:
                continue
            ids_ptr, n = u32(we), u8(we + 0x13)
            ids = [s16(ids_ptr + 2 * k) for k in range(n)] if ram(ids_ptr) else []
            log.write(f"  window entry {wid:#x} at {we:#x}: x {s16(we + 0xA)} y {s16(we + 0xC)} "
                      f"w {s16(we + 0xE)} h {s16(we + 0x10)} texts {[hex(t) for t in ids]}\n")
            for t in ids:
                e = texts.get(t)
                if e is None:
                    continue
                links = [u32(e + o) for o in (0x18, 0x1C, 0x20, 0x24)]
                link_ids = [hex(by_addr[a]) if a in by_addr else (0 if a == 0 else hex(a)) for a in links]
                sid = s16(e + 0xE)
                word = u32(e)
                log.write(f"    text {t:#x} at {e:#x}: +0 {word:#x} {cstr(word)!r} +6 {s16(e + 6)} +8 {s16(e + 8)} "
                          f"+0xe {sid:#x} {cstr(strings.get(sid, 0))!r} +0x12 {u8(e + 0x12)} "
                          f"+0x13 {u8(e + 0x13):#04x} +0x2a {u8(e + 0x2A):#04x} "
                          f"+0x18/+0x1c/+0x20/+0x24 {link_ids}\n")
        log.flush()

    def press(key, wait, tag):
        F.hold(0, [key], 3)
        F.run(wait)
        dump(tag)
        shot(tag)

    F.run(30)
    F.move_to(0, tz=9.12)
    F.move_to(0, tx=1.74)
    F.align(0, tx=1.74)
    F.move_to(0, tz=7.92)
    F.hold(0, ["Up"], 2)
    F.run(4)
    for n in range(5):
        press("A", 90, f"a{n}")
    for n in range(4):
        press("Down", 20, f"down{n}")
    for n in range(3):
        press("A", 90, f"b{n}")
    F.run(240)
    dump("wait240")
    shot("wait240")
    for n in range(6):
        press("A", 90, f"c{n}")
    for n in range(10):
        press("B", 60, f"back{n}")
    F.run(120)
    log.close()
