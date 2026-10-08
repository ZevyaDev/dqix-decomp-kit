"""Exit 0 when the address lies inside some file's delinked range in any module, 1 otherwise.

    python delinked.py <addr_hex> [module]      module: main or NNN; default every module
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import glob
import re
import sys

REPO = _kp.REPO
RANGE = re.compile(r"(?m)^\s*\.text\s+start:0x([0-9a-fA-F]+)\s+end:0x([0-9a-fA-F]+)[ \t]*\r?$")


def files(mod=None):
    root = f"{REPO}/config/{_kp.region()}/arm9"
    paths = glob.glob(f"{root}/delinks.txt") + glob.glob(f"{root}/overlays/*/delinks.txt")
    if mod:
        paths = [p for p in paths if (mod == "main") == ("overlays" not in p) and (mod == "main" or f"ov{mod}" in p)]
    return paths


def covers(addr, texts):
    return any(int(lo, 16) <= addr < int(hi, 16) for text in texts for lo, hi in RANGE.findall(text))


if __name__ == "__main__":
    mod = sys.argv[2] if len(sys.argv) > 2 else None
    texts = (open(p, encoding="utf-8", errors="ignore").read() for p in files(mod))
    sys.exit(0 if covers(int(sys.argv[1], 16), texts) else 1)
