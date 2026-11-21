import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "M4", "touchrects")
MANAGER = 0x02389A74


def play(F):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "touchrects.log"), "w")

    def u8(a):
        return con.read(a, 1)[0]

    def s16(a):
        return struct.unpack("<h", con.read(a, 2))[0]

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def dump(tag):
        cursor_id = u8(MANAGER + 0xB0)
        windows, capacity, opened = u32(MANAGER + 0x9C), u8(MANAGER + 0xB3), u8(MANAGER + 0xB4)
        log.write(f"f{con.frames} dump {tag}: cursorWindowId {cursor_id:#x} windows {windows:#x} "
                  f"capacity {capacity} open {opened}\n")
        cursor_window = None
        if 0x02000000 <= windows < 0x02400000:
            for i in range(min(capacity, opened)):
                w = windows + i * 0xE0
                if u8(w + 0xC4) == cursor_id:
                    cursor_window = w
                    break
        if cursor_window is not None:
            w = cursor_window
            log.write(f"  cursor window {w:#x}: tileX {s16(w + 0xAC)} tileY {s16(w + 0xAE)} "
                      f"entryXs {w + 0xC:#x} entryYs {w + 0x30:#x} entryWidths {w + 0x54:#x} "
                      f"entryHeights {w + 0x78:#x}\n")
        log.write(f"  manager +0x38 {u32(MANAGER + 0x38)} +0x3c {s16(MANAGER + 0x3C)} +0x3e {s16(MANAGER + 0x3E)} "
                  f"+0x40 {u32(MANAGER + 0x40):#x} +0x44 {u32(MANAGER + 0x44):#x} "
                  f"+0x48 {u32(MANAGER + 0x48):#x} +0x4c {u32(MANAGER + 0x4C):#x}\n")
        log.flush()

    def press(key, wait, tag):
        F.hold(0, [key], 3)
        F.run(wait)
        dump(tag)
        shot(tag)

    F.run(30)
    dump("start")
    press("X", 120, "menu")
    press("A", 120, "items")
    press("A", 120, "member")
    for n in range(4):
        press("B", 40, f"back{n}")
    F.run(60)
    log.close()
