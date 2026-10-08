#!/usr/bin/env python3
"""Emit an `asm` function that reproduces a ROM function instruction-for-instruction.

    python asmgen.py <main|NNN> <addr> [Name] > out.cpp

FOR HAND-WRITTEN SDK ASSEMBLY ONLY. Most functions are C and must be decompiled as C -- this is
the endgame tool for the routines that provably have no C form, and it exists so that "needs asm"
means "write it now", not "skiplist it and burn a worker on every sibling later".

The evidence that a given function is SDK asm is concrete, not a hunch: pret/pokediamond carries
the same NitroSDK routines as `asm void ...` in arm9/lib/NitroSDK/src/MI_memory.c, and DQIX's
MI_CpuFill8 (VectorizedMemset) matches theirs instruction for instruction. DQIX's SDK build differs
from pokediamond's in one mechanical way: it spells every PREDICATED instruction as an explicit
branch pair (`ldrneh r3,[r0,#-1]` becomes `bne L; b M; L: ldrh r3,[r0,#-1]`), which is why no C
form and no compiler flag ever reproduced it.

REFUSES rather than guesses: a function containing a PC-relative literal load is rejected, because
the assembler places its own literal pool and that changes the layout -- those need a hand-written
`ldr rN, =value` and a size check, so they are not safe to auto-generate.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import re
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

REPO = _kp.REPO


CONDS = {"eq", "ne", "cs", "hs", "cc", "lo", "mi", "pl",
         "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le", "al"}


def is_local_branch(mn):
    """True for `b` and `b<cond>`, false for bl / bl<cond> / blx / bx.

    Testing `startswith("bl")` is WRONG and cost a compile: `blo`, `blt` and `bls` are
    branch-if-lower / less-than / lower-or-same, not branch-with-link, so their targets were left
    as raw addresses and the assembler rejected them.
    """
    return mn == "b" or (len(mn) == 3 and mn[0] == "b" and mn[1:] in CONDS)


SHIFTS = ("lsl", "lsr", "asr", "ror")

# capstone prints the AAPCS register aliases; mwccarm's inline assembler knows ip, sp, lr and pc but
# not these three, and rejects the operand rather than the mnemonic, so the error names a line that
# looks perfectly ordinary.
ALIASES = {"sb": "r9", "sl": "r10", "fp": "r11"}
ALIAS_RE = re.compile(r"\b(%s)\b" % "|".join(ALIASES))


def normalise(mn, op):
    """Rewrite capstone's disassembly into what mwccarm's inline assembler accepts.

    capstone prints the shift pseudo-instructions in their standalone UAL form (`lsr r3, ip, #8`),
    but this assembler only takes the canonical ARM encoding, where a shift is an operand of MOV:
    `mov r3, ip, lsr #8`. Same for the flag-setting forms. Everything else passes through, so an
    unhandled mnemonic fails loudly at assembly time rather than silently producing wrong bytes.
    """
    # The suffixes come off in the order ARM spells them: `lsrles` is lsr + le + s. Peeling only `s`
    # left every PREDICATED shift (`lsrle r3, r3, #0x10`) to reach the assembler as a mnemonic it has
    # never heard of, which is what stopped the MSL division helpers assembling.
    op = ALIAS_RE.sub(lambda m: ALIASES[m.group(1)], op)
    # capstone names the ARM status register APSR; mwasmarm only knows CPSR.
    op = re.sub(r"\bapsr\b", "cpsr", op)
    # capstone prints the default addressing mode as no suffix at all; mwasmarm has no bare `ldm`.
    m = re.match(r"^(ldm|stm)(%s)?$" % "|".join(CONDS), mn)
    if m:
        return m.group(1) + (m.group(2) or "") + "ia", op
    # push/pop are UAL spellings of the stack forms of stm/ldm; mwasmarm only knows the ARM ones.
    m = re.match(r"^(push|pop)(%s)?$" % "|".join(CONDS), mn)
    if m:
        cond = m.group(2) or ""
        return ("stmdb" if m.group(1) == "push" else "ldmia") + cond, f"sp!, {op}"
    rest, setflags = (mn[:-1], "s") if mn.endswith("s") and mn[:-1] not in SHIFTS else (mn, "")
    cond = ""
    for c in CONDS:
        if rest.endswith(c) and rest[:-len(c)] in SHIFTS:
            rest, cond = rest[:-len(c)], c
            break
    if rest in SHIFTS:
        parts = [p.strip() for p in op.split(",")]
        if len(parts) == 3:
            return f"mov{cond}{setflags}", f"{parts[0]}, {parts[1]}, {rest} {parts[2]}"
    return mn, op


def load(mod, addr):
    if mod == "main":
        cfg = f"{REPO}/{buildcfg.config_root()}"
        rom = open(f"{REPO}/{buildcfg.pristine('main')}", "rb").read()
        base = 0x02000000
    else:
        cfg = f"{REPO}/{buildcfg.config_dir(mod)}"
        rom = open(f"{REPO}/{buildcfg.pristine(mod)}", "rb").read()
        base = min(int(x, 16) for x in
                   re.findall(r"start:0x([0-9a-fA-F]+)", open(f"{cfg}/delinks.txt").read()))
    sym = open(f"{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()
    m = re.search(r"(?m)^(\S+)\s+kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\)\s+addr:0x0*%s\b"
                  % addr.lstrip("0"), sym)
    if not m:
        sys.exit(f"NO-SLOT: nothing at {addr}")
    if m.group(2) != "arm":
        sys.exit("THUMB functions are not supported by this generator")
    name, size = m.group(1), int(m.group(3), 16)
    a = int(addr, 16)
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    return name, size, a, list(md.disasm(rom[a - base:a - base + size], a))


PCREL = re.compile(r"\[pc, #(-?(?:0x)?[0-9a-fA-F]+)\]")


def pc_target(i):
    """Address a PC-relative load reads, or None. ARM's PC reads as the instruction address + 8."""
    m = PCREL.search(i.op_str)
    return None if not m else (i.address & ~3) + 8 + int(m.group(1), 0)


def emit_s(mod, addr, name, sym, size, a, ins, prov):
    """A standalone mwasmarm source, for the routines mwcc's inline assembler cannot express.

    Three things only the real assembler can do, and each of them blocked a whole family:
    instructions the inline assembler has never heard of (`swpb`); a label after `bx lr`, which the
    inline assembler reads as a redefined data object; and EXPORTING AN INTERIOR LABEL. The last is
    what makes a function like _u32_div_f landable at all -- something outside branches to a label
    in the middle of it, and if that label is not exported the linker resolves the branch through
    an interworking veneer, which is 8 bytes that shift every module after it.
    """
    words = {i.address: i for i in ins}
    externs = set()
    pool = {t for t in (pc_target(i) for i in ins) if t is not None and a <= t < a + size}
    labels = {}
    for i in ins:
        m = re.match(r"^#(0x[0-9a-fA-F]+)$", i.op_str)
        if m and is_local_branch(i.mnemonic):
            t = int(m.group(1), 16)
            if a <= t < a + size:
                labels.setdefault(t, "_L%x" % (t - a))
    for t in pool:
        labels.setdefault(t, "_P%x" % (t - a))

    out = [f"// {name} at 0x{addr} is hand-written library assembly, transcribed",
           "// instruction-for-instruction from the ROM. It is not un-decompiled C."]
    if prov:
        out += ["//", f"// PROVENANCE: {prov}"]
    out += ["//",
            "// Assembly rather than an mwccarm `asm` block because the inline assembler cannot",
            "// express this one. Mnemonics are the canonical ARM spellings mwasmarm accepts.",
            "", "\t.section .text", "\t.arm", ""]
    for g in exported(mod, a, size):
        out.append(f"\t.global {g}")
    out.append("")
    for off in range(0, size, 4):
        at = a + off
        if at in labels and at not in pool:
            out.append(f"{labels[at]}:")
        for g in exported_at(mod, at):
            out.append(f"{g}:")
        if at in pool:
            i = words.get(at)
            out.append(f"{labels[at]}:")
            out.append("\t.word 0x%08x" % (i.bytes[0] | i.bytes[1] << 8 | i.bytes[2] << 16
                                           | i.bytes[3] << 24) if i else "\t.word 0")
            continue
        i = words.get(at)
        if i is None:
            sys.exit(f"REFUSING: no instruction decoded at +0x{off:x}")
        op = i.op_str
        m = re.match(r"^#(0x[0-9a-fA-F]+)$", op)
        if m and int(m.group(1), 16) in labels:
            op = labels[int(m.group(1), 16)]
        elif m and i.mnemonic.startswith("b"):
            # A BRANCH OUT OF THE FUNCTION NEEDS THE CALLEE'S NAME. Left as a raw address the
            # assembler rejects it outright, and these library routines tail-call each other
            # constantly.
            names = exported_at(mod, int(m.group(1), 16))
            if not names:
                sys.exit("REFUSING: branch to 0x%x at +0x%x, which no symbol names"
                         % (int(m.group(1), 16), i.address - a))
            op = names[0]
            externs.add(names[0])
        elif pc_target(i) is not None and pc_target(i) in labels:
            op = PCREL.sub(labels[pc_target(i)], op)
        mn, op = normalise(i.mnemonic, op)
        out.append(f"\t{mn} {op}".rstrip())
    if externs:
        at = out.index("\t.arm") + 1
        out[at:at] = [f"\t.extern {e}" for e in sorted(externs)]
    print("\n".join(out))


def symbols_text(mod):
    cfg = f"{REPO}/{buildcfg.config_dir(mod)}"
    return open(f"{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()


SYMLINE = re.compile(r"(?m)^(\S+)\s+kind:(?:function|data|label)[^\s]*\s+addr:0x([0-9a-fA-F]+)")


def exported(mod, a, size):
    return [n for n, v in ((m.group(1), int(m.group(2), 16))
                           for m in SYMLINE.finditer(symbols_text(mod))) if a <= v < a + size]


def exported_at(mod, at):
    return [n for n, v in ((m.group(1), int(m.group(2), 16))
                           for m in SYMLINE.finditer(symbols_text(mod))) if v == at]


def main():
    want_s = "--s" in sys.argv
    args = [x for x in sys.argv[1:] if x != "--s"]
    mod, addr = args[0], args[1]
    sym, size, a, ins = load(mod, addr)
    name = args[2] if len(args) > 2 else sym
    if want_s:
        return emit_s(mod, addr, name, sym, size, a, ins,
                      args[4] if len(args) > 4 else "")
    if len(ins) * 4 != size:
        sys.exit(f"REFUSING: {len(ins)} instructions do not cover 0x{size:x} bytes "
                 f"(literal pool or undecodable data inside the function). Try --s.")
    for i in ins:
        if "[pc" in i.op_str:
            sys.exit("REFUSING: PC-relative literal load at +0x%x. The inline assembler places its "
                     "own pool, which changes the layout -- use --s, which emits the word itself."
                     % (i.address - a))

    # Branch targets inside the function become labels.
    labels = {}
    for i in ins:
        m = re.match(r"^#(0x[0-9a-fA-F]+)$", i.op_str)
        if m and is_local_branch(i.mnemonic):
            t = int(m.group(1), 16)
            if a <= t < a + size:
                labels.setdefault(t, "_L%x" % (t - a))

    # SIGNATURE, not `(void)`. These routines have real parameters and the reference decomps state
    # them; emitting `(void)` throws that away and leaves a file nobody can read or call. Pass the
    # signature from the reference source (see PROVENANCE below) as argv[4].
    sig = args[3] if len(args) > 3 else "void"
    prov = args[4] if len(args) > 4 else ""
    out = ["#include <globaldefs.h>", "",
           "// KEEP-NAME: the ROM symbol is a curated name, not a func_ tag.",
           f"// USA: func_{addr}",
           "//",
           "// Hand-written SDK assembly, transcribed instruction-for-instruction from the ROM.",
           "// It is not un-decompiled C: no C form reaches it, because DQIX's SDK build spells every",
           "// PREDICATED instruction as an explicit branch pair (`ldrneh r3,[r0,#-1]` becomes",
           "// `bne L; b M; L: ldrh r3,[r0,#-1]`), which is also why the reference decomp's own asm",
           "// does not assemble to these bytes -- theirs is ~20 instructions shorter for that reason."]
    if prov:
        out += ["//", f"// PROVENANCE: {prov}"]
    # C LINKAGE. mwcc mangles an asm function like any other, so the object exported
    # _Z16VectorizedMemsetv while the config binds VectorizedMemset, and the link failed on a file
    # whose bytes were already exact.
    out += ["extern \"C\" ARM", f"asm void {name}({sig})", "{"]
    for i in ins:
        if i.address in labels:
            out.append(f"{labels[i.address]}:")
        op = i.op_str
        m = re.match(r"^#(0x[0-9a-fA-F]+)$", op)
        if m and is_local_branch(i.mnemonic):
            t = int(m.group(1), 16)
            if t in labels:
                op = labels[t]
        mn, op = normalise(i.mnemonic, op)
        out.append(f"    {mn} {op}".rstrip())
    out.append("}")
    print("\n".join(out))


if __name__ == "__main__":
    main()
