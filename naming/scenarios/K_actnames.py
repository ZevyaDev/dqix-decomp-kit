import importlib.util
import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/field_battle.mst"}
HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = 0x02108E10
ENTRY = 0x3C
IDS = [0x1, 0x29, 0x19A, 0xE1, 0x3F, 0x40, 0x41, 0x42]


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text(con, addr):
    if not 0x02000000 <= addr < 0x02400000:
        return None
    raw = con.read(addr, 64)
    return raw.split(b"\0", 1)[0].decode("latin-1")


def dump(F, out):
    con = F.cons[0]
    out.append(f"frame {con.frames}")
    for base in (TABLES, TABLES + 0xC):
        head, entries = struct.unpack("<II", con.read(base, 8))
        count = head & 0xFFF
        out.append(f"table {base:08x} count {count} entries {entries:08x}")
        for i in range(count):
            rec = entries + i * ENTRY
            name_ptr, word = struct.unpack("<II", con.read(rec, 8))
            ident = word & 0xFFF
            if ident in IDS:
                out.append(f"  id {ident:#x} record {rec:08x} +0 {name_ptr:08x} {text(con, name_ptr)!r}")


def play(F):
    battle = load("battle")
    out = []
    for _ in range(120):
        if battle.byte(F, battle.BATTLE):
            break
        F.hold(0, ["Left"], 4)
    battle.wait(F, "battle", lambda: battle.byte(F, battle.BATTLE) != 0, 300)
    battle.wait(F, "menu", lambda: battle.hand(F) is not None, 900)
    dump(F, out)
    path = os.path.join(kitpaths.SP, "names", "b3", "K", "actnames.log")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
