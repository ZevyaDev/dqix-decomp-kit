"""Rank the idioms that actually BLOCK functions, from real candidate diffs.

countpat.py measures how often an instruction appears; that is not the same as how
often it blocks a match. This runs the structural differ over parked candidates and
clusters the FIRST genuine difference in each -- target instruction(s) versus ours,
registers and immediates normalised away. The biggest clusters are the idioms worth
cracking next.

Usage: python diffmine.py [max-candidates]
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import glob
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
MAXC = int(sys.argv[1]) if len(sys.argv) > 1 else 150

REG = re.compile(r'\b(?:r\d+|sb|sl|fp|ip|lr|sp|pc)\b')
IMM = re.compile(r'#-?0x[0-9a-f]+|#-?\d+')


def norm(ins):
    return IMM.sub('#K', REG.sub('R', ins)).strip()


def module_of(addr, cache={}):
    if not cache:
        for p in [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + \
                 sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt")):
            mod = "main" if "overlays" not in p else re.search(r'ov(\d+)', p).group(1)
            for m in re.finditer(r'kind:function\([^)]*\) addr:0x([0-9a-fA-F]{8})',
                                 open(p, encoding="utf-8", errors="ignore").read()):
                cache.setdefault(m.group(1).lower(), mod)
    return cache.get(addr.lower())


def done_ranges(cache={}):
    if not cache:
        rs = []
        for p in [f"{REPO}/{buildcfg.config_root()}/delinks.txt"] + \
                 sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/delinks.txt")):
            txt = open(p, encoding="utf-8").read()
            rs += [(int(a, 16), int(b, 16)) for a, b in
                   re.findall(r'(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$', txt)]
        cache["r"] = rs
    return cache["r"]


def main():
    pools = sorted(set(glob.glob(f"{SP}/hold_*") + glob.glob(f"{SP}/*_stage") +
                       glob.glob(f"{SP}/staging/*") + [f"{SP}/quarantine", f"{SP}/repair_work"]))
    seen, jobs = set(), []

    def is_stub(path):
        """An unwritten scaffold body. Gating one tells you nothing about idioms.

        Without this, every top cluster came back as "target has a prologue, ours returns
        immediately" -- which is not a blocking idiom, it is a function nobody has written yet.
        68% of parked .cpp files were stubs, so the ranking was almost entirely noise.
        """
        try:
            txt = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            return True
        m = re.search(r"\)\s*\{(.*)\}\s*$", txt, re.S)
        body = m.group(1) if m else ""
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
        body = re.sub(r"//[^\n]*", "", body)
        return not body.strip()

    for d in pools:
        if d.replace("\\", "/").rstrip("/").endswith(("/scaffold", "/repair_work")):
            continue          # scaffolds are stubs by construction; repair_work is our own output
        for f in sorted(glob.glob(f"{d}/*.cpp")):
            m = re.search(r'([0-9a-fA-F]{8})\.cpp$', os.path.basename(f))
            if not m:
                continue
            if is_stub(f):
                continue
            a = m.group(1).lower()
            v = int(a, 16)
            if a in seen or any(lo <= v < hi for lo, hi in done_ranges()):
                continue
            mod = module_of(a)
            if mod:
                seen.add(a)
                jobs.append((mod, a, f))

    clusters = defaultdict(list)
    verdicts = Counter()
    done = 0
    for mod, addr, path in jobs:
        if done >= MAXC:
            break
        r = subprocess.run([sys.executable, f"{KIT}/sdiff.py", mod, addr, path, "1"],
                           capture_output=True, text=True, cwd=REPO, stdin=subprocess.DEVNULL)
        out = r.stdout or ""
        if "COMPILE-FAIL" in out or "NO-SLOT" in out:
            verdicts["compile/slot"] += 1
            continue
        head = out.split("\n")[0]
        m = re.search(r'target (\d+) instrs .*mine (\d+) instrs', head)
        if not m:
            verdicts["no-diff-output"] += 1
            continue
        done += 1
        same_count = m.group(1) == m.group(2)
        blocks = re.findall(r'^== (\w+).*?\n((?:   (?:tgt|MINE).*\n)+)', out, re.M)
        if not blocks:
            verdicts["identical"] += 1
            continue
        kind, block = blocks[0]
        # "   tgt  02185cc8 mov r4, r0" -> keep from the mnemonic on, not just the operands
        tgt = [norm(" ".join(l.split()[2:])) for l in block.split("\n") if l.strip().startswith("tgt")]
        mine = [norm(l.split(None, 1)[-1]) for l in block.split("\n") if l.strip().startswith("MINE")]
        key = (f"{'SAMECOUNT' if same_count else 'DIFFCOUNT'} {kind}",
               " ; ".join(tgt[:2]), " ; ".join(mine[:2]))
        clusters[key].append(f"{mod}:{addr}")
        verdicts["clustered"] += 1

    print(f"analysed {done} candidates: {dict(verdicts)}\n")
    print("largest blocking clusters (target || ours):")
    for key, addrs in sorted(clusters.items(), key=lambda kv: -len(kv[1]))[:18]:
        kind, tgt, mine = key
        print(f"  {len(addrs):3d}  [{kind}]")
        print(f"       tgt : {tgt[:78]}")
        print(f"       mine: {mine[:78]}")
        print(f"       e.g. {', '.join(addrs[:3])}")


main()
