import os

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/field_battle.mst"}
GAME_STATE = 0x020F33D8
RECORDS = GAME_STATE + 0x474
RECORD_SIZE = 0x964
LEARNED = 0x8EC
SKILL = 0x106
LOG = os.path.join(kitpaths.SP, "names", "b9", "F", "b9F_skillbits.log")


def play(F):
    F.run(30)
    con = F.cons[0]
    with open(LOG, "w", encoding="utf-8") as log:
        for n in range(4):
            record = RECORDS + n * RECORD_SIZE
            bits = con.read(record + LEARNED, 0x24)
            name = con.read(record + 0x4, 0x10).split(b"\0")[0]
            log.write(f"record {n} {record:#x} name? {name!r} learned {bits.hex()} "
                      f"skill {SKILL:#x}: {(bits[SKILL // 8] >> (SKILL % 8)) & 1}\n")
