import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import os as _bcos, sys as _bcsys
_bcsys.path.insert(0, _bcos.path.dirname(_bcos.path.dirname(_bcos.path.abspath(__file__))))
import buildcfg
"""Every stack slot the ROM function touches, against every slot our candidate touches.

`pad/spslots.py` answers this question only for `main:02061c04` -- it is wired to casediff, which is
the per-case machinery for that one function. This is the same question for ANY address, which is
what a 4000-byte "frame is 0x388 vs 0x1e0" verdict actually needs: a frame that is too big is never
a colouring problem, and no rewrite rule can see it.

Usage: python pad/framemap.py <module> <addr> <src.cpp>
       MWCC=2.0/sp2p2 python pad/framemap.py ...      (same override as the gate)

Reads:  the ROM slot straight out of extract/, and the candidate compiled with the project flags.
Prints: the two frame sizes, then the slots side by side in address order with the widths that
        touch them, then the first rank where the two lists diverge -- the object below that rank is
        the one whose size is wrong.
"""
import os
import re
import subprocess
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from elftools.elf.elffile import ELFFile

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
CC = buildcfg.cc_path(os.environ.get("MWCC"))
FLAGS = list(buildcfg.FLAGS)

MOD, ADDR, SRC = sys.argv[1], sys.argv[2].lower(), sys.argv[3]
cfg = buildcfg.config_dir(MOD)
symtxt = open(f"{REPO}/{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()
m = re.search(r'\S+ kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\) addr:0x0*%s\b'
              % ADDR.lstrip('0'), symtxt, re.I)
if not m:
    print("NO-SLOT")
    sys.exit(1)
isa, slot = m.group(1).lower(), int(m.group(2), 16)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if isa == "thumb" else CS_MODE_ARM)

if MOD == "main":
    blob = open(f"{REPO}/{buildcfg.pristine('main')}", "rb").read()
    base = 0x02000000
else:
    blob = open(f"{REPO}/{buildcfg.pristine(MOD)}", "rb").read()
    base = min(int(x, 16) for x in
               re.findall(r'start:0x([0-9a-fA-F]+)', open(f"{REPO}/{cfg}/delinks.txt").read()))
off = int(ADDR, 16) - base
rom = list(md.disasm(blob[off:off + slot], int(ADDR, 16)))

obj = f"{SP}/framemap_{os.getpid()}.o"
r = subprocess.run([CC] + FLAGS + ["-c", os.path.abspath(SRC), "-o", obj],
                   capture_output=True, text=True, cwd=REPO)
if r.returncode:
    print("COMPILE-FAIL", (r.stdout + r.stderr)[-400:])
    sys.exit(1)
best = b""
with open(obj, "rb") as fh:
    for s in ELFFile(fh).iter_sections():
        if s.name.startswith(".text") and s.data_size > len(best):
            best = s.data()
mine = list(md.disasm(best, 0))
os.remove(obj)

SUB = re.compile(r"^sp, sp, #(0x[0-9a-f]+|\d+)$")
SLOT = re.compile(r"\[sp,? ?(?:#(0x[0-9a-f]+|\d+))?\]|(?:^|, )sp, #(0x[0-9a-f]+|\d+)")


def frame_and_slots(instrs):
    """(bytes of frame, {offset: set of mnemonics touching it})."""
    size, slots = 0, {}
    for i in instrs:
        opstr = i.op_str
        if i.mnemonic == "sub":
            mm = SUB.match(opstr)
            if mm:
                size = int(mm.group(1), 0)
                continue
        if "sp" not in opstr:
            continue
        for mm in SLOT.finditer(opstr):
            raw = mm.group(1) or mm.group(2)
            # `[sp]` with no displacement is offset 0, and it is a real slot like any other.
            n = int(raw, 0) if raw else 0
            slots.setdefault(n, set()).add(i.mnemonic)
    return size, slots


rsize, rslots = frame_and_slots(rom)
msize, mslots = frame_and_slots(mine)
print("frame   ROM 0x%x (%d)   ours 0x%x (%d)   delta %+d"
      % (rsize, rsize, msize, msize, msize - rsize))
print("slots   ROM %d   ours %d" % (len(rslots), len(mslots)))
print()

rk, mk = sorted(rslots), sorted(mslots)
print("%-4s  %-22s  %-22s" % ("rank", "ROM", "ours"))
for n in range(max(len(rk), len(mk))):
    a = "0x%-5x %s" % (rk[n], ",".join(sorted(rslots[rk[n]]))) if n < len(rk) else ""
    b = "0x%-5x %s" % (mk[n], ",".join(sorted(mslots[mk[n]]))) if n < len(mk) else ""
    flag = "" if a[:7] == b[:7] else "  <-"
    print("%-4d  %-22s  %-22s%s" % (n, a, b, flag))

for n in range(min(len(rk), len(mk))):
    if rk[n] != mk[n]:
        print("\nFIRST DIVERGENCE at rank %d: ROM 0x%x, ours 0x%x (%+d)."
              % (n, rk[n], mk[n], mk[n] - rk[n]))
        print("Everything below this rank agrees, so the object occupying the space just under it "
              "is the wrong size. A uniform shift from here down means ONE object is wrong; a shift "
              "that grows means several are.")
        break
else:
    if len(rk) != len(mk):
        print("\nSame offsets as far as both lists go, but the counts differ (%d vs %d): the extra "
              "slots are objects one side has and the other does not." % (len(rk), len(mk)))
