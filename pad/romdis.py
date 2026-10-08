"""Disassemble an arbitrary ARM9 range from the pristine image, with no config entry needed.

`wlist.py` needs a symbol; the two remaining `r1/r2` two-node sites live in code `symbols.txt` has
no function for, so the only way to look at them -- and to use one as a laboratory for case 0xd3 --
is to read the bytes directly.

Usage: python romdis.py <start-hex> <count-instrs>
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import sys

import capstone

REPO = _kp.REPO
blob = open(f"{REPO}/{buildcfg.extract_root()}/arm9/arm9.bin", "rb").read()
BASE = 0x02000000

start = int(sys.argv[1], 16)
n = int(sys.argv[2]) if len(sys.argv) > 2 else 32
off = start - BASE
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
md.skipdata = True
for i, ins in enumerate(md.disasm(blob[off:off + n * 4], start)):
    print("  %08x  %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))
