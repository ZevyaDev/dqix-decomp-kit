import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
TABLE = 0x020F33D8 + 0x572C
LOG = os.path.join(kitpaths.SP, "names", "b9", "E", "b9E_skilltable_mem.log")


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(120)
    c = F.cons[0]
    entries, count = struct.unpack("<II", c.read(TABLE, 8))
    with open(LOG, "w", encoding="utf-8") as log:
        log.write(f"f{c.frames} table {TABLE:#x} entries {entries:#x} count {count:#x}\n")
        for i in range(count):
            addr = entries + 12 * i
            raw = bytes(c.read(addr, 12))
            entry_id = struct.unpack_from("<H", raw, 0)[0] & 0x7FF
            word4 = struct.unpack_from("<I", raw, 4)[0]
            bonus = ((word4 << 12) & 0xFFFFFFFF) >> 24
            log.write(f"{i} {addr:#x} id {entry_id:#x} bonus {bonus} raw {raw.hex()}\n")
