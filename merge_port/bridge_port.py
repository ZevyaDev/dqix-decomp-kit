import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import re
import subprocess
import sys

REPO = _kp.REPO
ADDR = re.compile(r"addr:0x([0-9a-fA-F]+)")


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout


def table(text):
    out = {}
    for line in text.splitlines():
        m = ADDR.search(line)
        if m and line.split():
            out[m.group(1).lower()] = line.split()[0]
    return out


sym_files = [f for f in git("ls-files", "config/" + buildcfg.REGION).split() if f.endswith("symbols.txt")]
renames = {}
for f in sym_files:
    old = table(git("show", "HEAD:" + f))
    new = table(open(REPO + "/" + f, encoding="utf-8").read())
    for a, o in old.items():
        n = new.get(a)
        if n and n != o and o.startswith("_Z"):
            renames[o] = n

TOKEN = re.compile(r"\b_Z\w+")
for path in sys.argv[1:]:
    text = git("show", "HEAD:" + path)
    hits = []

    def sub(m):
        t = m.group(0)
        if t in renames:
            hits.append((t, renames[t]))
            return renames[t]
        return t

    text = TOKEN.sub(sub, text)
    open(REPO + "/" + path, "w", encoding="utf-8", newline="").write(text)
    print("%s: %d bridge renames" % (path, len(hits)))
    for o, n in sorted(set(hits)):
        print("  %s -> %s" % (o, n))
    left = sorted(set(re.findall(r"\b(?:BattleStruct|CombatantStruct|GetBattleStruct)\b", text)))
    if left:
        print("  still names: %s" % ", ".join(left))
