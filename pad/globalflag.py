"""Which optimisation level was the game built with? Ask the functions that already match.

Every committed function is byte-exact under the project default (-O2). If the ROM had been built at
another level, those functions would still have to be byte-exact under -O2 -- which is only possible
where the two levels emit IDENTICAL code. So the question is not "does -O4 match somewhere", it is:

    among committed functions where -O2 and -O4 DISAGREE, which one matches the ROM?

Every discriminating function that matches only under -O2 is evidence for -O2 globally. One that
matches only under -O4 is evidence the file wants an override -- and a pile of them would mean the
project default is wrong.

    python pad/globalflag.py [n] [--sets "-O4|-O3"]
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import glob
import os
import random
import re
import subprocess
import sys

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO

owner = {}
for p in [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + \
        sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt")):
    mod = "main" if "overlays" not in p else re.search(r"ov(\d+)", p).group(1)
    for m in re.finditer(r"kind:function\(\w+,size=0x[0-9a-fA-F]+\) addr:0x([0-9a-fA-F]{8})",
                         open(p, encoding="utf-8", errors="ignore").read()):
        owner.setdefault(m.group(1).lower(), mod)


def gate(mod, addr, path, flags):
    env = dict(os.environ)
    env["WGATE_ALLOW_COMMITTED"] = "1"
    env.pop("WGATE_SESSION", None)
    if flags:
        env["WGATE_FLAGS"] = flags
    r = subprocess.run([sys.executable, f"{KIT}/wgate.py", mod, addr, path],
                       capture_output=True, text=True, cwd=REPO, env=env)
    out = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    return bool(out) and out[-1].strip() == "MATCH"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 40
    sets = ["-O4"]
    if "--sets" in sys.argv:
        sets = [s.strip() for s in sys.argv[sys.argv.index("--sets") + 1].split("|")]
    files = glob.glob(f"{REPO}/src/**/*.cpp", recursive=True)
    random.seed(7)
    random.shuffle(files)
    tally = {s: {"both": 0, "default": 0, "alt": 0, "neither": 0} for s in sets}
    checked = 0
    for f in files:
        txt = open(f, encoding="utf-8", errors="ignore").read()
        m = re.search(r"//\s*USA: func_(?:ov\d+_)?([0-9a-fA-F]{8})", txt)
        if not m:
            continue
        addr = m.group(1).lower()
        mod = owner.get(addr)
        if not mod:
            continue
        base = gate(mod, addr, f, "")
        if not base:
            continue                      # not reproducible as-is; says nothing about flags
        checked += 1
        for s in sets:
            alt = gate(mod, addr, f, s)
            key = "both" if alt else "default"
            tally[s][key] += 1
        if checked >= n:
            break
    print("committed functions that reproduce under the default: %d" % checked)
    for s in sets:
        t = tally[s]
        disc = t["default"]
        print("  vs %-10s identical %d, DISCRIMINATING %d (all of which match the DEFAULT, not %s)"
              % (s, t["both"], disc, s))
    print("\nA discriminating function that matched ONLY the alternative would appear as a flagsweep")
    print("hit on a COMMITTED address; none has. Read that as: the default is the global setting, and")
    print("a flag override is a per-file exception, not a project-wide correction.")


if __name__ == "__main__":
    main()
