"""Reconstruct a global object's real field layout from every access in the image.

    python objmap.py <module> <symbol_addr> [more_modules...]

Finds every pool word equal to the symbol address, then reports the load/store offsets and widths
used off that base. An invented `char pad[N]; int field;` struct is a guess; this is the evidence.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import os
import re
import struct
import sys

import capstone

REPO = _kp.REPO
target = int(sys.argv[2], 0)
mods = [sys.argv[1]] + sys.argv[3:]

md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
md.detail = True


def image(mod):
    cfg = buildcfg.config_root()
    ext = buildcfg.extract_root()
    if mod == "arm9":
        return (REPO + "/" + ext + "/arm9/arm9.bin",
                REPO + "/" + cfg + "/delinks.txt",
                REPO + "/" + cfg + "/symbols.txt")
    return (REPO + "/" + ext + "/arm9_overlays/%s.bin" % mod,
            REPO + "/" + cfg + "/overlays/%s/delinks.txt" % mod,
            REPO + "/" + cfg + "/overlays/%s/symbols.txt" % mod)


def syms(path):
    out = []
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except IOError:
        return out
    for m in re.finditer(r"^(\S+) kind:function\(\w+,size=0x([0-9a-fA-F]+)\) addr:0x([0-9a-fA-F]+)",
                         text, re.M):
        out.append((int(m.group(3), 16), int(m.group(2), 16), m.group(1)))
    out.sort()
    return out


rows = []
for mod in mods:
    binpath, cfg, symfile = image(mod)
    try:
        blob = open(binpath, "rb").read()
        base = min(int(x, 16) for x in
                   re.findall(r"start:0x([0-9a-fA-F]+)",
                              open(cfg, encoding="utf-8", errors="ignore").read()))
    except (IOError, ValueError):
        continue
    table = syms(symfile)
    words = [int.from_bytes(blob[i:i + 4], "little") for i in range(0, len(blob) - 3, 4)]
    pool = {i for i, w in enumerate(words) if w == target}
    if not pool:
        continue
    print("== %s: %d pool word(s) hold %08x" % (mod, len(pool), target))
    ins = list(md.disasm(blob, base))
    by_addr = {i.address: k for k, i in enumerate(ins)}
    for pi in pool:
        paddr = base + pi * 4
        for k, i in enumerate(ins):
            if i.mnemonic != "ldr" or "pc" not in i.op_str:
                continue
            m = re.search(r"\[pc, #(-?(?:0x)?[0-9a-fA-F]+)\]", i.op_str)
            if not m:
                continue
            tgt = i.address + 8 + int(m.group(1), 0)
            if tgt != paddr:
                continue
            reg = i.op_str.split(",")[0].strip()
            owner = next((n for s, sz, n in table if s <= i.address < s + sz), "?")
            for j in ins[k + 1:k + 14]:
                if j.mnemonic in ("bl", "blx"):
                    break
                mm = re.search(r"\[%s(?:, #(-?(?:0x)?[0-9a-fA-F]+))?\]" % reg, j.op_str)
                if mm and j.mnemonic.startswith(("ldr", "str")):
                    off = int(mm.group(1), 0) if mm.group(1) else 0
                    rows.append((off, j.mnemonic, mod, j.address, owner))
                if j.op_str.startswith(reg + ",") and j.mnemonic in ("mov", "add", "sub"):
                    break

print()
print("field accesses by offset:")
seen = {}
for off, mn, mod, addr, owner in sorted(rows):
    seen.setdefault((off, mn), []).append((mod, addr, owner))
for (off, mn), hits in sorted(seen.items()):
    print("  +0x%-4x %-6s x%-3d  e.g. %s %08x  %s"
          % (off, mn, len(hits), hits[0][0], hits[0][1], hits[0][2][:40]))
