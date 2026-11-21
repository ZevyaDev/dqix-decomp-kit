import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Q = load("quests")
START = Q.START
QUEST_LIST = 0x0217101C
OUT = os.path.join(kitpaths.SP, "names", "dyn", "probe", "b10O4_questlist")


def text(raw):
    return raw.split(b"\0", 1)[0].decode("latin-1")


def dump(F, tag, lines):
    con = F.cons[0]
    first, second = struct.unpack("<II", con.read(QUEST_LIST, 8))
    lines.append(f"{tag} f{con.frames}: word0 {first:#010x} word1 {second:#010x}")
    if 0x02000000 <= first < 0x02400000:
        counts = struct.unpack("<4h", con.read(first + 0x48, 8))
        lines.append(f"  word0 +0x48 shorts {counts}")
    if 0x02000000 <= second < 0x02400000:
        rows = struct.unpack("<8I", con.read(second, 0x20))
        for i, row in enumerate(rows):
            shown = text(con.read(row, 0x80)) if 0x02000000 <= row < 0x02400000 else ""
            lines.append(f"  word1[{i}] {row:#010x} {shown!r}")


def snap(F, tag):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"{tag}.png"))


def play(F):
    os.makedirs(OUT, exist_ok=True)
    lines = []
    F.run(30)
    dump(F, "field", lines)
    Q.press(F, "X", 60)
    Q.press(F, "Right", 20)
    Q.press(F, "Down", 20)
    Q.press(F, "A", 200)
    for _ in range(5):
        Q.press(F, "Down", 30)
    Q.press(F, "A", 200)
    dump(F, "records", lines)
    Q.press(F, "A", 150)
    dump(F, "normal_list", lines)
    snap(F, "normal_list")
    for _ in range(9):
        Q.press(F, "Down", 40)
    dump(F, "normal_list_scrolled", lines)
    snap(F, "normal_list_scrolled")
    Q.press(F, "B", 60)
    for _ in range(4):
        Q.press(F, "B", 60)
    dump(F, "closed", lines)
    with open(os.path.join(OUT, "questlist.log"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
