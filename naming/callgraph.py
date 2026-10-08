"""Write cg.json, the call graph queue.py and queue2.py rank by: {callers, callees}, keys module|addr|name.

    python callgraph.py [<repo>]      default: the label clone ($DQIX_LABEL_REPO)
"""
import bisect
import glob
import json
import os
import re
import sys

import namingpaths
import buildcfg

CALLS = {"arm_call", "arm_call_thumb", "thumb_call", "thumb_call_arm"}
FUNC = re.compile(r"^(\S+) kind:function\(\w+,size=0x([0-9a-fA-F]+)\) addr:0x([0-9a-fA-F]+)", re.M)
RELOC = re.compile(r"^from:0x([0-9a-fA-F]+) kind:(\w+) to:0x([0-9a-fA-F]+) module:(\S+)", re.M)


def modules(repo):
    base = f"{repo}/{buildcfg.config_root()}"
    out = {"main": base, "itcm": f"{base}/itcm", "dtcm": f"{base}/dtcm"}
    for d in sorted(glob.glob(f"{base}/overlays/ov*")):
        out[os.path.basename(d)] = d.replace("\\", "/")
    return {m: d for m, d in out.items() if os.path.exists(f"{d}/symbols.txt")}


def functions(cfg):
    text = open(f"{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()
    fl = sorted((int(a, 16), int(a, 16) + int(s, 16), n) for n, s, a in FUNC.findall(text))
    return fl, [f[0] for f in fl]


def owner(table, addr):
    fl, starts = table
    i = bisect.bisect_right(starts, addr) - 1
    if i >= 0 and fl[i][0] <= addr < fl[i][1]:
        return fl[i]
    return None


def target_module(spec, here):
    if spec == "main":
        return "main"
    m = re.fullmatch(r"overlay\((\d+)\)", spec)
    if m:
        return "ov%03d" % int(m.group(1))
    if spec in ("itcm", "dtcm"):
        return spec
    return None


def main():
    repo = (sys.argv[1] if len(sys.argv) > 1 else namingpaths.LABEL).replace("\\", "/")
    mods = modules(repo)
    tables = {m: functions(d) for m, d in mods.items()}
    callers, callees = {}, {}
    for m, d in mods.items():
        path = f"{d}/relocs.txt"
        if not os.path.exists(path):
            continue
        for frm, kind, to, spec in RELOC.findall(open(path, encoding="utf-8", errors="ignore").read()):
            if kind not in CALLS:
                continue
            tm = target_module(spec, m)
            if tm not in tables:
                continue
            src = owner(tables[m], int(frm, 16))
            dst = owner(tables[tm], int(to, 16) & ~1)
            if not src or not dst:
                continue
            a = f"{m}|{src[0]:08x}|{src[2]}"
            b = f"{tm}|{dst[0]:08x}|{dst[2]}"
            callees.setdefault(a, set()).add(b)
            callers.setdefault(b, set()).add(a)
    out = {"callers": {k: sorted(v) for k, v in sorted(callers.items())},
           "callees": {k: sorted(v) for k, v in sorted(callees.items())}}
    with open(f"{namingpaths.NAMING}/cg.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    print(f"cg.json: {len(callers)} callees with callers, {sum(len(v) for v in callees.values())} edges")


main()
