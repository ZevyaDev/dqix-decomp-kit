#!/usr/bin/env python
"""How many already-matched functions are sitting on disk but NOT in the build, per module.

A "recoverable" addr is one that (a) some staging dir holds a .cpp for, carrying this module's
`// USA: func_[ovNNN_]<addr>` tag, and (b) is not already delinked in that module's delinks.txt.
It cost worker tokens once and will cost zero to land.

Usage:  python recoverable.py            -> "<mod> <count>" per module, most first
        python recoverable.py <mod>      -> just that module's line
Module names are exactly what ov_recover.py takes: "main" or a zero-padded overlay ("017").
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
_kp.require_usa()
import re, os, sys, glob

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO

# every dir ov_recover can gather from. Keep this in sync with ov_recover's STAGING/DEFSTAGE: a dir we
# move source INTO but never gather FROM is exactly how 1500 matched files went dark.
STAGE_GLOBS = [f"{SP}/hold_*", f"{SP}/quarantine", f"{SP}/main_stage", f"{SP}/ov000_*"]

TAG = re.compile(r'// USA: func_(?:ov(\d+)_)?([0-9a-fA-F]{8})')


def delinked(mod):
    hexc = "[0-9a-fA-F]" if mod == "main" else "[0-9a-f]"
    cfg = buildcfg.config_dir(mod)
    p = f"{REPO}/{cfg}/delinks.txt"
    if not os.path.exists(p):
        return set(), []
    t = open(p).read()
    starts = set(f"{int(x,16):08x}" for x in
                 re.findall(r'(?m)^\s*\.text start:0x(%s+) end:' % hexc, t))
    # main has legacy multi-function files: one delink entry covers several funcs, so an addr can be
    # done without being a range START. Range membership is the only correct test there.
    rng = [(int(a, 16), int(b, 16))
           for a, b in re.findall(r'(?m)^\s*\.text start:0x(%s+) end:0x(%s+)\s*$' % (hexc, hexc), t)]
    return starts, rng


held = {}
seen_files = set()
for g in STAGE_GLOBS:
    for d in glob.glob(g):
        if not os.path.isdir(d):
            continue
        for fp in glob.glob(f"{d}/*.cpp"):
            rp = os.path.realpath(fp)
            if rp in seen_files:
                continue
            seen_files.add(rp)
            try:
                m = TAG.search(open(fp, encoding='utf-8', errors='ignore').read())
            except OSError:
                continue
            if m:
                held.setdefault(m.group(1) or "main", set()).add(m.group(2).lower())

# VERIFIED count from the last sweep's own classification. The raw held count is an UPPER BOUND — it
# only means "a .cpp with this module's USA tag exists and the addr is not delinked". It does NOT mean
# the source matches. Most held files are FAILED attempts. Reporting the raw number led me to tell the
# user "182 functions of matched source are stranded, more than a 14-hour run produced"; the sweep then
# landed 1. recover_sweep logs `classify: TRUSTED n RISKY n BAD {...}` per module — read the most recent
# line per module so the headline number is the one that can actually land.
verified = {}
_sl = f"{SP}/wlog/sweep.log"
if os.path.exists(_sl):
    for m in re.finditer(r'^\[(\w+)\] classify: TRUSTED (\d+) RISKY (\d+)',
                         open(_sl, encoding='utf-8', errors='ignore').read(), re.M):
        mod = m.group(1)
        mod = "main" if mod == "main" else mod.replace("ov", "")
        verified[mod] = int(m.group(2)) + int(m.group(3))   # last occurrence wins

rows = []
for mod, addrs in held.items():
    starts, rng = delinked(mod)
    n = sum(1 for a in addrs
            if a not in starts and not any(s <= int(a, 16) < e for s, e in rng))
    if n:
        rows.append((n, mod))
rows.sort(reverse=True)

want = sys.argv[1] if len(sys.argv) > 1 else None
# machine-readable form for recover_sweep.sh (`awk '$2>0'`) keeps column 2 = held count, unchanged.
# Column 3 is the verified count from the last sweep, or "?" if that module has never been classified.
for n, mod in rows:
    if want is None or mod == want:
        v = verified.get(mod)
        print(mod, n, ("?" if v is None else v))
if want is not None and not any(mod == want for n, mod in rows):
    print(want, 0, 0)
if want is None and rows:
    tot = sum(n for n, _ in rows)
    kv = [verified.get(m) for _, m in rows if verified.get(m) is not None]
    print(f"# held={tot} (UPPER BOUND: a tagged .cpp exists, NOT that it matches)"
          f"  verified-good-at-last-sweep={sum(kv) if kv else '?'}", file=sys.stderr)
