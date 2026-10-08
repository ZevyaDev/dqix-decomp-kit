#!/usr/bin/env python
"""Find pool words that hold an overlay ID and give them a `kind:overlay_id` relocation.

The SDK writes an overlay ID as the address of the LCF symbol `OVERLAY_<n>_ID`, so mwcc pools it
and no C constant reproduces the load. A site qualifies when a pooled value below the overlay count
reaches a known overlay-ID parameter unclobbered.

Usage: python ovidrelocs.py [--apply]
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import glob, os, re, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from capstone.arm import ARM_OP_REG

REPO = _kp.REPO
APPLY = "--apply" in sys.argv
OVERLAY_COUNT = 0x23
CONSUMERS = {
    0x020a1940: "r0",
    0x020a1bb4: "r0",
    0x020a18f4: "r0",
    0x0202fd44: "r1",
    0x021b2bd0: "r2",
}
CALL_CLOBBERS = {"r0", "r1", "r2", "r3", "r12", "lr"}

md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
md.detail = True
PC = re.compile(r'\[pc, #(-?(?:0x)?[0-9a-fA-F]+)\]')


def module_sites(cfg, binpath, base):
    sym = open(f"{REPO}/{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()
    blob = open(f"{REPO}/{binpath}", "rb").read()
    sites = []
    for m in re.finditer(r'^(\S+) kind:function\(arm,size=0x([0-9a-fA-F]+)\) addr:0x([0-9a-fA-F]+)', sym, re.M):
        size = int(m.group(2), 16)
        func = int(m.group(3), 16)
        body = blob[func - base:func - base + size]
        if len(body) != size:
            continue
        ins = list(md.disasm(body, func))
        for k, i in enumerate(ins):
            if not i.mnemonic.startswith("ldr"):
                continue
            mm = PC.search(i.op_str)
            if not mm:
                continue
            pool = i.address + 8 + int(mm.group(1), 0)
            if not (func <= pool and pool + 4 <= func + size):
                continue
            value = int.from_bytes(blob[pool - base:pool - base + 4], "little")
            if value >= OVERLAY_COUNT:
                continue
            tracked = {i.reg_name(i.operands[0].reg)}
            for j in ins[k + 1:k + 48]:
                if j.mnemonic == "bl":
                    if CONSUMERS.get(j.operands[0].imm) in tracked:
                        sites.append((pool, value, func))
                        break
                    tracked -= CALL_CLOBBERS
                elif j.mnemonic in ("b", "bx", "blx") or j.mnemonic.startswith(("pop", "ldm")):
                    break
                else:
                    written = {j.reg_name(r) for r in j.regs_access()[1]}
                    copied = (j.mnemonic == "mov" and len(j.operands) == 2 and j.operands[1].type == ARM_OP_REG
                              and j.reg_name(j.operands[1].reg) in tracked)
                    tracked -= written
                    if copied:
                        tracked |= written
                if not tracked:
                    break
    return sites


def modules():
    yield "main", buildcfg.config_dir("main"), buildcfg.pristine('main'), 0x02000000
    for d in sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/ov*")):
        ov = os.path.basename(d)
        binpath = buildcfg.pristine(ov[2:])
        if not os.path.exists(f"{REPO}/{binpath}"):
            continue
        delinks = open(f"{d}/delinks.txt").read()
        base = min(int(x, 16) for x in re.findall(r'start:0x([0-9a-fA-F]+)', delinks))
        yield ov, buildcfg.config_dir(ov[2:]), binpath, base


total = 0
for name, cfg, binpath, base in modules():
    sites = module_sites(cfg, binpath, base)
    if not sites:
        continue
    path = f"{REPO}/{cfg}/relocs.txt"
    lines = open(path, encoding="utf-8").read().splitlines()
    existing = {}
    for n, line in enumerate(lines):
        m = re.match(r'from:0x([0-9a-fA-F]+) ', line)
        if m:
            existing[int(m.group(1), 16)] = n
    new = []
    for pool, value, func in sites:
        if pool in existing:
            if "kind:overlay_id" not in lines[existing[pool]]:
                print(f"{name} {pool:08x} CONFLICT {lines[existing[pool]]}")
            continue
        new.append((pool, f"from:0x{pool:08x} kind:overlay_id to:{value} module:none"))
    funcs = sorted({f for _, _, f in sites})
    print(f"{name}: {len(sites)} sites, {len(new)} new, functions {' '.join(f'{f:08x}' for f in funcs)}")
    total += len(new)
    if APPLY and new:
        entries = [(int(re.match(r'from:0x([0-9a-fA-F]+)', l).group(1), 16), l) for l in lines if l.startswith("from:")]
        others = [l for l in lines if not l.startswith("from:")]
        entries += new
        entries.sort(key=lambda e: e[0])
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for l in others:
                fh.write(l + "\n")
            for _, l in entries:
                fh.write(l + "\n")
print(f"new relocations: {total}{'' if APPLY else ' (dry run)'}")
