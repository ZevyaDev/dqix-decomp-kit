#!/usr/bin/env python
"""Full decoded listing of the TARGET function -- exactly its slot, never truncated.

WHY. The worker doc told workers to read the target with `grep -rhA80 "^func_ovNNN_ADDR:"`. That is 80
LINES, which is fine for the small tier and silently wrong for the large one: the median unmatched
>256B function in ov017 is 512B = 128 instructions, so -A80 showed 62% of it, and the largest is 6400B
= 1600 instructions, of which it showed 5%. Workers were being asked to byte-match functions whose
tails they had never seen -- which is a far better explanation for the large tier's 1.0 PASS/worker
than difficulty is.

Reads the PRISTINE ROM bytes for the symbol's exact size, so the listing is complete by construction
and needs no build. Pool words that decode as bogus instructions are shown as `.word` when they are
the target of a pc-relative load, so they are not mistaken for code.

Usage: python wlist.py <OV|main> <addr>
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import re, sys, os, glob

import buildcfg
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB

REPO = _kp.REPO
OV, ADDR = sys.argv[1], sys.argv[2]

if OV == "main":
    CFG = f"{REPO}/{buildcfg.config_dir('main')}"
    BLOB = open(f"{REPO}/{buildcfg.pristine('main')}", "rb").read()
    PFX, BASE = "func_", 0x02000000
else:
    CFG = f"{REPO}/{buildcfg.config_dir(OV)}"
    BLOB = open(f"{REPO}/{buildcfg.pristine(OV)}", "rb").read()
    PFX = buildcfg.func_prefix(OV)
    BASE = min(int(m, 16) for m in
               re.findall(r'start:0x([0-9a-fA-F]+)', open(f"{CFG}/delinks.txt").read()))

sym = open(f"{CFG}/symbols.txt", encoding='utf-8', errors='ignore').read()
m = (re.search(rf'{PFX}{ADDR} kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\)', sym, re.I)
     or re.search(r'\S+ kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\) addr:0x0*%s'
                  % ADDR.lstrip('0'), sym, re.I))
if not m:
    sys.exit(f"NO-SLOT: nothing at {ADDR} in {CFG}/symbols.txt")
ISA, slot = m.group(1).lower(), int(m.group(2), 16)

a = int(ADDR, 16)
off = a - BASE
buf = BLOB[off:off + slot]
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if ISA == 'thumb' else CS_MODE_ARM)
# WITHOUT skipdata capstone STOPS at the first word it cannot decode, and a mid-body literal pool is
# exactly that: on main:02061c04 the listing ended at 1278 of 2551 instructions and the second half of
# the function was simply invisible to every worker who read it. skipdata emits a `.byte` pseudo-op and
# keeps going, so the listing always covers the whole slot.
md.skipdata = True
step = 2 if ISA == 'thumb' else 4

# Literal pools sit inside .text and decode as valid-looking nonsense (the classic `andeq`). Mark every
# word that some pc-relative load points at, so the worker does not try to write C for a constant.
pool = set()
for i in md.disasm(buf, a):
    mm = re.search(r'\[pc, #(-?(?:0x)?[0-9a-fA-F]+)\]', i.op_str)
    if mm and i.mnemonic.startswith('ldr'):
        t = (i.address - a + (8 if ISA == 'arm' else 4) + int(mm.group(1), 0)) & ~3
        if 0 <= t < len(buf):
            pool.add(t)

# RESOLVE CALL/DATA TARGETS INLINE. Measured 08-11: workers hit symbols.txt 153 times in 4 hours at
# ~5.4k chars a grep, purely to turn `bl #0x21d8a40` into a name. The listing already knows the target
# address, so print the name next to it and there is nothing left to look up.
SYMS = {}
for _m in re.finditer(r'^(\S+) kind:(?:function|data)\([^)]*\) addr:0x([0-9a-fA-F]+)', sym, re.M):
    SYMS[int(_m.group(2), 16)] = _m.group(1)
for _c in glob.glob(f"{REPO}/{buildcfg.config_dir('main')}/symbols.txt") + glob.glob(f"{REPO}/{buildcfg.config_dir('main')}/overlays/ov*/symbols.txt"):
    if _c.replace("\\", "/") == f"{CFG}/symbols.txt":
        continue
    for _m in re.finditer(r'^(\S+) kind:(?:function|data)\([^)]*\) addr:0x([0-9a-fA-F]+)',
                          open(_c, encoding='utf-8', errors='ignore').read(), re.M):
        SYMS.setdefault(int(_m.group(2), 16), _m.group(1))

# LOOP BACK-EDGES. A branch to an EARLIER address is a loop edge; marking it makes the loop boundary
# visible without decoding it by hand. Branch-target mismatch is the tell that a diff is a loop-SHAPE
# problem rather than register colouring -- the distinction that cost 11 workers on func_ov027_021dc680.
BACK = set()
for i in md.disasm(buf, a):
    if i.mnemonic.startswith('b') and not i.mnemonic.startswith('bic'):
        mm = re.match(r'#(?:0x)?([0-9a-fA-F]+)$', i.op_str.strip())
        if mm and a <= int(mm.group(1), 16) <= i.address:
            BACK.add(int(mm.group(1), 16) - a)

print(f"{PFX}{ADDR}  isa={ISA}  size=0x{slot:x} ({slot//step} instrs)")
text = {i.address - a: f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(buf, a)}
for o in range(0, slot - step + 1, step):
    if o in pool:
        print(f"  +0x{o:04x}  .word 0x{int.from_bytes(buf[o:o+4],'little'):08x}   ; POOL DATA, not code")
    else:
        _txt = text.get(o, '.word 0x' + buf[o:o + step][::-1].hex())
        # annotate bl/b targets with the symbol name, and mark loop entry points
        _mm = re.search(r'#(?:0x)?([0-9a-fA-F]+)$', _txt)
        if _mm and _txt.split()[0].startswith('b'):
            _t = int(_mm.group(1), 16)
            _nm = SYMS.get(_t)          # targets are absolute now
            if _nm:
                _txt += f"   ; -> {_nm}"
        _mark = "LOOP>" if o in BACK else "     "
        print(f"  {_mark}+0x{o:04x}  {_txt}")

