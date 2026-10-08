"""Close the loop on a worker SKIP within minutes instead of at the next full sweep.

A worker that gives up leaves its best attempt in `attempts/`. repairsweep does re-gate that directory
-- but only when someone runs a full pass over 1200 candidates, which is hours away and re-does work
already done. This watches `attempts/` for NEW files, gates each once, and runs colorsweep on anything
close. A match is staged for the normal finish_wave path; nothing else is touched.

Cheap by construction: it compiles only when a file appears, which is a few times an hour.

Usage: skipsweep.py [--interval 60] [--once]
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
_kp.require_usa()
import glob, hashlib, os, re, subprocess, sys, time

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
WATCH = f"{SP}/attempts"
SEEN = f"{SP}/skipsweep_seen.txt"
INTERVAL = int(sys.argv[sys.argv.index("--interval") + 1]) if "--interval" in sys.argv else 60
ONCE = "--once" in sys.argv

sym = {}
for p in [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + \
         sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt")):
    mod = "main" if "overlays" not in p else re.search(r'ov(\d+)', p).group(1)
    for m in re.finditer(r'^\S+ kind:function\(\w+,size=0x[0-9a-fA-F]+\) addr:0x([0-9a-fA-F]{8})',
                         open(p, encoding="utf-8", errors="ignore").read(), re.M):
        sym.setdefault(m.group(1).lower(), mod)

skip = set()
for p in glob.glob(f"{SP}/skiplist*.txt"):
    for l in open(p, encoding="utf-8", errors="ignore"):
        m = re.match(r'\s*(?:0x)?([0-9a-fA-F]{8})', l)
        if m:
            skip.add(m.group(1).lower())


def landed():
    done = set()
    for p in [f"{REPO}/{buildcfg.config_root()}/delinks.txt"] + \
             sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/delinks.txt")):
        txt = open(p, encoding="utf-8", errors="ignore").read()
        for a, b in re.findall(r'(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$', txt):
            done.add((int(a, 16), int(b, 16)))
    return done


def gate(mod, addr, path):
    r = subprocess.run([sys.executable, f"{KIT}/wgate.py", mod, addr, path],
                       capture_output=True, text=True, cwd=REPO, stdin=subprocess.DEVNULL)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def bind_name(mod, addr, path):
    """Rename the definition to the symbol the config binds, which is what the gate checks."""
    txt = open(path, encoding="utf-8").read()
    want = f"func_{addr}" if mod == "main" else f"func_ov{mod}_{addr}"
    if want in txt:
        return
    m = re.search(r"// USA: (\w+)", txt)
    tag = m.group(1) if m else want
    stem = None
    for mm in re.finditer(r"(?:ARM|THUMB)\s+[\w:*]+\s+(\w+_%s)\s*\(" % addr, txt):
        stem = mm.group(1)
    if stem:
        txt = txt.replace(stem, want)
        txt = re.sub(r'(?m)^(?!extern "C" )((?:ARM|THUMB) [\w* ]*?%s\()' % re.escape(want),
                     r'extern "C" \1', txt)
        open(path, "w", encoding="utf-8", newline="\n").write(txt)


def cycle(seen):
    ranges = landed()
    hits = 0
    for f in sorted(glob.glob(f"{WATCH}/*.cpp"), key=os.path.getmtime):
        m = re.search(r'([0-9a-fA-F]{8})\.cpp$', os.path.basename(f))
        if not m:
            continue
        addr = m.group(1).lower()
        mod = sym.get(addr)
        if not mod or addr in skip:
            continue
        v = int(addr, 16)
        if any(lo <= v < hi for lo, hi in ranges):
            continue
        h = hashlib.md5(open(f, 'rb').read()).hexdigest()
        if f"{addr} {h}" in seen:
            continue
        seen.add(f"{addr} {h}")
        with open(SEEN, "a", encoding="utf-8") as fh:
            fh.write(f"{addr} {h}\n")
        work = f"{SP}/skipwork"
        os.makedirs(work, exist_ok=True)
        cand = f"{work}/{mod}_{addr}.cpp"
        open(cand, "w", encoding="utf-8", newline="\n").write(open(f, encoding="utf-8").read())
        bind_name(mod, addr, cand)
        verdict = gate(mod, addr, cand)
        if not verdict.startswith("MATCH"):
            subprocess.run([sys.executable, f"{KIT}/colorsweep.py", mod, addr, cand,
                            "--depth", "3", "--budget", "200", "--apply"],
                           capture_output=True, text=True, cwd=REPO, stdin=subprocess.DEVNULL)
            verdict = gate(mod, addr, cand)
        print(f"{time.strftime('%H:%M')} {mod} {addr} {verdict.splitlines()[0][:80]}", flush=True)
        if verdict.startswith("MATCH"):
            stage = f"{SP}/staging/" + ("main" if mod == "main" else f"ov{mod}")
            os.makedirs(stage, exist_ok=True)
            dst = f"{stage}/{os.path.basename(cand)}"
            open(dst, "w", encoding="utf-8", newline="\n").write(open(cand, encoding="utf-8").read())
            print(f"  STAGED {dst}", flush=True)
            hits += 1
    return hits


seen = set()
if os.path.isfile(SEEN):
    seen = {l.strip() for l in open(SEEN, encoding="utf-8") if l.strip()}
print(f"skipsweep watching {WATCH} every {INTERVAL}s ({len(seen)} already tried)", flush=True)
while True:
    try:
        cycle(seen)
    except Exception as e:
        print(f"cycle error: {e}", flush=True)
    if ONCE:
        break
    time.sleep(INTERVAL)
