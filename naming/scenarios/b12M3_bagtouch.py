import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "M3", "bagtouch")
MANAGER = 0x02389A74


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"f{F.cons[0].frames:05d}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def manager_state(con):
    raw = bytes(con.read(MANAGER, 0xB8))
    windows, = struct.unpack("<I", raw[0x9C:0xA0])
    count = raw[0xB4]
    touch = raw[0x50:0x53].hex()
    pages = struct.unpack("<ii", raw[0x8:0xC] + raw[0x58:0x5C])
    out = [f"windows(+0x9c) {windows:#x} count(+0xb4) {count} touch+0x4c..0x4e {touch} pages {pages}"]
    if windows and count <= 16:
        for i in range(count):
            w = bytes(con.read(windows + i * 0xE0, 0xE0))
            width, height, x, y = struct.unpack("<4h", w[0xA8:0xB0])
            out.append(f"[{i} @{windows + i * 0xE0:#x} id {w[0xC4]} x {x} y {y} w {width} h {height}]")
    return " ".join(out)


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def touch(F, x, y, wait, name):
    F.cons[0].touch(x, y)
    F.run(4)
    shot(F, f"{name}_held")
    F.cons[0].touch()
    F.run(wait)
    shot(F, name)


def play(F):
    con = F.cons[0]
    lines, last = [], [None]
    original = F.run

    def run(frames):
        for _ in range(frames):
            original(1)
            now = manager_state(con)
            if now != last[0]:
                lines.append(f"f{con.frames} {now}")
                last[0] = now

    F.run = run
    try:
        F.run(30)
        tap(F, "X", 60)
        tap(F, "A", 120)
        tap(F, "A", 180)
        for _ in range(5):
            tap(F, "Down", 30)
        F.run(90)
        shot(F, "bag_cursor")
        touch(F, 40, 172, 90, "touch_empty")
        touch(F, 210, 162, 150, "touch_sort")
        for _ in range(4):
            tap(F, "B", 40)
    finally:
        F.run = original
        os.makedirs(OUT, exist_ok=True)
        path, run_no = os.path.join(OUT, "manager.log"), 2
        while os.path.exists(path):
            path, run_no = os.path.join(OUT, f"manager.r{run_no}.log"), run_no + 1
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
