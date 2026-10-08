"""Find callee declarations that will not resolve to the symbol the ROM's relocation names.

A symbol fault is INVISIBLE until the bytes match: wgate reports BYTEDIFF first, so a candidate
parked a few bytes out can also carry a wrong callee, and nobody learns until the codegen is fixed.
`ov015:0218ee38` had two -- a name that existed only in its C++-mangled form, declared `extern "C"`
so it resolved to a different address entirely, which only the reloc check caught.

This costs no compile: it reads the declarations out of each source and checks them against
config/symbols.txt for the module.

    python pad/symaudit.py [<file.cpp> ...]      default: every clsbest/ artifact
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import glob
import os
import re
import sys

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO

symbols = {}
for p in [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + \
        sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt")):
    for line in open(p, encoding="utf-8", errors="ignore"):
        m = re.match(r"(\S+)\s+kind:function\(", line)
        if m:
            symbols.setdefault(m.group(1), p)

# A mangled name carries its plain name inside it: _Z<len><name>... Build plain -> mangled.
demangled = {}
for name in symbols:
    m = re.match(r"^_Z(\d+)(\w+)", name)
    if m:
        plain = m.group(2)[:int(m.group(1))]
        demangled.setdefault(plain, []).append(name)

DECL = re.compile(r'^\s*(extern\s+"C"\s+)?(?:extern\s+)?(?:ARM|THUMB)?\s*'
                  r'[\w:*&<>\s]+?\b([A-Za-z_]\w*)\s*\([^;{]*\)\s*;', re.M)


def audit(path):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    own = re.search(r"//\s*(?:SCRATCH-)?USA:\s*(\w+)", txt)
    own = own.group(1) if own else None
    out = []
    for m in DECL.finditer(txt):
        is_c, name = bool(m.group(1)), m.group(2)
        if name == own or name in ("if", "for", "while", "switch", "return", "sizeof"):
            continue
        if name in symbols:
            continue
        if name in demangled:
            # A plain C++ declaration mangles to the committed name whenever the signature matches,
            # so only an extern "C" one is certainly unresolvable.
            if is_c:
                out.append((name, 'declared extern "C" but the symbol is mangled: %s'
                            % demangled[name][0]))
        elif re.match(r"^(func_(ov\d+_)?[0-9a-fA-F]{8}|_Z)", name):
            out.append((name, "no such committed symbol"))
    return out


def main():
    files = sys.argv[1:] or sorted(glob.glob(f"{SP}/clsbest/*.cpp"))
    bad = 0
    for f in files:
        hits = audit(f)
        if hits:
            bad += 1
            print(os.path.basename(f))
            for name, why in hits:
                print("    %-52s %s" % (name, why))
    print("%d of %d file(s) carry a latent symbol fault" % (bad, len(files)))


# IMPORTABLE. recipe_select calls audit() per claim; with the CLI body at module level the import
# audited whatever happened to be in sys.argv -- the module and address -- and threw.
if __name__ == "__main__":
    main()
