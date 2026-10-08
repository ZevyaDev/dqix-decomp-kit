import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
# Preflight for the mwldarm link: verify no dsd-delinked gap module has
#     sum(symbol sizes in a section)  >  section size
# mwldarm hard-errors on that with a misleading message that names neither the symbol nor the cause:
#     mwldarm: In section .text in file main_5.o , the sum of all symbol sizes exceed section size.
#     This is most likely cause by code generation bug in compiler/assembler.
# It has nothing to do with codegen: dsd emits a nested `kind:data` symbol (an inline table living
# INSIDE a function's address range) with its own st_size on top of the enclosing function's size, so
# those bytes are counted twice.  Harmless while the module has enough unattributed bytes (blob /
# padding) to absorb it; fatal the moment a new delink entry splits that module into fully-attributed
# code.  See SP/inv/mainfix_FINDINGS.md.
#
# Usage:  python modsize_check.py            # scan build/<region>/delinks/*.o, exit 1 on any violation
#         python modsize_check.py --nested   # also list every nested sized symbol (the latent mines)
# Run it after `ninja delink` and BEFORE `ninja check` — it turns the cryptic link failure into the
# exact module, section, and offending symbol.  Pure ELF reader: no pyelftools, no repo writes.
import struct, glob, sys, os, re

REPO = _kp.REPO
SHT_PROGBITS, SHT_SYMTAB = 1, 2


def read_elf(path):
    d = open(path, 'rb').read()
    if d[:4] != b'\x7fELF' or d[4] != 1:
        raise ValueError(f"{path}: not a 32-bit ELF")
    shoff, = struct.unpack_from('<I', d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x2e)
    secs = []
    for i in range(shnum):
        name, typ, flags, addr, off, size, link, info, align, entsize = \
            struct.unpack_from('<10I', d, shoff + i * shentsize)
        secs.append(dict(idx=i, name=name, typ=typ, off=off, size=size, link=link))
    shstr = secs[shstrndx]
    for s in secs:
        st = shstr['off'] + s['name']
        s['sname'] = d[st:d.index(b'\0', st)].decode('utf-8', 'replace')
    syms = []
    for s in secs:
        if s['typ'] != SHT_SYMTAB: continue
        strtab = secs[s['link']]
        for j in range(s['size'] // 16):
            nm, val, sz, info, other, shndx = struct.unpack_from('<IIIBBH', d, s['off'] + j * 16)
            st = strtab['off'] + nm
            syms.append(dict(name=d[st:d.index(b'\0', st)].decode('utf-8', 'replace'),
                             val=val, size=sz, typ=info & 0xf, shndx=shndx))
    return secs, syms


def main():
    os.chdir(REPO)
    show_nested = '--nested' in sys.argv[1:]
    objs = sorted(glob.glob(buildcfg.build_root() + '/delinks/*.o'))
    if not objs:
        print("modsize_check: no delinked objects — run `ninja delink` first"); return 2
    viol, nested = [], []
    for p in objs:
        secs, syms = read_elf(p)
        for s in secs:
            if s['typ'] != SHT_PROGBITS or not s['sname'].startswith('.'): continue
            sized = sorted((y for y in syms if y['shndx'] == s['idx'] and y['size']),
                           key=lambda y: y['val'])
            total = sum(y['size'] for y in sized)
            if total > s['size']:
                # name the culprits: every symbol strictly inside another symbol's range
                inner = [y['name'] for i, y in enumerate(sized)
                         for z in sized[:i] if z['val'] < y['val'] < z['val'] + z['size']]
                viol.append((p, s['sname'], s['size'], total, inner))
            for i, y in enumerate(sized):
                for z in sized[:i]:
                    if z['val'] < y['val'] < z['val'] + z['size']:
                        nested.append((p, s['sname'], y['name'], y['size'], z['name']))
    if show_nested:
        print(f"nested sized symbols: {len(nested)}")
        for p, sec, y, sz, z in nested:
            print(f"  {os.path.basename(p)} {sec}: {y} (0x{sz:x}) inside {z}")
    if not viol:
        print(f"modsize_check: OK — {len(objs)} delinked objects, 0 sum-of-symbol-sizes violations")
        return 0
    print(f"modsize_check: {len(viol)} VIOLATION(S) — mwldarm will reject these at link:")
    for p, sec, size, total, inner in viol:
        print(f"  {p} {sec}: size=0x{size:x} sum=0x{total:x} over by 0x{total - size:x}")
        print(f"    double-counted (nested) symbols: {inner or '(none — different cause)'}")
    print("  FIX: declare each nested `kind:data(...)` symbol as `kind:label(arm)` in the module's")
    print("       symbols.txt so dsd emits it size-0, OR keep the module unsplit so its unattributed")
    print("       bytes absorb the double-count.  See SP/inv/mainfix_FINDINGS.md.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
