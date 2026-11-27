import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "O4")
LIST = 0x021707C0


def run_path(stem, ext):
    path = os.path.join(OUT, f"{stem}.{ext}")
    n = 2
    while os.path.exists(path):
        path = os.path.join(OUT, f"{stem}.r{n}.{ext}")
        n += 1
    return path


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def shot(F, tag, suffix):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"wardrobe{suffix}_f{F.cons[0].frames}_{tag}.png"))


def dump(F, tag, lines):
    con = F.cons[0]
    ptr = struct.unpack("<I", con.read(LIST, 4))[0]
    lines.append(f"{tag} f{con.frames}: data_ov004_021707c0 = {ptr:#010x}")
    if 0x02000000 <= ptr < 0x02400000:
        raw = con.read(ptr, 0x7e)
        for i in range(20):
            a, b, c, d = struct.unpack("<hhBB", raw[i * 6:i * 6 + 6])
            lines.append(f"  [{i:2d}] +0 {a:3d} +2 {b:3d} +4 {c:3d} +5 {d:3d}")
        total, found = struct.unpack("<HH", raw[0x78:0x7c])
        lines.append(f"  +0x78 {total} +0x7a {found} +0x7c {raw[0x7c]}")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    log = run_path("wardrobe", "log")
    suffix = os.path.basename(log)[len("wardrobe"):-len(".log")]
    lines = []
    F.run(30)
    dump(F, "field", lines)
    press(F, "X", 60)
    press(F, "Right", 20)
    press(F, "Down", 20)
    press(F, "A", 200)
    dump(F, "records", lines)
    press(F, "Down", 30)
    press(F, "A", 200)
    dump(F, "wardrobe", lines)
    shot(F, "wardrobe", suffix)
    press(F, "Right", 60)
    dump(F, "wardrobe_right", lines)
    shot(F, "wardrobe_right", suffix)
    press(F, "B", 120)
    dump(F, "back", lines)
    press(F, "Down", 30)
    press(F, "A", 200)
    dump(F, "itemlist", lines)
    shot(F, "itemlist", suffix)
    press(F, "B", 120)
    press(F, "B", 60)
    press(F, "B", 60)
    with open(log, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
