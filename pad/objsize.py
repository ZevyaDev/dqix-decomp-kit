import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import os as _bcos, sys as _bcsys
_bcsys.path.insert(0, _bcos.path.dirname(_bcos.path.dirname(_bcos.path.abspath(__file__))))
import buildcfg
"""Per-symbol sizes for a MULTI-FUNCTION file, against what the config expects. Seconds, not minutes.

wgate compiles a whole file and compares ONE address's slot, so it cannot judge a file that defines
several functions (a class): it answers OVERGEN or WRONG-SYMBOL for reasons that have nothing to do
with the candidate. The only gate left was `ninja check`, which takes 3-6 minutes -- long enough that
a worker session spends its entire budget on one build and never edits anything (measured twice on
Ov34BackgroundLoader.cpp).

This compiles the file once and prints, per function symbol, the size the object has against the size
the ROM's config declares. That is the same question `dsd check` asks about layout, and it answers in
seconds.

    python pad/objsize.py <file.cpp> [<mwcc version>]
"""
import glob
import os
import re
import subprocess
import sys

from elftools.elf.elffile import ELFFile

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
FLAGS = list(buildcfg.FLAGS)


def expected_sizes():
    out = {}
    for p in [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + \
            sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt")):
        for m in re.finditer(r"^(\S+)\s+kind:function\(\w+,size=0x([0-9a-fA-F]+)\)",
                             open(p, encoding="utf-8", errors="ignore").read(), re.M):
            out.setdefault(m.group(1), int(m.group(2), 16))
    return out


def main():
    src = sys.argv[1]
    mw = sys.argv[2] if len(sys.argv) > 2 else None
    cc = buildcfg.cc_path(mw)
    obj = f"{SP}/handwork/objsize_{os.getpid()}.o"
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    r = subprocess.run([cc] + FLAGS + ["-c", src, "-o", obj], capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        print((r.stdout or "") + (r.stderr or ""))
        return 1
    want = expected_sizes()
    fh = open(obj, "rb")
    elf = ELFFile(fh)
    sym = elf.get_section_by_name(".symtab")
    rows = []
    for s in sym.iter_symbols():
        if s["st_info"]["type"] != "STT_FUNC" or not s.name or not s["st_size"]:
            continue
        got, exp = s["st_size"], want.get(s.name)
        rows.append((s.name, got, exp))
    fh.close()
    try:
        os.remove(obj)
    except OSError:
        pass
    bad = 0
    print("%-52s %8s %8s" % ("symbol", "ours", "config"))
    for name, got, exp in sorted(rows, key=lambda t: -t[1]):
        flag = ""
        if exp is None:
            flag = "  (not in config)"
        elif exp != got:
            flag = "  <-- %+d" % (got - exp)
            bad += 1
        print("%-52s %8s %8s%s" % (name[:52], hex(got), hex(exp) if exp else "-", flag))
    print("\n%d symbol(s), %d differ from the config under %s" % (len(rows), bad, mw or buildcfg.MWCC_VERSION))
    return 0


if __name__ == "__main__":
    sys.exit(main())
