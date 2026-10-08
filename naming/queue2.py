import bisect, collections, json, os, re, subprocess, sys

from namingpaths import LABEL as REPO, NAMING as SP
import buildcfg

CFG = REPO + "/" + buildcfg.config_root()
SRC_BRANCH = "labeling-pass"
OUTDIR = sys.argv[1] if len(sys.argv) > 1 else SP + "/chunks4"
PER = int(sys.argv[2]) if len(sys.argv) > 2 else 11
NBATCH = int(sys.argv[3]) if len(sys.argv) > 3 else 12

FUNC = re.compile(r"^(\S+)\s+kind:function\((\w+),size=0x([0-9a-fA-F]+)\)\s+addr:0x([0-9a-fA-F]+)")
ADDR = re.compile(r"0[12][0-9a-f]{6}")
ASSET = re.compile(r"^[A-Za-z0-9_%<>./\-]+\.(nat|gp2|bin|spr|chr|pac|nsarc|stb|sdat|obg|mes|"
                   r"bact|ambl|amdj|mse|NCGR|bncg|cchr|mon)$")


def git(*a):
    return subprocess.check_output(["git", "-C", REPO] + list(a)).decode("utf-8", "replace")


def rels():
    root = buildcfg.config_root()
    yield "main", root
    for sub in ("itcm", "dtcm"):
        yield sub, root + "/" + sub
    for n in sorted(os.listdir(CFG + "/overlays")):
        yield n, root + "/overlays/" + n


def parse_funcs(text):
    out = []
    for line in text.splitlines():
        m = FUNC.match(line)
        if m:
            out.append((int(m.group(4), 16), int(m.group(3), 16), m.group(1)))
    out.sort()
    return out


def parse_delinks(text, fl):
    starts = [f[0] for f in fl]
    out, cur = {}, None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^(src/\S+\.(?:cpp|c|s)):$", s)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"^\.text start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)$", s)
        if m and cur:
            a, b = int(m.group(1), 16), int(m.group(2), 16)
            i = bisect.bisect_left(starts, a)
            while i < len(fl) and fl[i][0] < b:
                out[fl[i][0]] = cur
                i += 1
    return out


cg = json.load(open(SP + "/cg.json", encoding="utf-8"))
callers = collections.Counter()
for k, v in cg["callers"].items():
    mod, addr, _name = k.split("|")
    callers[(mod, int(addr, 16))] = len(v)

sx = json.load(open(SP + "/strxref.json", encoding="utf-8"))
evidence = {}
for k, v in sx.items():
    mod, _name, addr = k.split(" ")
    a = [s for s in v if ASSET.match(s) or s.startswith("data/") or s.startswith("/data/")]
    if a:
        evidence[(mod, int(addr, 16))] = a

SKIP = set()
_sp = SP + "/skip_addrs.txt"
if os.path.exists(_sp):
    for _l in open(_sp, encoding="utf-8"):
        _l = _l.strip().lower()
        if _l:
            SKIP.add(_l)

rows = []
for mod, base in rels():
    cur_syms = parse_funcs(open(REPO + "/" + base + "/symbols.txt", encoding="utf-8",
                                errors="replace").read())
    try:
        lab_syms = parse_funcs(git("show", "%s:%s/symbols.txt" % (SRC_BRANCH, base)))
        lab_src = parse_delinks(git("show", "%s:%s/delinks.txt" % (SRC_BRANCH, base)), lab_syms)
    except subprocess.CalledProcessError:
        continue
    ported = set(parse_delinks(open(REPO + "/" + base + "/delinks.txt", encoding="utf-8",
                                    errors="replace").read(), cur_syms))
    for addr, size, name in cur_syms:
        if addr in ported:
            continue
        src = lab_src.get(addr)
        if not src:
            continue
        if not (name.startswith("func_") or ADDR.search(name)):
            continue
        key = (mod, addr)
        ev = evidence.get(key, [])
        rows.append({
            "address": "0x%08x" % addr,
            "current_name": name,
            "module": mod,
            "size": "0x%x" % size,
            "callers": str(callers.get(key, 0)),
            "asset_strings": " | ".join(ev),
            "labeling_source": src,
            "_rank": (0 if ev else 1, -callers.get(key, 0)),
        })

rows.sort(key=lambda r: r.pop("_rank"))
os.makedirs(OUTDIR, exist_ok=True)
n = 0
for i in range(0, min(len(rows), PER * NBATCH), PER):
    json.dump(rows[i:i + PER], open("%s/batch%02d.json" % (OUTDIR, n), "w"), indent=1)
    n += 1
print("candidates:", len(rows), " batches:", n, " ->", OUTDIR)
print("with asset strings:", sum(1 for r in rows if r["asset_strings"]))
