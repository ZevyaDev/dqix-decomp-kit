import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "M3")
NPC_MANAGER = 0x021075F4
MESSAGE_WINDOW = 0x021152F4
SOUND_EFFECTS = 0x02108760


def words(con, addr, n):
    return struct.unpack(f"<{n}I", bytes(con.read(addr, 4 * n)))


def sprite_cache(con):
    count, flags, entries = words(con, NPC_MANAGER, 3)
    loads, no_share = flags & 0xFF, (flags >> 8) & 0xFF
    out = [f"cache count {count} loads(+4) {loads} noShare(+5) {no_share} entries(+8) {entries:#x}"]
    if entries and count <= 32:
        for i in range(count):
            raw = bytes(con.read(entries + i * 0x3C, 0x3C))
            refs = struct.unpack("<i", raw[0x38:0x3C])[0]
            if refs >= 0:
                name = raw[:0x10].split(b"\0", 1)[0].decode("ascii", "replace")
                out.append(f"[{i}] {name} refs {refs}")
    return " ".join(out)


def npc_state(con):
    slots = sum(1 for w in words(con, NPC_MANAGER + 0xC, 32) if w)
    count = words(con, NPC_MANAGER + 0x8C, 1)[0]
    saved_zone, saved_count = struct.unpack("<HH", bytes(con.read(NPC_MANAGER + 0x1DE, 4)))
    mask = words(con, NPC_MANAGER + 0x1E4, 1)[0]
    records = sum(1 for b in bytes(con.read(NPC_MANAGER + 0x9E, 0x140)) if b)
    return (f"npcSlots {slots} npcCount(+0x8c) {count} savedZone(+0x1de) {saved_zone:#x} "
            f"savedCount(+0x1e0) {saved_count} mask(+0x1e4) {mask:#x} savedRecordBytesNonzero {records}")


def message_state(con):
    w = MESSAGE_WINDOW
    target, = words(con, w + 0x38, 1)
    is_open, = words(con, w + 0x998, 1)
    task, allocator, sprite_set, sprites, anim_list = struct.unpack("<iIIII", bytes(con.read(w + 0x2D0, 20)))
    sprite_id, = struct.unpack("<H", bytes(con.read(w + 0x2E4, 2)))
    b6, b7 = bytes(con.read(w + 0x2E6, 2))
    frame_alloc, = words(con, w + 0x19E0 + 0x444, 1)
    return (f"msg+0x38 {target:#x} +0x998 {is_open} task(+0x2d0) {task} alloc(+0x2d4) {allocator:#x} "
            f"set(+0x2d8) {sprite_set:#x} sprites(+0x2dc) {sprites:#x} list(+0x2e0) {anim_list:#x} "
            f"+0x2e4 {sprite_id} +0x2e6 {b6} state(+0x2e7) {b7} frameAlloc(+0x1e24) {frame_alloc:#x}")


def sound_state(con):
    heap, = words(con, SOUND_EFFECTS, 1)
    loaded, = struct.unpack("<h", bytes(con.read(SOUND_EFFECTS + 0xB4, 2)))
    return f"se heap(+0) {heap:#x} loadedSet(+0xb4) {loaded}"


def play(F):
    import dqix_flows
    con = F.cons[0]
    logs = {"cache": [], "npc": [], "msg": [], "se": []}
    probes = {"cache": sprite_cache, "npc": npc_state, "msg": message_state, "se": sound_state}
    last = {k: None for k in logs}
    original = F.run

    def run(frames):
        for _ in range(frames):
            original(1)
            for key, fn in probes.items():
                now = fn(con)
                if now != last[key]:
                    logs[key].append(f"f{con.frames} {now}")
                    last[key] = now

    F.run = run
    try:
        dqix_flows.boot_all(F)
        dqix_flows.leave_church(F, 0)
        dqix_flows.church_to_inn(F, 0)
    finally:
        F.run = original
        os.makedirs(OUT, exist_ok=True)
        for key, lines in logs.items():
            base = os.path.join(OUT, f"townlog_{key}")
            path, run_no = f"{base}.log", 2
            while os.path.exists(path):
                path, run_no = f"{base}.r{run_no}.log", run_no + 1
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(lines) + "\n")
