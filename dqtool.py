#!/usr/bin/env python3
"""Analysis tools for the DQIX decomp, as subcommands. NOT part of the autonomous pipeline.

    python dqtool.py dis    <main|NNN> <addr>          disassemble the TARGET bytes of a function
    python dqtool.py obj    <file.o> [name-substr]     disassemble every function symbol in an .o
    python dqtool.py count  '<regex>[;<regex>...]'     how many UNMATCHED functions contain a pattern
    python dqtool.py find   '<regex>[;<regex>...]'     which COMMITTED functions contain it (exemplars)
    python dqtool.py named  [main|NNN] [maxsize]       ROM functions with a curated name, not yet done
    python dqtool.py staged [module ...]               how much staged work is actually NEW
    python dqtool.py stubs                             how much of the parked pool is unwritten stubs

Each of these was its own file (tdis.py, odis_syms.py, countpat.py, findpat.py, namedtodo.py,
staged_value.py, stubcount.py). They share the same config parsing and are used the same way -- by
hand, while investigating -- so they belong in one place with one `--help`. The pipeline never
calls them, which is why collapsing them carries no risk to a running wave.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import glob
import os
import re
import sys

REPO = _kp.REPO
SP = _kp.SP
KIT = _kp.KIT


def cfg_for(mod):
    """(config dir, pristine binary, load base) for a module."""
    if mod == "main":
        cfg = f"{REPO}/{buildcfg.config_root()}"
        rom = open(f"{REPO}/{buildcfg.extract_root()}/arm9/arm9.bin", "rb").read()
        return cfg, rom, 0x02000000
    cfg = f"{REPO}/{buildcfg.config_root()}/overlays/ov{mod}"
    rom = open(f"{REPO}/{buildcfg.extract_root()}/arm9_overlays/ov{mod}.bin", "rb").read()
    base = min(int(m, 16) for m in
               re.findall(r"start:0x([0-9a-fA-F]+)", open(f"{cfg}/delinks.txt").read()))
    return cfg, rom, base


def done_ranges(cfg):
    """Address ranges already covered by a delinked file (per-file entries only, never the
    section-table rows -- those are anchored differently: a file entry ends at the address)."""
    d = open(f"{cfg}/delinks.txt", encoding="utf-8", errors="ignore").read()
    return [(int(a, 16), int(b, 16)) for a, b in
            re.findall(r"(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$", d)]


def functions(cfg):
    """[(name, isa, size, addr)] for every function symbol in a module."""
    out = []
    for m in re.finditer(r"(?m)^(\S+)\s+kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\)\s+addr:0x([0-9a-fA-F]+)",
                         open(f"{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()):
        out.append((m.group(1), m.group(2), int(m.group(3), 16), int(m.group(4), 16)))
    return out


def cmd_dis(argv):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
    mod, addr = argv[0], argv[1]
    cfg, rom, base = cfg_for(mod)
    hit = next((f for f in functions(cfg) if f[3] == int(addr, 16)), None)
    if not hit:
        print("NO-SLOT: nothing at that address"); return 1
    name, isa, size, a = hit
    data = rom[a - base:a - base + size]
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if isa == "thumb" else CS_MODE_ARM)
    print(f"{name}  {isa}  size=0x{size:x}")
    for i in md.disasm(data, 0):
        print(f"  0x{i.address:04x}  {i.mnemonic} {i.op_str}".rstrip())
    return 0


def cmd_obj(argv):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
    from elftools.elf.elffile import ELFFile
    path = argv[0]
    want = argv[1] if len(argv) > 1 else ""
    with open(path, "rb") as fh:
        elf = ELFFile(fh)
        md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
        for sym in elf.get_section_by_name(".symtab").iter_symbols():
            if sym["st_info"]["type"] != "STT_FUNC" or not sym.name or want not in sym.name:
                continue
            sec = elf.get_section(sym["st_shndx"])
            data = sec.data()[sym["st_value"]:sym["st_value"] + (sym["st_size"] or len(sec.data()))]
            print(f"{sym.name}  size=0x{len(data):x}")
            for i in md.disasm(data, 0):
                print(f"    0x{i.address:04x}  {i.mnemonic} {i.op_str}".rstrip())
    return 0


def _decode(mod, addr, size, isa, rom, base):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if isa == "thumb" else CS_MODE_ARM)
    return [f"{i.mnemonic} {i.op_str}".strip()
            for i in md.disasm(rom[addr - base:addr - base + size], 0)]


def _scan(pattern, want_matched):
    """Walk every module, decode each function, report those whose instructions match `pattern`
    (a ';'-separated sequence of per-instruction regexes)."""
    pats = [re.compile(p) for p in pattern.split(";")]
    mods = ["main"] + sorted(re.search(r"ov(\d+)", p).group(1)
                             for p in glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/ov*"))
    hits, scanned = [], 0
    for mod in mods:
        try:
            cfg, rom, base = cfg_for(mod)
        except OSError:
            continue
        rngs = done_ranges(cfg)
        for name, isa, size, addr in functions(cfg):
            matched = any(s <= addr < e for s, e in rngs)
            if matched != want_matched:
                continue
            scanned += 1
            ins = _decode(mod, addr, size, isa, rom, base)
            for i in range(len(ins) - len(pats) + 1):
                if all(p.search(ins[i + k]) for k, p in enumerate(pats)):
                    hits.append((mod, name, addr, size))
                    break
    return hits, scanned


def cmd_count(argv):
    hits, scanned = _scan(argv[0], want_matched=False)
    per = {}
    for mod, _n, _a, _s in hits:
        per[mod] = per.get(mod, 0) + 1
    print(f"unmatched functions scanned: {scanned}")
    print(f"containing the pattern:      {len(hits)}")
    for mod, n in sorted(per.items(), key=lambda kv: -kv[1]):
        print(f"   {mod}: {n}")
    return 0


def cmd_find(argv):
    hits, scanned = _scan(argv[0], want_matched=True)
    for mod, name, addr, size in hits[:20]:
        print(f"   ({mod!r}, {name!r}, {hex(addr)}, {hex(size)})")
    print(f"{len(hits)} hits across {scanned} matched functions")
    return 0


def cmd_named(argv):
    mod = argv[0] if argv else "main"
    maxsize = int(argv[1], 0) if len(argv) > 1 else 0x400
    cfg, _rom, _base = cfg_for(mod)
    rngs = done_ranges(cfg)
    rows = [(sz, a, isa, n) for n, isa, sz, a in functions(cfg)
            if not n.startswith("func_") and sz and sz <= maxsize
            and not any(s <= a < e for s, e in rngs)]
    for sz, a, isa, n in sorted(rows):
        print(f"{mod:<5} 0x{a:08x}  {isa:<5} size=0x{sz:<4x}  {n}")
    print(f"{len(rows)} named-but-undecompiled functions <= 0x{maxsize:x} bytes")
    return 0


def cmd_staged(argv):
    total = 0
    for d in sorted(glob.glob(f"{SP}/staging/*/")):
        name = os.path.basename(d.rstrip("/\\"))
        mod = "main" if name == "main" else name.replace("ov", "")
        if argv and mod not in argv:
            continue
        try:
            cfg, _rom, _base = cfg_for(mod)
        except OSError:
            continue
        rngs = done_ranges(cfg)
        seen, new, dup, done, untagged = set(), [], 0, 0, 0
        for f in sorted(glob.glob(d + "*.cpp")):
            m = re.search(r"// USA: func_(?:ov\d+_)?([0-9a-fA-F]{8})",
                          open(f, encoding="utf-8", errors="ignore").read())
            if not m:
                untagged += 1
                continue
            a = m.group(1).lower()
            v = int(a, 16)
            if any(s <= v < e for s, e in rngs):
                done += 1
            elif a in seen:
                dup += 1
            else:
                seen.add(a)
                new.append(a)
        total += len(new)
        print(f"{mod:<6} {len(glob.glob(d + '*.cpp')):3d} files -> {len(new):3d} NEW, "
              f"{done} delinked, {dup} dup, {untagged} untagged")
    print(f"\nTOTAL NEW ADDRESSES WAITING: {total}")
    return 0


def cmd_stubs(_argv):
    body = re.compile(r"\)\s*\{(.*)\}\s*$", re.S)
    stub = real = 0
    per = {}
    for f in glob.glob(f"{SP}/**/*.cpp", recursive=True):
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        m = body.search(txt)
        code = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", m.group(1) if m else "", flags=re.S)).strip()
        d = os.path.basename(os.path.dirname(f))
        isstub = (not code) or code in (";", "return;")
        per.setdefault(d, [0, 0])[0 if isstub else 1] += 1
        stub += isstub
        real += not isstub
    for d, (s, r) in sorted(per.items(), key=lambda kv: -kv[1][0])[:12]:
        print(f"  {d:<28} {s:5d} stub / {r:5d} real")
    print(f"\nTOTAL: {stub} stubs, {real} real ({100.0 * stub / max(1, stub + real):.0f}% stubs)")
    return 0


CMDS = {"dis": cmd_dis, "obj": cmd_obj, "count": cmd_count, "find": cmd_find,
        "named": cmd_named, "staged": cmd_staged, "stubs": cmd_stubs}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(2)
    os.chdir(REPO)
    sys.exit(CMDS[sys.argv[1]](sys.argv[2:]))
