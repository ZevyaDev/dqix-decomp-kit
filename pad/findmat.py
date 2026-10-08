"""Find committed functions whose ROM keeps a derived pointer `add rA, rB, #imm` in its own callee-saved
register while the base rB dies, the shape our build refuses (it re-forms `rB + imm` at every use).

Usage: python findmat.py [imm_hex]
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import os
import re
import sys

import capstone
from capstone import arm

REPO = _kp.REPO
CALLEE = {arm.ARM_REG_R4, arm.ARM_REG_R5, arm.ARM_REG_R6, arm.ARM_REG_R7, arm.ARM_REG_R8,
          arm.ARM_REG_R9, arm.ARM_REG_R10, arm.ARM_REG_R11}
LOW = {arm.ARM_REG_R0, arm.ARM_REG_R1, arm.ARM_REG_R2, arm.ARM_REG_R3}
want_imm = int(sys.argv[1], 16) if len(sys.argv) > 1 else None

md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
md.detail = True
md.skipdata = True


def modules():
    yield "main", f"{REPO}/{buildcfg.config_root()}/delinks.txt", f"{REPO}/{buildcfg.extract_root()}/arm9/arm9.bin"
    for d in sorted(os.listdir(f"{REPO}/{buildcfg.config_root()}/overlays")):
        yield d, f"{REPO}/{buildcfg.config_root()}/overlays/{d}/delinks.txt", f"{REPO}/{buildcfg.extract_root()}/arm9_overlays/{d}.bin"


def ranges(cfg):
    text = open(cfg).read()
    base = min(int(x, 16) for x in re.findall(r"start:0x([0-9a-fA-F]+)", text))
    out = []
    for block in re.split(r"\n(?=\S)", text):
        head = block.split("\n", 1)[0].strip()
        if not head.endswith(".cpp:"):
            continue
        for a, b in re.findall(r"\.text start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)", block):
            out.append((head[:-1], int(a, 16), int(b, 16)))
    return base, out


def scan(ins):
    hits = []
    for i in range(1, len(ins)):
        if ins[i].mnemonic != "mov" or ins[i - 1].mnemonic != "bl":
            continue
        ops = ins[i].operands
        if len(ops) != 2 or ops[1].type != arm.ARM_OP_REG or ops[1].reg != arm.ARM_REG_R0:
            continue
        rb = ops[0].reg
        if rb not in CALLEE:
            continue
        for j in range(i + 1, min(i + 12, len(ins))):
            o = ins[j].operands
            if ins[j].mnemonic == "add" and len(o) == 3 and o[1].type == arm.ARM_OP_REG and o[1].reg == rb \
                    and o[2].type == arm.ARM_OP_IMM and o[0].reg in CALLEE and o[0].reg != rb:
                if want_imm is not None and o[2].imm != want_imm:
                    continue
                ra = o[0].reg
                rb_dead = None
                uses = 0
                for k in range(j + 1, len(ins)):
                    try:
                        rd, wr = ins[k].regs_access()
                    except capstone.CsError:
                        continue
                    if rb_dead is None:
                        if rb in rd:
                            rb_dead = False
                        elif rb in wr:
                            rb_dead = True
                    ok = ins[k].operands
                    if ins[k].mnemonic == "mov" and len(ok) == 2 and ok[1].type == arm.ARM_OP_REG \
                            and ok[1].reg == ra and ok[0].reg in LOW:
                        uses += 1
                if rb_dead and uses >= 2:
                    hits.append((ins[j].address, ins[i].address, uses))
                break
    return hits


for mod, cfg, binp in modules():
    if not os.path.exists(cfg) or not os.path.exists(binp):
        continue
    blob = open(binp, "rb").read()
    base, rs = ranges(cfg)
    for path, a, b in rs:
        code = blob[a - base:b - base]
        ins = [x for x in md.disasm(code, a) if x.id != 0]
        for add_at, mov_at, uses in scan(ins):
            print(f"{mod} {path} add@{add_at:08x} uses={uses}")
