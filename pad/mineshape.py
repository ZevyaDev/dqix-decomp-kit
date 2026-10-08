"""Find an already-matched function whose ROM code has a shape no source form reproduces.

`findorr.py` answered one such question and its answer -- a left-associated OR chain in
`GenerateDeviceRandomBytes_020120f0` -- was the crack. This is the same search with the pattern on
the command line, so the next residue costs a regex instead of a new script.

    python mineshape.py '<regex>' [window=3]

The regex is matched against a window of consecutive instructions joined by ' ; ', each rendered as
`mnemonic operands`. Backreferences work, so a register can be required to repeat:

    python mineshape.py 'lsl (r\\d+), \\1, #\\d+ ; .* ; orr (r\\d+), \\2, \\1, lsr #\\d+'

Committed hits are listed first -- their C IS the answer. Uncommitted ones in a delinked range are
laboratories; the rest are unsplit code.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import glob
import os
import re
import sys

import capstone

REPO = _kp.REPO
BASE = 0x02000000

if len(sys.argv) < 2:
    sys.exit(__doc__)
PAT = re.compile(sys.argv[1])
WIN = int(sys.argv[2]) if len(sys.argv) > 2 else 3

md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
md.skipdata = True

ranges = []
txt = open(f"{REPO}/{buildcfg.config_root()}/delinks.txt", encoding="utf-8", errors="ignore").read()
for a, b in re.findall(r"(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$", txt):
    ranges.append((int(a, 16), int(b, 16)))
ranges.sort()

sources = {}
for p in glob.glob(f"{REPO}/src/**/*.c*", recursive=True):
    t = open(p, encoding="utf-8", errors="ignore").read()
    for m in re.finditer(r"//\s*USA:\s*\w*?([0-9a-fA-F]{8})", t):
        sources[int(m.group(1), 16)] = p

blob = open(f"{REPO}/{buildcfg.extract_root()}/arm9/arm9.bin", "rb").read()
window = []
committed, lab, raw = [], [], []
for ins in md.disasm(blob, BASE):
    window.append(ins)
    if len(window) > WIN:
        window.pop(0)
    if len(window) < WIN:
        continue
    joined = " ; ".join("%s %s" % (i.mnemonic, i.op_str) for i in window)
    if not PAT.search(joined):
        continue
    addr = window[0].address
    owner = next((r for r in ranges if r[0] <= addr < r[1]), None)
    src = sources.get(owner[0]) if owner else None
    (committed if src else lab if owner else raw).append((addr, joined, src))

print("%d hit(s): %d in a committed source, %d delinked without one, %d unsplit"
      % (len(committed) + len(lab) + len(raw), len(committed), len(lab), len(raw)))
for tag, rows in (("COMMITTED -- their C IS the answer", committed),
                  ("delinked, no source", lab), ("unsplit code", raw)):
    if not rows:
        continue
    print("\n== %s" % tag)
    for addr, joined, src in rows[:25]:
        where = os.path.relpath(src, REPO).replace("\\", "/") if src else ""
        print("  0x%08x  %s  %s" % (addr, joined[:88], where))
