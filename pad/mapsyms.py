import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import glob
import re
import sys

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection

REPO = _kp.REPO
CFG = REPO + "/" + buildcfg.config_root()


def tables():
    by_module, committed = {}, set()
    for p in [CFG + "/symbols.txt"] + glob.glob(CFG + "/overlays/*/symbols.txt"):
        mod = "main" if p == CFG + "/symbols.txt" else "overlay(%d)" % int(re.search(r"ov(\d+)", p).group(1))
        table = by_module.setdefault(mod, {})
        for line in open(p, encoding="utf-8", errors="ignore"):
            m = re.match(r"(\S+) kind:(\w+)\S* addr:0x([0-9a-fA-F]{8})", line)
            if m:
                committed.add(m.group(1))
                addr = int(m.group(3), 16)
                if m.group(2) == "function" or addr not in table:
                    table[addr] = m.group(1)
    return by_module, committed


def rom_relocs(mod):
    path = CFG + ("/relocs.txt" if mod == "main" else "/overlays/ov%03d/relocs.txt" % int(mod))
    rom = {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"from:0x([0-9a-fA-F]+) kind:(\S+) to:0x([0-9a-fA-F]+) module:(\S+)", line)
        if m:
            rom[int(m.group(1), 16)] = (m.group(2), int(m.group(3), 16), m.group(4))
    return rom


def mapsyms(mod, obj, func, base):
    by_module, committed = tables()
    rom = rom_relocs(mod)
    seen = {}
    with open(obj, "rb") as f:
        elf = ELFFile(f)
        symtab = elf.get_section_by_name(".symtab")
        fsym = next(s for s in symtab.iter_symbols() if s.name == func)
        fsec, fstart, fsize = fsym["st_shndx"], fsym["st_value"], fsym["st_size"]
        for sec in elf.iter_sections():
            if not isinstance(sec, RelocationSection) or sec["sh_info"] != fsec:
                continue
            for r in sec.iter_relocations():
                off = r["r_offset"] - fstart
                if not 0 <= off < fsize:
                    continue
                s = symtab.get_symbol(r["r_info_sym"])
                if s["st_shndx"] != "SHN_UNDEF" or s.name in committed:
                    continue
                hit = rom.get(base + off)
                if hit is None:
                    seen.setdefault(s.name, set()).add("offset 0x%x: NO ROM RELOC" % off)
                    continue
                _kind, to, tmod = hit
                seen.setdefault(s.name, set()).add(
                    "%s 0x%08x %s" % (tmod, to, by_module.get(tmod, {}).get(to, "?")))
    return seen


if __name__ == "__main__":
    mod, obj, func, base = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4], 16)
    for name, hits in sorted(mapsyms(mod, obj, func, base).items()):
        print(name, "->", " | ".join(sorted(hits)))
