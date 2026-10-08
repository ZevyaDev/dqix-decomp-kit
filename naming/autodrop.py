import json, os, subprocess, sys

from namingpaths import LABEL as REPO, NAMING as SP
import buildcfg

PLAN = sys.argv[1]
OUT = sys.argv[2]


def run(argv, cwd=REPO):
    return subprocess.call(argv, cwd=cwd,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def attempt(items):
    json.dump(items, open(SP + "/try.json", "w"))
    run(["git", "checkout", "-q", "--", "."])
    run(["git", "clean", "-qfd"])
    if run([sys.executable, SP + "/port2.py", SP + "/try.json", "--apply"]) != 0:
        return False
    run([sys.executable, SP + "/propagate.py"])
    if run([sys.executable, "tools/configure.py", buildcfg.REGION]) != 0:
        return False
    return run(["ninja", "check"]) == 0


plan = json.load(open(PLAN))
dropped = []
while True:
    if attempt(plan):
        break
    lo, hi = 0, len(plan)
    while lo < hi:
        mid = (lo + hi) // 2
        print("  prefix", mid, flush=True)
        if attempt(plan[:mid]):
            lo = mid + 1
        else:
            hi = mid
    if lo == 0 or lo > len(plan):
        print("bisect failed to isolate", flush=True)
        break
    bad = plan[lo - 1]
    print("DROP", bad["address"], bad["name"], bad["labeling_source"], flush=True)
    dropped.append(bad)
    plan = [p for p in plan if p["address"] != bad["address"]]
    if not plan:
        break

json.dump(plan, open(OUT, "w"), indent=1)
json.dump(dropped, open(OUT.replace(".json", "_dropped.json"), "w"), indent=1)
print("kept", len(plan), "dropped", len(dropped))
for d in dropped:
    print("   ", d["address"], d["name"])
