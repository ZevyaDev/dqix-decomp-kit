"""Transliterate every remaining ARM function; keep the matches, the references and the blockers.

Zero model tokens. Three outputs, in descending order of how much they are worth:

  1. REFERENCES  -- for functions >= REF_MIN bytes, save `attempts/Trans_<addr>.cpp`. resume_one
     attaches it to the prompt as reading material, which is the only artifact that says what the
     untouched blocks of a 10KB dispatch actually do.
  2. BLOCKERS    -- the instruction forms that still stop the translator, counted. Each form taught
     to translate.py applies pool-wide, so this list is a work queue ordered by payoff.
  3. MATCHES     -- staged for the normal wave path. Measured expectation is LOW (0 of 36 in a
     sample): a transliteration colours registers its own way, while the ROM came from idiomatic C,
     so the two coincide only on trivial functions -- and those were matched long ago. Anything here
     is upside, and it is verified by the real gate before it is staged, so it cannot pollute a build.

Usage: transweep.py [--shard i/n] [--limit N] [--refmin BYTES]
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import bisect
import collections
import glob
import importlib.util
import os
import re
import subprocess
import sys

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
os.chdir(REPO)
sys.path.insert(0, KIT)

_sh = sys.argv[sys.argv.index("--shard") + 1] if "--shard" in sys.argv else "1/1"
SHARD, NSHARD = (int(_sh.split("/")[0]), int(_sh.split("/")[1])) if "/" in _sh else (1, 1)
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10 ** 9
REF_MIN = int(sys.argv[sys.argv.index("--refmin") + 1]) if "--refmin" in sys.argv else 1024
TAG = "" if NSHARD == 1 else f"_{SHARD}of{NSHARD}"

spec = importlib.util.spec_from_file_location("_t", f"{KIT}/translate.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)

done = []
for p in [f"{REPO}/{buildcfg.config_root()}/delinks.txt"] + \
         sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/delinks.txt")):
    for a, b in re.findall(r"(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$",
                           open(p, encoding="utf-8", errors="ignore").read()):
        done.append((int(a, 16), int(b, 16)))
done.sort()


def landed(v):
    i = bisect.bisect_right(done, (v, 1 << 60)) - 1
    return i >= 0 and done[i][0] <= v < done[i][1]


pool = []
for cfg, mod in [(f"{REPO}/{buildcfg.config_root()}", "main")] + \
                [(os.path.dirname(p), re.search(r"ov(\d+)", p.replace(chr(92), "/")).group(1))
                 for p in sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt"))]:
    sym = open(f"{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()
    for m in re.finditer(r"kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\) addr:0x([0-9a-fA-F]+)",
                         sym):
        if m.group(1) != "arm":
            continue
        s, a = int(m.group(2), 16), int(m.group(3), 16)
        if s and not landed(a):
            pool.append((mod, "%08x" % a, s))
pool.sort(key=lambda x: (x[0], x[1]))
pool = pool[SHARD - 1::NSHARD][:LIMIT]

# addr -> the symbol the config binds, so a byte-exact translation can be rebound instead of lost.
BOUND = {}
for _p in [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + \
          sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt")):
    for _l in open(_p, encoding="utf-8", errors="ignore"):
        _m = re.match(r"(\S+)\s+kind:function\([^\n]*?addr:0x([0-9a-fA-F]+)", _l)
        if _m:
            BOUND[_m.group(2).lower().rjust(8, "0")] = _m.group(1)

work = f"{SP}/transweep_work{TAG}"
os.makedirs(work, exist_ok=True)
os.makedirs(f"{SP}/attempts", exist_ok=True)
res = collections.Counter()
forms = collections.Counter()
print(f"{len(pool)} unmatched ARM functions"
      + (f" (shard {SHARD}/{NSHARD})" if NSHARD > 1 else ""), flush=True)

for n, (mod, addr, size) in enumerate(pool, 1):
    try:
        src = T.translate(mod, addr)
    except Exception as e:
        res["raised"] += 1
        continue
    if not src:
        res["no-output"] += 1
        continue
    if "UNTRANSLATED" in src:
        res["untranslated"] += 1
        for l in src.split(chr(10)):
            m = re.search(r"UNTRANSLATED \+0x[0-9a-f]+: (\S+)", l)
            if m:
                forms[m.group(1)] += 1
        continue
    p = f"{work}/{mod}_{addr}.cpp"
    open(p, "w", encoding="utf-8", newline="\n").write(src)
    r = subprocess.run([sys.executable, f"{KIT}/wgate.py", mod, addr, p], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", cwd=REPO,
                       stdin=subprocess.DEVNULL)
    head = (((r.stdout or "") + (r.stderr or "")).strip().splitlines() or ["(none)"])[0]
    if head.startswith("MATCH"):
        res["MATCH"] += 1
        stage = f"{SP}/staging/" + ("main" if mod == "main" else f"ov{mod}")
        os.makedirs(stage, exist_ok=True)
        open(f"{stage}/Trans_{addr}.cpp", "w", encoding="utf-8", newline="\n").write(src)
        print(f"  MATCH {mod}:{addr} ({size}B) -> staged", flush=True)
    elif "WRONG-SYMBOL" in head:
        # BYTES ARE RIGHT, ONLY THE NAME IS WRONG -- that is a free function, not a near miss.
        # translate.py names its output `Trans_<addr>`; rebinding it to the symbol the config
        # requires turns WRONG-SYMBOL into MATCH. main:02048934 (96B) was found and thrown away
        # exactly this way before the rename was added here.
        want = BOUND.get(addr)
        fixed = False
        if want:
            txt = src.replace(f"Trans_{addr}", want)
            open(p, "w", encoding="utf-8", newline="\n").write(txt)
            r2 = subprocess.run([sys.executable, f"{KIT}/wgate.py", mod, addr, p],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", cwd=REPO, stdin=subprocess.DEVNULL)
            if (((r2.stdout or "") + (r2.stderr or "")).strip().splitlines() or [""])[0].startswith("MATCH"):
                stage = f"{SP}/staging/" + ("main" if mod == "main" else f"ov{mod}")
                os.makedirs(stage, exist_ok=True)
                open(f"{stage}/Trans_{addr}.cpp", "w", encoding="utf-8", newline="\n").write(txt)
                res["MATCH"] += 1
                fixed = True
                print(f"  MATCH {mod}:{addr} ({size}B) after name rebind -> staged", flush=True)
        if not fixed:
            res["bytes-match-name-wrong"] += 1
            print(f"  BYTES MATCH {mod}:{addr} ({size}B) -- name rebind failed", flush=True)
    elif head.startswith("COMPILE"):
        res["compile-fail"] += 1
    else:
        res["diff"] += 1
    if size >= REF_MIN:
        open(f"{SP}/attempts/Trans_{addr}.cpp", "w", encoding="utf-8", newline="\n").write(src)
        res["reference-saved"] += 1
    if n % 100 == 0:
        print(f"  ...{n}/{len(pool)} {dict(res)}", flush=True)

print(f"\ndone: {dict(res)}")
print("blocking forms:", dict(forms.most_common(12)))
