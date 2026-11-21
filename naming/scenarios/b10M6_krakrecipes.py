import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("C5_krakpot", os.path.join(os.path.dirname(__file__), "C5_krakpot.py"))
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)

START = K.START
GAME_STATE = 0x020F33D8
TABLE = GAME_STATE + 0x7AC4
ENTRIES = 0x1D7
LOG = os.path.join(kitpaths.SP, "names", "b10", "M6", "b10M6_krakrecipes_mem.log")


def table(F):
    raw = F.cons[0].read(TABLE, 2 * ENTRIES)
    return struct.unpack(f"<{ENTRIES}H", raw)


def describe(words):
    used = [(i, w) for i, w in enumerate(words) if w >> 2]
    return used


def play(F):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    before = table(F)
    K.play(F)
    after = table(F)
    with open(LOG, "w", encoding="utf-8") as log:
        used = describe(before)
        log.write(f"f0 table {TABLE:#x}: {len(used)} used entries before\n")
        for i, w in used:
            log.write(f"  before [{i}] {w:#06x} id {w >> 2:#x} bit1 {(w >> 1) & 1} bit0 {w & 1}\n")
        log.write(f"f{F.cons[0].frames} after: {len(describe(after))} used entries\n")
        for i, (a, b) in enumerate(zip(before, after)):
            if a != b:
                log.write(f"  changed [{i}] {a:#06x} -> {b:#06x} id {b >> 2:#x} bit1 {(b >> 1) & 1} bit0 {b & 1}\n")
