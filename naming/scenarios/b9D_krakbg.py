import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

LAYOUT = 0x0238DEC0
OUT = os.path.join(kitpaths.SP, "names", "b9", "D", "krakbg")


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "krakbg.log"), "w")

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def dump(tag):
        log.write(f"f{con.frames} {tag}\n")
        layers, windows = struct.unpack("<II", con.read(LAYOUT + 0x2C, 8))
        layer_count, window_count = con.read(LAYOUT + 0x38, 2)
        log.write(f"  layers {layers:#x} x{layer_count} windows {windows:#x} x{window_count}\n")
        if not (0x02000000 <= layers < 0x02400000 and 0x02000000 <= windows < 0x02400000):
            return
        for i in range(layer_count):
            base = layers + 0x20 * i
            raw = con.read(base, 0x20)
            screen = struct.unpack("<I", raw[0x14:0x18])[0]
            log.write(f"  layer {i} {base:#x} +0x1c {raw[0x1c]:#04x} screen {screen:#x}\n")
            if 0x02000000 <= screen < 0x02400000:
                cells = struct.unpack("<1024H", con.read(screen, 0x800))
                for row in range(24):
                    line = " ".join(f"{c:04x}" for c in cells[row * 32:row * 32 + 32])
                    log.write(f"    r{row:02d} {line}\n")
        for i in range(window_count):
            base = windows + 0xE0 * i
            raw = con.read(base, 0xE0)
            layer = struct.unpack("<I", raw[4:8])[0]
            width, height, tx, ty = struct.unpack("<hhhh", raw[0xA8:0xB0])
            rows = struct.unpack("<h", raw[0xC0:0xC2])[0]
            log.write(f"  window {i} {base:#x} id {raw[0xC4]:#04x} flags {raw[0xC5]:#04x} state {raw[0x9C]}"
                      f" layer {layer:#x} tile ({tx}, {ty}) width {width} height {height} rows {rows}\n")
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
    dump("category list")
    shot("1_list")
    for _ in range(4):
        press(F, "Down", 20)
    press(F, "A", 90)
    dump("item list")
    shot("2_items")
    for _ in range(6):
        press(F, "B", 60)
    log.close()
