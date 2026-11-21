import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OBJECTS = 0x020F33D8 + 8
LOG = os.path.join(kitpaths.SP, "names", "b10", "M2", "leaderwatch.log")


def snapshot(con):
    out = []
    for i in range(4):
        obj = struct.unpack("<I", con.read(OBJECTS + 4 * i, 4))[0]
        if not obj:
            out.append((i, 0))
            continue
        index = struct.unpack("<h", con.read(obj + 4, 2))[0]
        followed, position, leader = struct.unpack("<3b", con.read(obj + 0x1C8, 3))
        out.append((i, obj, index, followed, position, leader))
    return tuple(out)


def play(F):
    import dqix_flows

    con = F.cons[0]
    lines, last = [], [None]
    base_run = F.run

    def run(frames):
        for _ in range(frames):
            base_run(1)
            now = snapshot(con)
            if now != last[0]:
                parts = []
                for entry in now:
                    if len(entry) == 2:
                        parts.append(f"obj{entry[0]}=NULL")
                    else:
                        i, obj, index, followed, position, leader = entry
                        parts.append(f"obj{i}={obj:#010x} index4={index} follows1c8={followed} "
                                     f"position1c9={position} leader1ca={leader}")
                lines.append(f"f{con.frames} " + " | ".join(parts))
                last[0] = now
        return True

    F.run = run
    try:
        dqix_flows.boot_all(F)
        dqix_flows.leave_church(F, 0)
    finally:
        F.run = base_run
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
