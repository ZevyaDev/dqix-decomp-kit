"""Drop staged sources whose address is already committed.

`finish_wave` drops a staged file only when `committed_addrs()` claims it, and `gather()` decides
"already done" with `_already()` -- a DIFFERENT test. A file can therefore satisfy neither, sit in
staging/<mod>/ forever, and be re-wired on every pass. Two combined builds went RED today for
exactly that: the address was already delinked from src/, so re-wiring the staged copy defined the
symbol twice.

    python stagepurge.py            report only
    python stagepurge.py --apply    move the already-landed files to staging_landed/

Same test as the integrator: a source is landed when a LIVE (uncommented) delink range covers its
address AND a tracked file under src/ defines it.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import glob
import os
import re
import shutil
import subprocess
import sys

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
APPLY = "--apply" in sys.argv


def cfg_for(mod):
    if mod == "main":
        return f"{REPO}/{buildcfg.config_root()}"
    return f"{REPO}/{buildcfg.config_dir(mod)}"


def live_ranges(mod):
    try:
        dl = open(f"{cfg_for(mod)}/delinks.txt", encoding="utf-8", errors="ignore").read()
    except OSError:
        return []
    return [(int(a, 16), int(b, 16)) for a, b in re.findall(
        r"(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$", dl)]


def tracked_sources():
    out = subprocess.run(["git", "-C", REPO, "ls-files", "src"],
                         capture_output=True, text=True).stdout
    return [l.strip() for l in out.splitlines() if l.strip().endswith((".cpp", ".c", ".s"))]


def main():
    _kp.require_usa()
    tracked = tracked_sources()
    defined = set()
    for rel in tracked:
        try:
            txt = open(f"{REPO}/{rel}", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for m in re.finditer(r"(?m)^//\s*USA:\s*\S*?([0-9a-fA-F]{8})\b", txt):
            defined.add(m.group(1).lower())

    landed, kept = [], []
    for p in sorted(glob.glob(f"{SP}/staging/*/*.cpp") + glob.glob(f"{SP}/staging/*/*.c")
                    + glob.glob(f"{SP}/staging/*/*.s")):
        p = p.replace(chr(92), "/")
        mod = p.split("/")[-2].replace("ov", "", 1) if "/ov" in p else "main"
        m = re.search(r"([0-9a-fA-F]{8})", os.path.basename(p))
        if not m:
            kept.append((p, "no address in the filename"))
            continue
        a = m.group(1).lower()
        covered = any(s <= int(a, 16) < e for s, e in live_ranges(mod))
        if covered and a in defined:
            landed.append((p, a))
        else:
            why = "not delinked" if not covered else "delinked but no tracked definition"
            kept.append((p, why))

    for p, why in kept:
        print(f"KEEP  {os.path.basename(p):<34} {why}")
    for p, a in landed:
        print(f"{'MOVED' if APPLY else 'LANDED'} {os.path.basename(p):<34} {a} already committed")
        if APPLY:
            dst = f"{SP}/staging_landed/{p.split('/')[-2]}"
            os.makedirs(dst, exist_ok=True)
            shutil.move(p, f"{dst}/{os.path.basename(p)}")
    print(f"\n{len(landed)} already landed, {len(kept)} still pending"
          + ("" if APPLY else "  (run with --apply to move them)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
