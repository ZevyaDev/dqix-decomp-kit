import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
GAME_STATE = 0x020F33D8
LOG = os.path.join(kitpaths.SP, "names", "b10", "M6", "b10M6_camreset_mem.log")


def camera(F):
    con = F.cons[0]
    cam = struct.unpack("<I", con.read(GAME_STATE + 0x3B0, 4))[0]
    if not 0x02000000 <= cam < 0x02800000:
        return f"camera {cam:#x}"
    orbit = struct.unpack("<3i", con.read(cam + 0x220, 12))
    home = struct.unpack("<h", con.read(cam + 0x246, 2))[0]
    return f"camera {cam:#x} +0x220 angle {orbit[0]:#x} height {orbit[1]:#x} distance {orbit[2]:#x} +0x246 {home:#x}"


def watch(F, log, frames, keys=None, step=10):
    for _ in range(0, frames, step):
        if keys:
            F.hold(0, keys, step)
        else:
            F.run(step)
        log.write(f"f{F.cons[0].frames} {'+'.join(keys) if keys else '-'} {camera(F)}\n")


def play(F):
    import dqix_flows
    T = dqix_flows.T
    with open(LOG, "w", encoding="utf-8") as log:
        dqix_flows.boot_all(F)
        dqix_flows.leave_church(F, 0)
        log.write(f"f{F.cons[0].frames} outside {camera(F)}\n")
        F.walk(0, ["Left"], lambda p: p[0] < 11.7)
        F.walk(0, ["Down"], lambda p: p[1] > 12.0)
        F.walk(0, ["Left"], lambda p: p[0] < 2.2)
        F.walk(0, ["Down"], lambda p: p[1] > 32.0)
        F.move_to(0, tz=32.5)
        F.move_to(0, tx=-7.6)
        F.align(0, tx=-7.6)
        log.write(f"f{F.cons[0].frames} at inn door {camera(F)}\n")
        watch(F, log, 8, ["R"], step=4)
        watch(F, log, 20)
        F.walk(0, ["Up"], max_steps=10)
        log.write(f"f{F.cons[0].frames} walked {camera(F)} pos {F.pos(0)}\n")
        watch(F, log, T["room_transition"] + 120)
