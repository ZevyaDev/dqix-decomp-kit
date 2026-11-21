import os
import re

START = {"save": "saves/dq9ds_kheg_aug30.sav"}

NAME = re.compile(rb"mp\d{4}[a-z]{0,2}(?:\.chr)?")


def scan(F, label, out):
    raw = F.cons[0].read(0x02000000, 0x400000)
    for m in NAME.finditer(raw):
        out.write("%s %08x %s\n" % (label, 0x02000000 + m.start(), m.group().decode()))


MEMBER_DATA = (0x020F384C, 0x020F41B0, 0x020F4B14, 0x020F5478)


def dump_members(F, out):
    import struct
    for base in MEMBER_DATA:
        raw = F.cons[0].read(base, 0x500)
        equipped = struct.unpack("<10h", raw[0x488:0x49c])
        out.write("member %08x equipped %s gender_bit %d\n" % (base, list(equipped), raw[0x49c] & 1))
        for k in range(9):
            rec = raw[0x194 + k * 0x20:0x194 + k * 0x20 + 0x20]
            pointer = struct.unpack("<I", rec[0:4])[0]
            record_id = struct.unpack("<h", rec[0x18:0x1a])[0]
            category = None
            if 0x02000000 <= pointer < 0x02400000:
                word1 = struct.unpack("<I", F.cons[0].read(pointer + 4, 4))[0]
                category = (word1 << 12 & 0xFFFFFFFF) >> 24
            out.write("  +%03x id %d pointer %08x bits12_19 %s\n" % (0x194 + k * 0x20, record_id, pointer, category))


def play(F):
    import dqix_flows
    import kitpaths
    path = os.path.join(kitpaths.SP, "names", "b9", "C", "mpnames.log")
    with open(path, "w") as out:
        dqix_flows.boot_all(F)
        dqix_flows.leave_church(F, 0)
        scan(F, "before_inn", out)
        dqix_flows.church_to_inn(F, 0)
        scan(F, "in_inn", out)
        dump_members(F, out)
