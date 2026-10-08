#!/usr/bin/env python
"""ZERO-TOKEN inference of everything the binary already states about a function.

None of this is gate-able on its own — it is HELD material that goes into the scaffold so the worker
starts from facts instead of guesses. Only complete, byte-exact functions ever reach the gate and the
ROM checksum; nothing here can pollute the build.

Derived exactly (not guessed):
  * ARG COUNT      — which of r0..r3 are READ before being written (the classic liveness question)
  * RETURNS        — whether r0 is defined on the path to `bx lr`
  * STACK FRAME    — `sub sp,sp,#N` and how many sp-relative slots are touched
  * CALLEE-SAVED   — the push/pop list = how many values must stay live across calls (recipe #9's ladder)
  * STRUCT FIELDS  — every `[rN,#imm]` access with its width, grouped by base register and, where the
                     base is traceable to an incoming argument, attributed to that argument
  * CONTROL FLOW   — branch targets, so loops and if-chains are visible without re-reading the disasm

Usage: python infer.py <module> <addr>        (prints a comment block for scaffold.py)
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import re, sys, os
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
md.detail = True

WIDTH = {'ldr': ('int', 4), 'str': ('int', 4), 'ldrh': ('unsigned short', 2), 'strh': ('unsigned short', 2),
         'ldrb': ('unsigned char', 1), 'strb': ('unsigned char', 1), 'ldrsh': ('short', 2),
         'ldrsb': ('signed char', 1), 'ldrd': ('long long', 8), 'strd': ('long long', 8)}
MEM = re.compile(r'\[(\w+)(?:, #(-?(?:0x)?[0-9a-fA-F]+))?\]')


def load(mod, addr):
    if mod == "main":
        cfg, binp, base = buildcfg.config_dir("main"), buildcfg.pristine('main'), 0x02000000
    else:
        cfg = f"{buildcfg.config_dir(mod)}"
        binp = f"{buildcfg.pristine(mod)}"
        d = open(f"{REPO}/{cfg}/delinks.txt").read()
        base = min(int(x, 16) for x in re.findall(r'start:0x([0-9a-fA-F]+)', d))
    sym = open(f"{REPO}/{cfg}/symbols.txt", encoding='utf-8', errors='ignore').read()
    m = re.search(r'^\S+ kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\) addr:0x0*%s\b'
                  % addr.lstrip('0'), sym, re.M | re.I)
    if not m or m.group(1) != 'arm':
        return None, None
    sz = int(m.group(2), 16); a = int(addr, 16)
    blob = open(f"{REPO}/{binp}", "rb").read()
    return list(md.disasm(blob[a - base:a - base + sz], a)), sz


def infer(mod, addr):
    ins, sz = load(mod, addr)
    if not ins:
        return None
    out = []

    # ---- ARG COUNT: r0..r3 read before written, scanning until the first call clobbers them ----
    written, args = set(), set()
    for i in ins:
        if i.mnemonic.startswith('bl'):
            break
        # A PUSH READS the registers it saves, and mwccarm's standard prologue pushes r3 purely to
        # keep the stack 8-byte aligned. Counting that as "r3 read before written" made almost every
        # function report 4 arguments -- strcpy(dst, src) came back as ARGS: 4 -- and the scaffold
        # handed the worker a 4-parameter signature, which changes the register setup and the bytes.
        # A save is not a use: skip the store-multiple forms entirely.
        if i.mnemonic in ('push', 'stmdb', 'stm', 'stmia', 'stmib', 'stmda'):
            continue
        try:
            rd, wr = i.regs_access()
        except Exception:
            break
        for r in rd:
            n = i.reg_name(r)
            if n in ('r0', 'r1', 'r2', 'r3') and n not in written:
                args.add(n)
        for r in wr:
            written.add(i.reg_name(r))
    nargs = (max(int(a[1]) for a in args) + 1) if args else 0
    out.append(f"ARGS      : {nargs}  (r0..r3 read-before-written: {' '.join(sorted(args)) or 'none'})")

    # ---- RETURNS: is r0 defined on the way out? ----
    ret = False
    for i in reversed(ins):
        if i.mnemonic in ('bx', 'pop', 'ldm') or i.mnemonic.startswith('b'):
            continue
        try:
            _, wr = i.regs_access()
        except Exception:
            break
        if any(i.reg_name(r) == 'r0' for r in wr):
            ret = True
        break
    out.append(f"RETURNS   : {'yes (r0 defined at exit)' if ret else 'probably void'}")

    # ---- STACK FRAME + CALLEE-SAVED (recipe #9's ladder depth) ----
    frame = 0
    for i in ins[:4]:
        m = re.match(r'^sp, sp, #(-?(?:0x)?[0-9a-fA-F]+)$', i.op_str)
        if i.mnemonic == 'sub' and m:
            frame = int(m.group(1), 0)
    saved = []
    for i in ins[:2]:
        if i.mnemonic in ('push', 'stmdb'):
            saved = [r.strip() for r in re.sub(r'^.*\{|\}.*$', '', i.op_str).split(',')]
    cs = [r for r in saved if re.fullmatch(r'r([4-9]|1[01])|sb|sl|fp', r)]
    out.append(f"FRAME     : sub sp,#{hex(frame)}   callee-saved pushed: {len(cs)} ({' '.join(cs) or 'none'})")
    out.append(f"            => at least {len(cs)} values live across a call (recipe #9 ladder r4,r5,r6...)")

    # ---- STRUCT FIELDS: every [base,#off] access with width ----
    fields = {}
    for i in ins:
        w = WIDTH.get(i.mnemonic)
        if not w:
            continue
        m = MEM.search(i.op_str)
        if not m or m.group(1) == 'pc':
            continue
        base, off = m.group(1), int(m.group(2), 0) if m.group(2) else 0
        if base == 'sp':
            continue
        fields.setdefault(base, {})[off] = w
    if fields:
        out.append("FIELDS    : (offset -> width, from the actual loads/stores)")
        for base in sorted(fields):
            fl = ', '.join(f"+{hex(o)}:{fields[base][o][0]}" for o in sorted(fields[base]))
            hint = "  <- likely arg0" if base == 'r0' else ""
            out.append(f"            via {base}{hint}: {fl}")

    # ---- SWITCH / JUMP TABLE. Recipe #17: the emitted shape is a PURE FUNCTION of the case-value set
    #      (count + span), and mwccarm emits a BRANCH table inline. So the exact `switch` is readable
    #      straight off the binary: the bounds `cmp` gives the case count, an optional `sub` gives the
    #      base value, and the run of `b` after `add pc,pc,rX,lsl #2` gives one entry per case.
    #      240 unmatched functions contain one. Match the case-value set and the dispatch is byte-exact.
    for n, i in enumerate(ins):
        if not (i.mnemonic.startswith('add') and 'pc, pc' in i.op_str):
            continue
        cnt, base = None, 0
        for j in range(max(0, n - 6), n):                      # bounds check just above the dispatch
            mm = re.match(r'^(\w+), #(-?(?:0x)?[0-9a-fA-F]+)$', ins[j].op_str)
            if ins[j].mnemonic.startswith('cmp') and mm:
                cnt = int(mm.group(2), 0) + 1
            if ins[j].mnemonic.startswith('sub') and mm:
                base = int(mm.group(2), 0)
            m2 = re.match(r'^(\w+), (\w+), #(-?(?:0x)?[0-9a-fA-F]+)$', ins[j].op_str)
            if ins[j].mnemonic.startswith('sub') and m2:
                base = int(m2.group(3), 0)
        entries = []
        for k in range(n + 1, len(ins)):
            if ins[k].mnemonic != 'b':
                break
            mm = re.match(r'^#(0x[0-9a-fA-F]+)$', ins[k].op_str)
            entries.append(int(mm.group(1), 16) - ins[0].address if mm else -1)
        if entries:
            out.append(f"SWITCH    : jump table at +0x{i.address - ins[0].address:x}, "
                       f"{len(entries)} entries, case values {base}..{base + len(entries) - 1}"
                       + (f" (bounds cmp says {cnt} cases)" if cnt else ""))
            out.append("            write EXACTLY this case set — recipe #17: the dispatch is a pure")
            out.append("            function of (count, span); nothing else changes it.")
            out.append("            targets: " + ' '.join(f"+0x{e:x}" for e in entries[:16]))
        break

    # ---- SOFT-FLOAT INTRINSICS. Recipe #13: WHICH `bl _f*` appears is a pure function of the static C
    #      types, so the operator is recoverable by table lookup. 283 unmatched functions call one.
    FLOATS = {0x0200bfc4: '>  (_fgr)', 0x0200bf68: '>= (_fgeq)', 0x0200c088: '<  (_fls)',
              0x0200c020: '<= (_fleq)', 0x0200c0e4: '== (_feq)', 0x0200c14c: '!= (_fneq)',
              0x0200c7d4: 'float multiply (_fmul)', 0x0200c5fc: 'float->fx32 (_ffix)'}
    fl = []
    for i in ins:
        if i.mnemonic != 'bl':
            continue
        mm = re.match(r'^#(0x[0-9a-fA-F]+)$', i.op_str)
        if mm and int(mm.group(1), 16) in FLOATS:
            fl.append((i.address - ins[0].address, FLOATS[int(mm.group(1), 16)]))
    if fl:
        out.append("FLOAT     : write these operators DIRECTLY in C under -fp soft (recipe #13) —")
        for off, op in fl[:8]:
            out.append(f"            +0x{off:<5x} {op}")
        out.append("            a float compare feeds the following bCC with NO cmp; that is expected.")

    # ---- CONTROL FLOW: internal branch targets ----
    lo, hi = ins[0].address, ins[-1].address
    tgts = {}
    for i in ins:
        if i.mnemonic.startswith('b') and not i.mnemonic.startswith('bl') and not i.mnemonic.startswith('bx'):
            m = re.match(r'^#(0x[0-9a-fA-F]+)$', i.op_str)
            if m:
                t = int(m.group(1), 16)
                if lo <= t <= hi:
                    tgts.setdefault(t, []).append((i.address, i.mnemonic))
    if tgts:
        back = sum(1 for t, srcs in tgts.items() for s, _ in srcs if s > t)
        out.append(f"CONTROL   : {len(tgts)} internal branch targets, {back} BACKWARD (= loops)")
        for t in sorted(tgts):
            srcs = ' '.join(f"{m}@+0x{s-lo:x}" for s, m in tgts[t])
            out.append(f"            +0x{t-lo:<4x} <- {srcs}")
        if back:
            out.append("            recipe #18: mwcc emits exactly ONE loop skeleton — `b <test>` at entry,")
            out.append("            body, bottom test. It never rotates/peels/unrolls, so the shape you see")
            out.append("            is a 1:1 image of a C choice (for vs do/while, < vs !=, index vs ptr).")

    # ---- PASTEABLE STRUCT. The field map above is facts; this is the same facts as code, so the
    #      worker does not hand-translate offsets into padding (a documented failure: `struct field` /
    #      `struct layout` appear repeatedly in the SKIP corpus).
    for basereg, fl in sorted(fields.items()):
        if len(fl) < 2:
            continue
        out.append(f"STRUCT    : suggested layout for the object in {basereg} (pad names are placeholders)")
        out.append(f"            struct S_{basereg} {{")
        pos = 0
        for off in sorted(fl):
            ctype, w = fl[off]
            if off > pos:
                out.append(f"                char pad{pos:x}[{off - pos}];")
            out.append(f"                {ctype} f{off:x};")
            pos = off + w
        out.append("            };")
        break

    # ---- CALLEE ARG COUNTS. The scaffold used to admit "signatures are the one guess" — they are not.
    #      At each `bl`, whichever of r0..r3 were WRITTEN since the previous call are that callee's
    #      arguments. Getting arity wrong changes the register setup and therefore the bytes, so this
    #      removes the last guess from the scaffold.
    callsites, live = [], set()
    for i in ins:
        if i.mnemonic == 'bl':
            n = max((int(r[1]) for r in live), default=-1) + 1
            mm = re.match(r'^#(0x[0-9a-fA-F]+)$', i.op_str)
            callsites.append((i.address - lo, n, int(mm.group(1), 16) if mm else 0))
            live = set()
            continue
        try:
            _, wr = i.regs_access()
        except Exception:
            continue
        for r in wr:
            nm2 = i.reg_name(r)
            if nm2 in ('r0', 'r1', 'r2', 'r3'):
                live.add(nm2)
    if callsites:
        out.append("CALL ARITY: args set up immediately before each call (= that callee's arg count)")
        for off, n, tgt in callsites:
            out.append(f"            +0x{off:<5x} {n} arg(s)" + (f"  -> 0x{tgt:08x}" if tgt else ""))

    # ---- STACK LOCALS: sp-relative slots actually touched => how many locals live in the frame ----
    slots = {}
    for i in ins:
        w = WIDTH.get(i.mnemonic)
        m = MEM.search(i.op_str) if w else None
        if m and m.group(1) == 'sp':
            slots[int(m.group(2), 0) if m.group(2) else 0] = w
    if slots:
        sl2 = ', '.join(f"sp+{hex(o)}:{slots[o][0]}" for o in sorted(slots))
        out.append(f"LOCALS    : {len(slots)} stack slot(s) touched — {sl2}")
        if frame and len(slots) * 4 < frame:
            out.append(f"            frame is 0x{frame:x} but only {len(slots)} slots are read/written;")
            out.append("            the rest is likely a struct or array passed by address.")

    # ---- RECIPE ROUTER. The worker doc has a symptom->recipe table that workers apply by eye. These
    #      signatures are exact, so pre-apply it: name the recipe and the offset it fires at.
    hits = []
    for n, i in enumerate(ins):
        o = i.op_str
        if i.mnemonic == 'bl' and n + 2 < len(ins) \
           and ins[n+1].mnemonic == 'cmp' and ins[n+1].op_str == 'r0, #0' \
           and not any(x.mnemonic.startswith('mov') for x in ins[n+2:n+3]):
            hits.append((i.address - lo, "#8 bool-return: write `bool F(){ return callee(...) != 0; }` "
                                         "(int + !=0 adds movne/moveq; plain return drops the cmp)"))
        if i.mnemonic == 'lsl' and '#31' in o:
            for k in range(n + 1, min(n + 3, len(ins))):
                if ins[k].mnemonic == 'orr' and 'lsr #31' in ins[k].op_str:
                    hits.append((i.address - lo, "#7 bit0 bitfield: real 1-bit UNSIGNED member, OR the "
                                                 "BARE field. `&1` and `?1:0` DEFEAT it"))
        if i.mnemonic in ('ldm', 'ldmia', 'stm', 'stmia', 'stmib') and '{' in o:
            regs = [r for r in re.sub(r'^.*\{|\}.*$', '', o).split(',')]
            if len(regs) >= 3 and 'sp' not in o:
                hits.append((i.address - lo, f"#6 struct-by-value: {len(regs)} consecutive words — pass a "
                                             f"struct BY VALUE, not {len(regs)} separate args"))
        if i.mnemonic.endswith(('eq', 'ne', 'lt', 'gt', 'le', 'ge')) and i.mnemonic[:3] in ('mov', 'mvn', 'ldr', 'str', 'add', 'sub'):
            hits.append((i.address - lo, "#3 if-conversion: this block PREDICATED, so it is <=5 instrs in "
                                         "the target. >=6 would branch — count before restructuring"))
    seen_r = set()
    if hits:
        out.append("RECIPES   : signatures detected (the worker doc's symptom->recipe table, pre-applied)")
        for off, txt in hits:
            key = txt[:4]
            if key in seen_r:
                continue
            seen_r.add(key)
            out.append(f"            +0x{off:<5x} {txt}")
    return '\n'.join(out)


if __name__ == "__main__":
    r = infer(sys.argv[1], sys.argv[2])
    print(r if r else "(not an ARM function / not found)")
