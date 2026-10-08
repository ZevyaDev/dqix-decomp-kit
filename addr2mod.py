#!/usr/bin/env python
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
# addr -> owning module ("main" or an overlay id), for callers that only have a bare address
# (lockout_harvest.sh reads quarantine/, whose paths carry no module).
#
# Resolved by ADDRESS RANGE, not by symbol name. The obvious implementation -- grep symbols.txt for
# `func_<addr>` -- silently fails on exactly the functions we care about: once a function matches it is
# RENAMED to something readable, so the `func_` symbol no longer exists. Both smoke-test addresses
# returned nothing under that version.
#
# Overlays are position-dependent and several share a load region, so one address can legitimately fall
# inside two overlays' ranges. That is genuinely ambiguous -- print NOTHING and let the caller skip,
# rather than gate a candidate against the wrong module. main is checked first and can never be
# ambiguous (its sections come from the active region's delinks).
import sys, re, os, glob

REPO = _kp.REPO
_root = f"{REPO}/{buildcfg.config_root()}"
if not os.path.isdir(_root):
    sys.exit(f"DQIX_REGION={buildcfg.REGION} has no {_root}")
raw = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
raw = raw[2:] if raw.startswith("0x") else raw
if not re.fullmatch(r'[0-9a-f]{1,8}', raw or ""):
    sys.exit(0)
a = int(raw, 16)


def spans(cfg):
    """Every section range this module owns, from its delinks.txt section table."""
    p = f"{REPO}/{cfg}/delinks.txt"
    if not os.path.exists(p):
        return []
    return [(int(s, 16), int(e, 16)) for s, e in
            re.findall(r'\.\w+\s+start:0x([0-9a-fA-F]+)\s+end:0x([0-9a-fA-F]+)\s+kind:',
                       open(p, encoding='utf-8', errors='ignore').read())]


if any(s <= a < e for s, e in spans(buildcfg.config_root())):
    print("main"); sys.exit(0)

hits = []
for d in sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/ov*")):
    ov = os.path.basename(d)
    if any(s <= a < e for s, e in spans(f"{buildcfg.config_root()}/overlays/{ov}")):
        hits.append(re.search(r'ov(\d+)', ov).group(1))
if len(hits) == 1:
    print(hits[0])
