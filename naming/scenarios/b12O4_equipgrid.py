import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "O4")
EQUIP_MENU_UI = 0x023531E4
CELLS = 0x2D90
CELL_SIZE = 0x1C
TAB = 0x3DBC
TAB_CATEGORIES = 0x0215CD60
BAG = 0x020F5FB0


def run_stem():
    stem = os.path.join(OUT, "equipgrid")
    n = 2
    while os.path.exists(stem + ".log"):
        stem = os.path.join(OUT, f"equipgrid.r{n}")
        n += 1
    return stem


def u32(con, addr):
    return struct.unpack("<I", con.read(addr, 4))[0]


def dump(F, stem, tag, lines):
    from PIL import Image
    con = F.cons[0]
    tab, page = struct.unpack("<Bb", con.read(EQUIP_MENU_UI + TAB, 2))
    cells = []
    for i in range(8, 24):
        item, count = struct.unpack("<hb", con.read(EQUIP_MENU_UI + CELLS + i * CELL_SIZE, 3))
        cells.append(f"{item & 0xffff:#06x}x{count}")
    lines.append(f"f{con.frames} {tag}: +0x3dbc {tab} +0x3dbd {page}")
    lines.append(f"  cells[8..23] {' '.join(cells)}")
    if tab < 8 and 0 <= page < 16:
        category = con.read(TAB_CATEGORIES + tab, 1)[0]
        ids = u32(con, BAG + 0xBD0 + category * 4)
        counts = u32(con, BAG + 0xBF0 + category * 4)
        if 0x02000000 <= ids < 0x02400000 and 0x02000000 <= counts < 0x02400000:
            raw_ids = struct.unpack("<16h", con.read(ids + page * 32, 32))
            raw_counts = struct.unpack("<16b", con.read(counts + page * 16, 16))
            bag = " ".join(f"{a & 0xffff:#06x}x{b}" for a, b in zip(raw_ids, raw_counts))
            lines.append(f"  bag category {category} page {page} {bag}")
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        f"{stem}_f{con.frames}_{tag}.png")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    stem = run_stem()
    lines = []
    steps = [("X", 40), ("Down", 15), ("A", 90), ("A", 90), ("A", 90), ("Down", 20), ("A", 120), ("A", 120),
             ("A", 120), ("B", 40), ("B", 40), ("B", 40), ("B", 40)]
    F.run(30)
    for n, (key, wait) in enumerate(steps):
        F.hold(0, [key], 3)
        F.run(wait)
        dump(F, stem, f"{n:02d}{key}", lines)
    with open(stem + ".log", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
