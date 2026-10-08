import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import os
import re
import struct
import sys

from elftools.elf.elffile import ELFFile

sys.path.insert(0, (_kp.KIT + "/frida"))
import forcenoalias  # noqa: E402

REPO = _kp.REPO

TARGETS = {
    "ov023": ((_kp.SP + "/handwork/evo/021d8ba0/ov023case/c_actor02.cpp"), 0x021f4c04, 0x3c4),
    "ov023base": ((_kp.SP + "/handwork/evo/021d8ba0/ov023case/c_dtlocal.cpp"), 0x021f4c04, 0x3c4),
    "ov026": ((_kp.SP + "/handwork/evo/021d8ba0/structify/v_honest.cpp"), 0x021d8ba0, 0x22c0),
}


def rom(mod, addr, size):
    # TARGETS are USA addresses. The active region must not move this read.
    cfg = open(f"{REPO}/config/usa/arm9/overlays/{mod}/delinks.txt").read()
    base = min(int(x, 16) for x in re.findall(r"start:0x([0-9a-fA-F]+)", cfg))
    blob = open(f"{REPO}/extract/usa/arm9_overlays/{mod}.bin", "rb").read()
    return struct.unpack("<%dI" % (size // 4), blob[addr - base:addr - base + size])


def relocish(w):
    return (w >> 24) in (0xEA, 0xEB) or (w & 0x0F7F0000) == 0x051F0000


def words(obj, size):
    with open(obj, "rb") as fh:
        e = ELFFile(fh)
        secs = [s for s in e.iter_sections() if s.name.startswith(".text") and s.data_size]
        data = max(secs, key=lambda s: s.data_size).data()
    return len(data), struct.unpack("<%dI" % (min(len(data), size) // 4), data[:size])


if __name__ == "__main__":
    name, mode = sys.argv[1], sys.argv[2]
    src, addr, size = TARGETS[name]
    mod = name[:5]
    obj = (_kp.KIT + "/frida/real_%s_%s.o") % (name, mode)
    forcenoalias.run(src, mode, obj)
    n, ours = words(obj, size)
    R = rom(mod, addr, size)
    bad = [i * 4 for i, (a, b) in enumerate(zip(ours, R)) if a != b and not (relocish(a) and relocish(b))]
    pool = [b for b in bad if b >= size - 0x40]
    print("%s mode=%s size=0x%x rom=0x%x diffwords=%d %s" % (name, mode, n, size, len(bad), ["0x%x" % b for b in bad[:24]]))
