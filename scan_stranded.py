"""List candidate sources whose address is not yet in any delinks range.

Reads every .cpp in the pools named on the command line (or a default set of
untracked pools) and reports the ones whose `// USA: func_...` address falls
outside every committed .text/.init delink range.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import bisect
import glob
import os
import re
import sys

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO

ranges = []
for d in [f"{REPO}/{buildcfg.config_root()}/delinks.txt"] + sorted(
        glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/delinks.txt")):
    with open(d, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    for x, y in re.findall(r"(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$", text):
        ranges.append((int(x, 16), int(y, 16)))
ranges.sort()


def landed(v):
    i = bisect.bisect_right(ranges, (v, 1 << 60)) - 1
    return i >= 0 and ranges[i][0] <= v < ranges[i][1]


pools = sys.argv[1:] or ["gated/*", "wave_*", "wmain", "fin011", "hold_*", "staging/*"]
rows = []
for pat in pools:
    for d in sorted(x.replace(chr(92), chr(47)) for x in glob.glob(f"{SP}/{pat}/")):
        for f in sorted(x.replace(chr(92), chr(47)) for x in glob.glob(d + "*.cpp")):
            with open(f, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
            m = re.search(r"// USA: func_(?:ov\d+_)?([0-9a-fA-F]{8})", body)
            if not m:
                rows.append(("NOADDR", d, os.path.basename(f)))
                continue
            a = int(m.group(1), 16)
            if not landed(a):
                rows.append((m.group(1).lower(), d, os.path.basename(f)))

by_addr = {}
for a, d, f in rows:
    by_addr.setdefault(a, []).append(os.path.basename(d.rstrip("/")) + "/" + f)
for a in sorted(by_addr):
    print(a, " ".join(by_addr[a]))
print(f"{len(by_addr)} unlanded address(es) across {len(rows)} file(s)")
