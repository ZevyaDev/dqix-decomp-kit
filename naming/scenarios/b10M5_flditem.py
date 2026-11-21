import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/field_battle.mst"}
SPOTS = 0x02108FE4
ZONE3D = 0x020FB3F0
LOG = os.path.join(kitpaths.SP, "names", "b10", "M5", "flditem.log")


def dump(F, tag, out):
    con = F.cons[0]
    raw = con.read(SPOTS, 0x30)
    head, count, flag = struct.unpack("<IHB", raw[4:11])
    out.append(f"f{con.frames} {tag} +0={raw[0:4]!r} +4={head:#x} +8={count} +a={flag} +c={struct.unpack('<I', raw[12:16])[0]:#x}")
    node, n = head, 0
    while 0x02000000 <= node < 0x02400000 and n < 32:
        rec = con.read(node, 0x70)
        w0, w1, owner = struct.unpack("<IIi", rec[0:12])
        points = [struct.unpack("<3i", rec[0xC + 12 * k:0x18 + 12 * k]) for k in range(8)]
        nxt = struct.unpack("<I", rec[0x6C:0x70])[0]
        out.append(f"  rec {node:#x} w0={w0:#010x} w1={w1:#010x} +8={owner:#x} points={points[:((w1 >> 17) & 0xF)]}")
        node, n = nxt, n + 1


def play(F):
    out = []
    dump(F, "start", out)
    F.run(60)
    dump(F, "f60", out)
    with open(LOG, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
