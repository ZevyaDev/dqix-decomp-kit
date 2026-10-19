#!/usr/bin/env python
"""Move skiplisted sources OUT of every directory an integrator reads.

Usage: python purge_skiplisted.py [--dry]

An integrator should not have to know what a skiplist is. It integrates what it finds, so a
skiplisted function must simply not be there: `integrate_fast` takes its candidates from untracked
src/ and from staging/, and a single skiplisted file in either is enough to red a combined build for
the whole ROM. 0208f588 is the worked example -- skiplisted as "byte-exact per function but shifts
the ARM9 link", it fails `check modules` for ARM9 main every time, and one NOSKIP wave that left its
source in src/ was enough to red the next combined build with it.

Files are MOVED, never deleted, into skiplisted_hold/ so the attempt survives for whenever the
address comes off the skiplist. Run this after any NOSKIP wave and before any integration.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import glob, os, re, shutil, subprocess, sys

import buildcfg

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
DRY = "--dry" in sys.argv
HOLD = f"{SP}/skiplisted_hold"
os.chdir(REPO)

skip = set()
for name in ("skiplist_main.txt", "skiplist_ov.txt"):
    p = f"{KIT}/{name}"
    if os.path.exists(p):
        for line in open(p, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line and not line.startswith("#"):
                skip.add(line.split()[0].lower())

# Every directory an integrator reads: staging/<mod>/ for integrate_fast, and untracked src/ for
# both. hold_*/ and quarantine/ are deliberately NOT purged -- ov_recover filters those during
# gather(), and they exist to preserve attempts.
targets = sorted(p for ext in buildcfg.SOURCE_EXTS for p in glob.glob(f"{SP}/staging/*/*{ext}"))
untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", "src"],
                           capture_output=True, text=True).stdout.split()
targets += [f for f in untracked if f.endswith(buildcfg.SOURCE_EXTS)]

TAG = re.compile(r"// USA: func_(?:ov\d+_)?([0-9a-fA-F]{8})\b")
moved = 0
for f in targets:
    if not os.path.exists(f):
        continue
    m = TAG.search(open(f, encoding="utf-8", errors="ignore").read())
    if not m or m.group(1).lower() not in skip:
        continue
    print(f"{'[dry] ' if DRY else ''}purge {f} (0x{m.group(1).lower()} is skiplisted)")
    if not DRY:
        os.makedirs(HOLD, exist_ok=True)
        dst = f"{HOLD}/{os.path.basename(f)}"
        if os.path.exists(dst):
            dst = f"{HOLD}/{m.group(1).lower()}_{os.path.basename(f)}"
        shutil.move(f, dst)
    moved += 1
print(f"purge_skiplisted: {moved} file(s) {'would be ' if DRY else ''}moved to {HOLD}")
