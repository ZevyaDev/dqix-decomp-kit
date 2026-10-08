"""Find a COMMITTED, byte-exact source whose ROM code contains an instruction shape.

findshape.py answers one hardcoded question (add/ldr pairing). This answers any of them: give it a
regex over `mnemonic operands` and it reports which delinked function each hit lands in and whether
that function has a committed source. Reading the C that already produces the shape beats guessing
at source forms.

Usage:
  python pad/findmnem.py "sub \\w+, \\w+, #0$"          one instruction
  python pad/findmnem.py "mov r3, #1" "sub \\w+, r3"    consecutive instructions (regex per row)
  python pad/findmnem.py ... --all                     list every hit, not just committed ones
  python pad/findmnem.py ... --limit N                  rows to print (default 25)
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import os
import re
import sys

import capstone

REPO = _kp.REPO
blob = open(f"{REPO}/{buildcfg.pristine('main')}", "rb").read()
cfg = f"{REPO}/{buildcfg.config_root()}/delinks.txt"
text = open(cfg).read()
base = min(int(x, 16) for x in re.findall(r"start:0x([0-9a-fA-F]+)", text))

ranges = sorted((int(a, 16), int(b, 16)) for a, b in
                re.findall(r"\.text start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)", text))

srcs = {}
for root, _, files in os.walk(f"{REPO}/src"):
    for f in files:
        if not f.endswith(".cpp"):
            continue
        path = os.path.join(root, f)
        addrs = set()
        m = re.search(r"_([0-9a-f]{8})\.cpp$", f)
        if m:
            addrs.add(int(m.group(1), 16))
        try:
            body = open(path, encoding="utf-8", errors="ignore").read()
        except IOError:
            body = ""
        for a in re.findall(r"//\s*USA:\s*\S*?_?([0-9a-f]{8})\b", body):
            addrs.add(int(a, 16))
        for a in re.findall(r"\b(02[0-9a-f]{6})\b", f):
            addrs.add(int(a, 16))
        for a in addrs:
            srcs[a] = path

argv, limit = sys.argv[1:], 25
if "--limit" in argv:
    k = argv.index("--limit")
    limit = int(argv[k + 1])
    del argv[k:k + 2]
pats = [re.compile(a, re.I) for a in argv if not a.startswith("--")]
if not pats:
    print(__doc__)
    sys.exit(2)

md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
md.skipdata = True
rows = [(i.address, "%s %s" % (i.mnemonic, i.op_str)) for i in md.disasm(blob, base)]

hits = []
for k in range(len(rows) - len(pats) + 1):
    if all(pats[j].search(rows[k + j][1]) for j in range(len(pats))):
        addr = rows[k][0]
        fn = next((a for a, b in ranges if a <= addr < b), None)
        hits.append((addr, fn, rows[k][1]))

named = [h for h in hits if h[1] in srcs]
print("%d hit(s), %d inside a committed source" % (len(hits), len(named)))
for addr, fn, txt in (hits if "--all" in sys.argv else named)[:limit]:
    tag = os.path.basename(srcs[fn]) if fn in srcs else (
        "%08x UNMATCHED" % fn if fn else "(no delink range)")
    print("  %08x  %-34s %s" % (addr, txt, tag))

size = {a: b - a for a, b in ranges}
todo, seen = [], set()
for addr, fn, txt in hits:
    if fn is None or fn in srcs or fn in seen:
        continue
    seen.add(fn)
    todo.append((size.get(fn, 1 << 30), fn, addr, txt))
print("\nsmallest UNMATCHED functions carrying the shape:")
for sz, fn, addr, txt in sorted(todo)[:12]:
    print("  %08x  %5d B  hit at %08x  %s" % (fn, sz, addr, txt))
