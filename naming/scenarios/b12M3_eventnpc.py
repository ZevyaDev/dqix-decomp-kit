import os
import struct

import kitpaths

START = {"save": "saves/story/033 - Tyrantula.sav", "state": "states/event.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "M3")
NPC_MANAGER = 0x021075F4
SLOT_SET = 0x01FFD348
SLOTS = 0x01FFD364
EVENT_OVERLAY = 1


def words(con, addr, n):
    return struct.unpack(f"<{n}I", bytes(con.read(addr, 4 * n)))


def npc_state(con):
    slots = sum(1 for w in words(con, NPC_MANAGER + 0xC, 32) if w)
    count, = words(con, NPC_MANAGER + 0x8C, 1)
    cache_count, flags, entries = words(con, NPC_MANAGER, 3)
    saved_zone, saved_count = struct.unpack("<HH", bytes(con.read(NPC_MANAGER + 0x1DE, 4)))
    mask, = words(con, NPC_MANAGER + 0x1E4, 1)
    records = bytes(con.read(NPC_MANAGER + 0x9E, 0x140))
    first = struct.unpack("<4hH", records[:10])
    return (f"cache(+0 {cache_count} +4 {flags & 0xFF} +8 {entries:#x}) npcSlots {slots} npcCount(+0x8c) {count} "
            f"savedZone(+0x1de) {saved_zone:#x} savedCount(+0x1e0) {saved_count} mask(+0x1e4) {mask:#x} "
            f"savedRecordBytesNonzero {sum(1 for b in records if b)} record0 {first}")


def slot0(con):
    k, = words(con, SLOT_SET, 1)
    return con.read(SLOTS + 6 * k, 1)[0]


def play(F):
    con = F.cons[0]
    lines, last = [], [None]
    original = F.run

    def run(frames):
        for _ in range(frames):
            original(1)
            now = npc_state(con)
            if now != last[0]:
                lines.append(f"f{con.frames} ov{slot0(con):03d} {now}")
                last[0] = now

    F.run = run
    try:
        F.hold(0, ["A"], 4)
        for _ in range(30):
            if slot0(con) == EVENT_OVERLAY:
                break
            F.run(4)
        for _ in range(80):
            F.run(56)
            if slot0(con) != EVENT_OVERLAY:
                break
            F.hold(0, ["A"], 4)
        F.run(120)
    finally:
        F.run = original
        os.makedirs(OUT, exist_ok=True)
        path, run_no = os.path.join(OUT, "eventnpc.log"), 2
        while os.path.exists(path):
            path, run_no = os.path.join(OUT, f"eventnpc.r{run_no}.log"), run_no + 1
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
