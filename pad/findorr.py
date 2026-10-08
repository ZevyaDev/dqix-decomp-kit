"""Where does a committed source already produce `orr rD, rD, rX, shift` feeding a stack store?

0209a104 and 0209a218 differ from the ROM only in which register the bitfield insert lands in: the
ROM accumulates into the word's own register and we take the inserted value's. No source form
reaches it, so read one that already does.

Usage: python findorr.py [max_gap=3]
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
GAP = int(sys.argv[1]) if len(sys.argv) > 1 else 3

blob = open(f"{REPO}/{buildcfg.extract_root()}/arm9/arm9.bin", "rb").read()
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
md.skipdata = True

ranges = []
for dl in [f"{REPO}/{buildcfg.config_root()}/delinks.txt"]:
    txt = open(dl, encoding="utf-8", errors="ignore").read()
    for a, b in re.findall(r"(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$", txt):
        ranges.append((int(a, 16), int(b, 16)))
ranges.sort()

sources = {}
for p in glob.glob(f"{REPO}/src/**/*.c*", recursive=True):
    t = open(p, encoding="utf-8", errors="ignore").read()
    for m in re.finditer(r"//\s*USA:\s*\w*?([0-9a-fA-F]{8})", t):
        sources[int(m.group(1), 16)] = p

ORR = re.compile(r"^(r\d+|sb|sl|fp|ip), (r\d+|sb|sl|fp|ip), (r\d+|sb|sl|fp|ip), (lsr|lsl|asr) #(\d+)$")
STR = re.compile(r"^(r\d+|sb|sl|fp|ip), \[sp(?:, #(?:0x)?[0-9a-fA-F]+)?\]$")

hits = []
window = []
for ins in md.disasm(blob, BASE):
    window.append(ins)
    if len(window) > GAP + 1:
        window.pop(0)
    if ins.mnemonic != "str":
        continue
    ms = STR.match(ins.op_str)
    if not ms:
        continue
    for prev in window[:-1]:
        if prev.mnemonic != "orr":
            continue
        mo = ORR.match(prev.op_str)
        if not mo or mo.group(1) != mo.group(2) or mo.group(1) != ms.group(1):
            continue
        owner = next((r for r in ranges if r[0] <= prev.address < r[1]), None)
        src = sources.get(owner[0]) if owner else None
        hits.append((prev.address, prev.op_str, src, owner))

print("%d site(s) where the accumulator IS the orr destination and it stores to the frame" % len(hits))
have = [h for h in hits if h[2]]
print("%d inside a committed source -- their C IS the answer:\n" % len(have))
for addr, ops, src, _ in have:
    print("  0x%08x  orr %-28s  %s" % (addr, ops, os.path.relpath(src, REPO).replace("\\", "/")))
print()
for addr, ops, src, owner in hits:
    if not src:
        print("  0x%08x  orr %-28s  %s" % (addr, ops, "delinked, no source" if owner else "not delinked"))
