#!/usr/bin/env python
"""Compact DECODED diff for the iteration loop: only the diverging instructions, side by side.

WHY THIS EXISTS. Cost of matching a large function is roughly (context size) x (iteration count), and
for the large tier both terms are bad: a 2KB function is ~500 instructions, and a worker that dumps
that disassembly once carries ~30k tokens in context for every one of the next 20-40 gate cycles. That
single decision dominates the bill -- measured 08-11, worker context averaged 226k tokens per message
and 83.6% of it was tool output.

wgate says WHICH bytes differ. wdiag prints the raw words. Neither tells you what changed, so the
worker re-disassembles to find out -- and that is the expensive habit. This prints exactly the diverging
instructions, decoded, target vs yours, with one instruction of context either side. A typical
mid-iteration diff comes out at 5-15 lines instead of a 500-line dump.

Usage: python wdiff.py <OV|main> <addr> <file.cpp> [section=.text]
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import subprocess, re, sys, os, io, threading

from elfobj import ELFFile

import residue
import buildcfg

REPO = _kp.REPO
# PID-isolated compiler scratch belongs to external state.
SCR = f"{_kp.SP}/handwork/compile"
os.makedirs(SCR, exist_ok=True)
CC = buildcfg.cc_path(os.environ.get("MWCC"))
FLAGS = list(buildcfg.FLAGS)
# Per-file flag experiments: a real build can compile one file with different optimisation
# settings, and that changes register allocation without changing the source. Set
# WDIFF_FLAGS to replace or extend the default set when probing such a case.
_extra = os.environ.get("WDIFF_FLAGS", "")
if _extra:
    FLAGS = FLAGS + _extra.split()

CTX = int(os.environ.get("WDIFF_CTX", "1"))       # instructions of context around each diverging run
MAXRUNS = int(os.environ.get("WDIFF_MAXRUNS", "12"))
THM_BR = {10, 25, 30, 31}


class Fail(Exception):
    pass


_MODULES = {}


def _module(ov):
    if ov not in _MODULES:
        cfg = buildcfg.config_dir(ov)
        with open(os.path.join(REPO, buildcfg.pristine(ov)), "rb") as fh:
            pristine = fh.read()
        with open(os.path.join(REPO, cfg, "delinks.txt"), encoding="utf-8") as fh:
            delinks = fh.read()
        if ov == "main":
            pfx, base = "func_", 0x02000000
        else:
            pfx = f"func_ov{ov}_"
            base = min(int(m, 16) for m in re.findall(r'start:0x([0-9a-fA-F]+)', delinks))
        with open(os.path.join(REPO, cfg, "symbols.txt"), encoding='utf-8', errors='ignore') as fh:
            symtxt = fh.read()
        _MODULES[ov] = (cfg, pristine, pfx, base, symtxt, delinks.split(chr(10) + chr(10))[0])
    return _MODULES[ov]


def diff(ov, addr, src, sec=None, out=None, diagnose=True, ctx=None, maxruns=None):
    out = [] if out is None else out
    try:
        return _diff(ov, addr, src, sec, out, diagnose, CTX if ctx is None else ctx,
                     MAXRUNS if maxruns is None else maxruns)
    except Fail as e:
        out.append(str(e))
        return 1


def _diff(OV, ADDR, SRC, SEC, out, diagnose, CTX, MAXRUNS):
    CFG, PRISTINE, PFX, BASE, symtxt, _head = _module(OV)
    m = re.search(rf'{PFX}{ADDR} kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\)', symtxt, re.I)
    if not m:
        m = re.search(r'\S+ kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\) addr:0x0*%s' % ADDR.lstrip('0'),
                      symtxt, re.I)
    if not m:
        raise Fail(f"NO-SLOT: nothing at {ADDR} in {CFG}/symbols.txt")
    ISA, slot = m.group(1).lower(), int(m.group(2), 16)

    if SEC is None:
        _av = int(ADDR, 16)
        _hit = next((mm.group(1) for mm in
                     re.finditer(r'\.(\w+)\s+start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+) kind:code', _head)
                     if int(mm.group(2), 16) <= _av < int(mm.group(3), 16)), None)
        SEC = '.' + _hit if _hit else ".text"

    _OBJ = f"{SCR}/wdiff_{os.getpid()}_{threading.get_ident()}.o"
    _cc, _flags = CC, FLAGS
    if not (os.environ.get("MWCC") or _extra):
        _b = os.environ.get("WDIFF_BUILD") or buildcfg.builds_for(OV, ADDR, SRC)[0]
        _cc, _flags = buildcfg.build_cc(_b), buildcfg.build_flags(_b)
    try:
        r = subprocess.run(buildcfg.compile_command(SRC, _OBJ, _cc, _flags + buildcfg.lang_flags(SRC)),
                           capture_output=True, text=True, cwd=REPO)
        if r.returncode != 0:
            raise Fail("COMPILE-FAIL: " + (r.stdout + r.stderr)[-600:])
        buildcfg.postcompile(_OBJ)
        with open(_OBJ, "rb") as _fh:
            elf = ELFFile(io.BytesIO(_fh.read()))
        _texts = buildcfg.sections(elf, SEC)
        texts = [s for _, s in _texts]
        if not texts:
            raise Fail(f"SIZE/OVERGEN: no {SEC} emitted")
        total = sum(s['sh_size'] for s in texts)
        reloc = set()
        for sec in buildcfg.relocations(elf, _texts[0][0]):
            for rr in sec.iter_relocations():
                o = rr['r_offset']
                if rr['r_info_type'] in THM_BR:
                    reloc.update(range(o, o + 4))
                else:
                    reloc.update(range(o & ~3, (o & ~3) + 4))

        a = int(ADDR, 16)
        mine = texts[0].data()[:slot]
        orig = PRISTINE[a - BASE:a - BASE + slot]
    finally:
        try:
            os.remove(_OBJ)
        except OSError:
            pass

    if total != slot:
        out.append(f"SIZE/OVERGEN: emitted {SEC} total=0x{total:x} but slot=0x{slot:x} "
                   f"({'too short' if total < slot else 'too long — define ONLY this function'})")

    diffs = [i for i in range(min(len(mine), len(orig))) if i not in reloc and mine[i] != orig[i]]
    if not diffs:
        out.append("MATCH")
        return 0

    step = 2 if ISA == 'thumb' else 4

    do, dm = residue.decode(orig, ISA), residue.decode(mine, ISA)
    bad =sorted({(i // step) * step for i in diffs})
    runs = []
    for o in bad:
        if runs and o - runs[-1][1] <= step * (CTX + 1):
            runs[-1][1] = o
        else:
            runs.append([o, o])

    out.append(f"BYTEDIFF {len(diffs)} bytes in {len(runs)} run(s), slot=0x{slot:x} isa={ISA}")
    for s, e in runs[:MAXRUNS]:
        lo, hi = max(0, s - step * CTX), min(len(orig) - step, e + step * CTX)
        for o in range(lo, hi + step, step):
            mark = "*" if o in bad else " "
            t, y = do.get(o, "?"), dm.get(o, "?")
            out.append(f" {mark}0x{o:04x}  {t:<34}| {y}" if t != y else f" {mark}0x{o:04x}  {t}")
    if len(runs) > MAXRUNS:
        out.append(f" ... {len(runs)-MAXRUNS} more run(s) suppressed (raise WDIFF_MAXRUNS)")
    out.append("legend: '*' = differs, left = TARGET | right = yours (reloc bytes already masked)")
    if diagnose:
        _diagnose(orig, mine, ISA, reloc, slot, out)
    return 0


def _diagnose(orig, mine, ISA, reloc, slot, out):
    _cls, _metric, _detail, _hint = residue.classify(orig, mine, ISA, reloc, slot)

    out.append("")
    out.append("DIAGNOSIS: %s%s" % (_cls, ("  " + _detail) if _detail else ""))
    if _cls == "LOOP-SHAPE":
        out.append("  BRANCH TARGETS DIFFER -> loop shape, NOT register colouring.")
        out.append("  No declaration/definition-order lever can fix it. Compare which instructions sit INSIDE")
        out.append("  the loop. Usual cause: the target hoists a field load OUT of the loop and keeps it in a")
        out.append("  register, while your source re-reads obj->field each iteration so the load is pulled IN.")
        out.append("  Fix: T* p = obj->field;  do { ... p++; obj->field = p; } while (...);")
    elif _cls == "REGPERM":
        out.append("  only REGISTER NUMBERS differ, every mnemonic and branch matches -> COLOURABLE.")
        out.append("  " + _hint)
        out.append("  Run: python colorsweep.py <mod> <addr> <your.cpp> --apply")
    elif _cls == "SCHED":
        out.append("  the same instructions in a DIFFERENT ORDER -> statement/definition order, not colouring.")
        out.append("  Move the definition, do not renumber registers. colorsweep r5/r16 generate these moves.")
    elif _cls == "SHAPE":
        out.append("  MNEMONICS differ -> the C construct itself is wrong, not the register assignment.")
        out.append("  Route by the differing instruction: predication (#3), offset chain (#4), bitfield (#7),")
        out.append("  bool-return (#8), volatile (#10). Do not permute declarations.")
    elif _cls in ("OVERGEN", "UNDERGEN"):
        out.append("  wrong SIZE -> no colouring rewrite can close it while the length is wrong.")
    else:
        out.append("  operands differ with matching mnemonics -> check immediates/offsets first (#4).")


def main(argv):
    os.chdir(REPO)
    out = []
    try:
        code = diff(argv[1], argv[2], argv[3], argv[4] if len(argv) > 4 else None, out)
    finally:
        for line in out:
            print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
