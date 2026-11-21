import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
GAME_STATE = 0x020F33D8
RECORDS = GAME_STATE + 0x474
STRIDE = 0x964
LOG = os.path.join(kitpaths.SP, "names", "b9", "E", "b9E_stats_mem.log")


def dump(F, log, tag):
    c = F.cons[0]
    for n in range(8):
        record = RECORDS + n * STRIDE
        bits = c.read(record + 0x8EC, 0x24)
        vocation = struct.unpack("<I", c.read(record + 0x950, 4))[0]
        learned = [i for i in range(0x24 * 8) if bits[i // 8] & (1 << (i % 8))]
        log.write(f"f{c.frames} {tag} record {record:#x} vocation {vocation} learned {[hex(i) for i in learned]}\n")


def play(F):
    import dqix_flows
    with open(LOG, "w", encoding="utf-8") as log:
        dqix_flows.boot_all(F)
        dump(F, log, "boot")
        dqix_flows.leave_church(F, 0)
        dqix_flows.church_to_inn(F, 0)
        dump(F, log, "inn")
