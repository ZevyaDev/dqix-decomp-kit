import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import os as _bcos, sys as _bcsys
_bcsys.path.insert(0, _bcos.path.dirname(_bcos.path.dirname(_bcos.path.abspath(__file__))))
import buildcfg
"""Compare ONE switch case body against the ROM, aligned at the body's own start.

wdiff aligns the whole function, so once one case body is the wrong size every later case reads as
a diff and the real per-case mismatch is invisible. This finds each build's body for a case through
its own jump table, then disassembles the two side by side from their own offsets.

Usage: python casediff.py <case_hex> [src.cpp] [--rom-only]
"""
import os
import re
import subprocess
import sys

import capstone
from elftools.elf.elffile import ELFFile

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
FUNC = 0x02061C04
TABLE = (0x28, 0x240)
# MWCC=<ver>/<sub> picks a different mwccarm build. Some functions only match on a later one
# than the project default, and the build is a variable to SEARCH (pad/ccscore.py), not a
# constant -- 02061c04 goes from 11 wrong-length case bodies to 2 on 2.0/sp2p2.
import os as _os
CC = buildcfg.cc_path(os.environ.get("MWCC"))
FLAGS = list(buildcfg.FLAGS)
# CDFLAGS appends to the command line. The build and the pragma state are searched routinely and
# the flags never were, though -proc and -inline change scheduling and allocation (pad/flagsweep.py).
FLAGS += _os.environ.get("CDFLAGS", "").split()
MD = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
MD.skipdata = True


def rom_text():
    blob = open(f"{REPO}/{buildcfg.extract_root()}/arm9/arm9.bin", "rb").read()
    cfg = f"{REPO}/{buildcfg.config_root()}/delinks.txt"
    base = min(int(x, 16) for x in re.findall(r"start:0x([0-9a-fA-F]+)", open(cfg).read()))
    off = FUNC - base
    return blob[off:off + 0x27DC]


def our_text(src):
    obj = os.path.splitext(src)[0] + "_cd.o"
    r = subprocess.run([CC] + FLAGS + ["-c", src, "-o", obj], capture_output=True, text=True,
                       cwd=REPO)
    if r.returncode:
        sys.exit(r.stdout[-2000:] + r.stderr[-2000:])
    with open(obj, "rb") as fh:
        secs = [s.data() for s in ELFFile(fh).iter_sections() if s.name.startswith(".text")]
    return max(secs, key=len)


def bodies(text):
    """case value -> (offset, length) from the dense jump table at the top of the function."""
    out = {}
    for off in range(*TABLE, 4):
        word = int.from_bytes(text[off:off + 4], "little")
        if word >> 24 != 0xEA:                      # unconditional b
            continue
        imm = word & 0xFFFFFF
        if imm & 0x800000:
            imm -= 0x1000000
        out[(off - TABLE[0]) // 4 + 0x64] = off + 8 + imm * 4
    ends = sorted(set(out.values())) + [len(text)]
    return {c: (t, ends[ends.index(t) + 1] - t) for c, t in out.items()}


def show(case, rom, ours):
    rb, ob = bodies(rom), bodies(ours)
    if case not in rb:
        sys.exit("case 0x%x is not in the table" % case)
    ro, rl = rb[case]
    print("case 0x%02x   ROM +0x%04x (%d B)   ours +0x%04x (%d B)"
          % (case, ro, rl, ob[case][0], ob[case][1]) if case in ob else "")
    oo, ol = ob.get(case, (0, 0))
    a = list(MD.disasm(rom[ro:ro + rl], 0))
    b = list(MD.disasm(ours[oo:oo + ol], 0)) if ol else []
    for i in range(max(len(a), len(b))):
        l = "%-38s" % ("%s %s" % (a[i].mnemonic, a[i].op_str) if i < len(a) else "")
        r = "%s %s" % (b[i].mnemonic, b[i].op_str) if i < len(b) else ""
        print("  %s%s| %s" % ("*" if l.strip() != r.strip() else " ", l, r))


if __name__ == "__main__":
    case = int(sys.argv[1], 16)
    src = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") \
        else f"{SP}/c04work/c04.cpp"
    show(case, rom_text(), our_text(src))
