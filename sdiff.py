"""Structural diff of a candidate against the ROM, ignoring pc-relative noise.

wdiff reports every literal-pool offset shift as a difference, so a single extra
instruction makes dozens of lines look wrong. Normalising immediates and pc
offsets shows only the places where the CODE actually differs, which is what you
edit the source to fix.

Usage: python sdiff.py <module> <addr> <file.cpp> [min-run]
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import os, re, sys, subprocess, difflib
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB

import buildcfg

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
MOD, ADDR, SRC = sys.argv[1], sys.argv[2], sys.argv[3]
MINRUN = int(sys.argv[4]) if len(sys.argv) > 4 else 1
CC = buildcfg.cc_path(os.environ.get("MWCC"))
FLAGS = list(buildcfg.FLAGS)
if os.environ.get("SDIFF_FLAGS"): FLAGS = FLAGS + os.environ["SDIFF_FLAGS"].split()

cfg = buildcfg.config_dir(MOD)
symtxt = open(f"{REPO}/{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()
m = re.search(r'\S+ kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\) addr:0x0*%s\b'
              % ADDR.lstrip('0'), symtxt, re.I)
if not m:
    print("NO-SLOT"); sys.exit(1)
isa, slot = m.group(1).lower(), int(m.group(2), 16)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if isa == "thumb" else CS_MODE_ARM)

if MOD == "main":
    blob = open(f"{REPO}/{buildcfg.pristine('main')}", "rb").read(); base = 0x02000000
else:
    blob = open(f"{REPO}/{buildcfg.pristine(MOD)}", "rb").read()
    base = min(int(x, 16) for x in
               re.findall(r'start:0x([0-9a-fA-F]+)', open(f"{REPO}/{cfg}/delinks.txt").read()))
off = int(ADDR, 16) - base
tgt = list(md.disasm(blob[off:off + slot], int(ADDR, 16)))

obj = f"{SP}/sdiff_{os.getpid()}.o"
r = subprocess.run([CC] + FLAGS + ["-c", SRC, "-o", obj], capture_output=True, text=True, cwd=REPO)
if r.returncode:
    print("COMPILE-FAIL", (r.stdout + r.stderr)[-300:]); sys.exit(1)
fh = open(obj, "rb")
e = ELFFile(fh)
best = b""
for s in e.iter_sections():
    if s.name.startswith(".text") and s.data_size > len(best):
        best = s.data()
mine = list(md.disasm(best, 0))
fh.close()
try:
    os.remove(obj)
except OSError:
    pass

def norm(i):
    s = i.mnemonic + " " + i.op_str
    s = re.sub(r'\[pc, #-?0x[0-9a-f]+\]', '[pc]', s)      # pool offsets shift with size
    s = re.sub(r'#-?0x[0-9a-f]+', '#K', s)
    s = re.sub(r'#\d+', '#K', s)
    return s

A = [norm(i) for i in tgt]
B = [norm(i) for i in mine]
sm = difflib.SequenceMatcher(None, A, B)
print("target %d instrs (0x%x), mine %d instrs, similarity %.1f%%"
      % (len(A), slot, len(B), 100 * sm.ratio()))
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "equal" or max(i2 - i1, j2 - j1) < MINRUN:
        continue
    print("== %s  target[%d:%d]  mine[%d:%d]" % (tag, i1, i2, j1, j2))
    for k in range(i1, min(i2, i1 + 8)):
        print("   tgt  %08x %s %s" % (tgt[k].address, tgt[k].mnemonic, tgt[k].op_str))
    for k in range(j1, min(j2, j1 + 8)):
        print("   MINE          %s %s" % (mine[k].mnemonic, mine[k].op_str))
