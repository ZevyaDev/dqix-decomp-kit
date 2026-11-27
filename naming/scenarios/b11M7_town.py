import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("town", os.path.join(os.path.dirname(__file__), "town.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

START = T.START
GAME_STATE = 0x020F33D8
LOG = os.path.join(kitpaths.SP, "names", "b11", "M7", "town_position.log")


def play(F):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    con = F.cons[0]
    log = open(LOG, "w", encoding="utf-8")

    def note():
        hero = struct.unpack("<I", con.read(GAME_STATE + 8, 4))[0]
        if 0x02000000 <= hero < 0x02400000:
            x, y, z = struct.unpack("<3i", con.read(hero + 0x44, 12))
            log.write(f"f{con.frames} hero {hero:#x} +0x44 {x} {y} {z}\n")

    for name in ("run", "hold"):
        original = getattr(F, name)

        def wrapped(*args, _original=original, **kwargs):
            result = _original(*args, **kwargs)
            note()
            return result
        setattr(F, name, wrapped)
    try:
        T.play(F)
    finally:
        log.close()
