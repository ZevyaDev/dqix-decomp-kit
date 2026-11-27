import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
LOG = os.path.join(kitpaths.SP, "names", "b11", "M3", "npcstate.log")
NPC_MANAGER = 0x021075F4
ZONE3D = 0x020FB3F0


def words(F, addr, n):
    return struct.unpack(f"<{n}I", F.cons[0].read(addr, 4 * n))


def dump(F, tag, out):
    con = F.cons[0]
    count = words(F, NPC_MANAGER + 0x8C, 1)[0]
    slots = words(F, NPC_MANAGER + 0xC, 32)
    zone = struct.unpack("<H", con.read(ZONE3D, 2))[0]
    saved_zone, saved_count = struct.unpack("<HH", con.read(NPC_MANAGER + 0x1DE, 4))
    mask = words(F, NPC_MANAGER + 0x1E4, 1)[0]
    out.write(f"{tag}: f{con.frames} zone3D.currentZoneID {zone:#x} npcCount(+0x8c) {count} "
              f"savedZone(+0x1de) {saved_zone:#x} savedCount(+0x1e0) {saved_count} mask(+0x1e4) {mask:#x}\n")
    for i, npc in enumerate(slots):
        if npc == 0:
            continue
        flags, _, data, placement, _, sprite, model, other = words(F, npc, 8)
        npc_id = struct.unpack("<H", con.read(data, 2))[0] if data else -1
        pos = struct.unpack("<3i", con.read(sprite + 4, 12)) if sprite else None
        rec = con.read(NPC_MANAGER + 0x9E + 10 * i, 10)
        sx, sy, sz, angle, bits = struct.unpack("<4hH", rec)
        out.write(f"  slot {i} npc {npc:#x} flags {flags:#x} id {npc_id:#x} +0x14 {sprite:#x} +0x18 {model:#x} "
                  f"+0x1c {other:#x} position {pos} | saved +0x9e[{i}] x {sx} y {sy} z {sz} angle {angle} "
                  f"id {bits & 0x1ff:#x} bit9 {(bits >> 9) & 1} bits10_14 {(bits >> 10) & 0x1f} bit15 {bits >> 15}\n")
    out.flush()


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w") as out:
        F.run(30)
        dump(F, "start", out)
        F.move_to(0, tz=9.12)
        F.move_to(0, tx=1.74)
        F.align(0, tx=1.74)
        F.move_to(0, tz=7.92)
        F.hold(0, ["Up"], 2)
        F.run(4)
        dump(F, "before_talk", out)
        for _ in range(5):
            press(F, "A", 90)
        for _ in range(4):
            press(F, "Down", 20)
        press(F, "A", 90)
        press(F, "A", 90)
        press(F, "A", 90)
        dump(F, "pot_open", out)
        F.run(240)
        for _ in range(6):
            press(F, "A", 90)
        for _ in range(10):
            press(F, "B", 60)
        dump(F, "pot_closed", out)
        F.run(120)
        dump(F, "end", out)
