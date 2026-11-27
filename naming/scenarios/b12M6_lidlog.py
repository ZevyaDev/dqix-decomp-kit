import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
STATE = 0x021117EC
VBLANK_COUNT = 0x027FFC3C
OUT = os.path.join(kitpaths.SP, "names", "b12", "M6")


def dump(F, tag, lines):
    con = F.cons[0]
    words = struct.unpack("<12I", con.read(STATE, 0x30))
    count = struct.unpack("<I", con.read(VBLANK_COUNT, 4))[0]
    lines.append(f"{tag} f{con.frames} vblank {count}: " + " ".join(f"{w:08x}" for w in words))


def log_path():
    path = os.path.join(OUT, "lidlog.log")
    n = 2
    while os.path.exists(path):
        path = os.path.join(OUT, f"lidlog.r{n}.log")
        n += 1
    return path


def play(F):
    lines = []
    F.run(58)
    dump(F, "open", lines)
    F.cons[0].set_lid(True)
    for _ in range(6):
        F.run(1)
        dump(F, "closing", lines)
    F.run(290)
    dump(F, "closed", lines)
    F.cons[0].set_lid(False)
    for _ in range(6):
        F.run(1)
        dump(F, "opening", lines)
    F.run(300)
    dump(F, "open again", lines)
    with open(log_path(), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
