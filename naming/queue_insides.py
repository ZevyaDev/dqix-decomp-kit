import json, os, re, subprocess, sys

from namingpaths import LABEL as REPO, NAMING as SP
import buildcfg

OUTDIR = sys.argv[1] if len(sys.argv) > 1 else SP + "/inside1"
PER = int(sys.argv[2]) if len(sys.argv) > 2 else 9
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 0

SYMF = re.compile(r"^(\S+)\s+kind:function\(([^)]*)\)\s+addr:0x([0-9a-fA-F]+)")
IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
JUNK = re.compile(r"^(obj|arg\d*|elem|node|tmp|val|ptr|dst|src|a|b|c|d|e|i|j|k|n|s|t|v|"
                  r"[a-z]\d+|v\d+|i\d+|cond\d+|flag\d*|field[0-9a-fA-F]+|pad\d*|pad[0-9a-fA-F]+|"
                  r"unk[0-9a-fA-F]*|.*_?0[0-9a-fA-F]{7})$")


def git(*a):
    return subprocess.check_output(["git", "-C", REPO] + list(a)).decode("utf-8", "replace")


def modules():
    for root in buildcfg.config_roots():
        cfg = REPO + "/" + root
        yield "main", cfg
        for sub in ("itcm", "dtcm"):
            yield sub, cfg + "/" + sub
        ovd = cfg + "/overlays"
        if not os.path.isdir(ovd):
            continue
        for n in sorted(os.listdir(ovd)):
            yield n, ovd + "/" + n


def symbols(base):
    out = {}
    p = base + "/symbols.txt"
    if not os.path.exists(p):
        return out
    for line in open(p, encoding="utf-8", errors="replace"):
        m = SYMF.match(line)
        if m:
            sz = re.search(r"size=0x([0-9a-fA-F]+)", m.group(2))
            out[int(m.group(3), 16)] = (m.group(1), int(sz.group(1), 16) if sz else 0)
    return out


def delinks(base):
    p = base + "/delinks.txt"
    if not os.path.exists(p):
        return
    cur = None
    for line in open(p, encoding="utf-8", errors="replace"):
        m = re.match(r"^(\S+\.(?:cpp|c|s)):\s*$", line)
        if m:
            cur = m.group(1)
            continue
        m = re.search(r"\.text start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)", line)
        if m and cur:
            yield cur, int(m.group(1), 16), int(m.group(2), 16)
            cur = None


added = set(x.strip().replace("\\", "/") for x in
            git("diff", "--name-only", "--diff-filter=A", "upstream-main..naming-pass",
                "--", "src").splitlines())
strx = json.load(open(SP + "/strxref.json", encoding="utf-8"))
bystr = {}
for key, vals in strx.items():
    parts = key.split()
    if len(parts) == 3:
        bystr[parts[2].lower()] = vals

GLOBALS = set()
for _m, _b in modules():
    _p = _b + "/symbols.txt"
    if os.path.exists(_p):
        for _l in open(_p, encoding="utf-8", errors="replace"):
            _mm = re.match(r"^(\S+)\s+kind:", _l)
            if _mm:
                GLOBALS.add(_mm.group(1))

entries = []
for mod, base in modules():
    syms = symbols(base)
    for src, start, end in delinks(base):
        if src not in added:
            continue
        path = REPO + "/" + src
        if not os.path.exists(path):
            continue
        name, size = syms.get(start, (None, end - start))
        if not name:
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        junk = sorted(set(i for i in IDENT.findall(text)
                         if JUNK.match(i) and i not in GLOBALS))
        entries.append({
            "file": src,
            "function": name,
            "module": mod,
            "address": "0x%08x" % start,
            "size": size,
            "junk_identifiers": junk,
            "asset_strings": bystr.get("0x%08x" % start, []),
        })

entries.sort(key=lambda e: -len(e["junk_identifiers"]))
if LIMIT:
    entries = entries[:LIMIT]
os.makedirs(OUTDIR, exist_ok=True)
n = 0
for i in range(0, len(entries), PER):
    json.dump(entries[i:i + PER], open("%s/batch%02d.json" % (OUTDIR, n), "w"), indent=1)
    n += 1
print("files:", len(entries), " batches:", n, " ->", OUTDIR)
print("no junk identifiers:", sum(1 for e in entries if not e["junk_identifiers"]))
