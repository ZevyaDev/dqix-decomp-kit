#!/usr/bin/env python3
"""What pull dispatch is actually costing, broken out by function SIZE.

    python pullstat.py [recent_n]

A single $/function figure is misleading while the pool is being drawn unevenly: the first 30
functions pull served were 4-24 bytes (claim.py used to hand out smallest-first), which produced a
flattering $0.56 that said nothing about the work that remains. Splitting by size band is the only
way to compare against autotune's $7.23 all-tiers baseline without fooling ourselves.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import glob
import os
import re
import sys

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
LINE = re.compile(r"(\d\d:\d\d) s(\d+) (MATCH|miss) ([0-9a-f]{8}) \$([0-9.]+)")


def sizes():
    out = {}
    for p in glob.glob(f"{REPO}/{buildcfg.config_root()}/**/symbols.txt", recursive=True):
        txt = open(p, encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r"kind:function\((?:arm|thumb),size=0x([0-9a-fA-F]+)\)"
                             r"\s+addr:0x([0-9a-fA-F]+)", txt):
            out[m.group(2).lower()] = int(m.group(1), 16)
    return out


def band(n):
    return "small <=64B" if n <= 64 else "med 65-256B" if n <= 256 else "large >256B"


def alerts(rows, cap):
    """Outcome alerts. The monitor watched only whether work was HAPPENING -- driver alive, files
    produced, commits landing -- so a fleet burning money and matching nothing read as healthy.
    These fire on the two failure shapes that actually cost money:

      * failing WITHOUT reaching the cap  -> the worker gave up on its own. Either the task is
        beyond it or something was taken away from it (moving the recipes out of the doc put the
        large band at 0-for-5 and nothing said a word).
      * failing AT the cap                -> the budget truncated real work; raising PER_FUNC_CAP
        for that size band may convert it.
    """
    out = []
    if len(rows) < 6:
        return out
    tried = len(rows)
    matched = sum(1 for r in rows if r[1] == "MATCH")
    spend = sum(r[3] for r in rows)
    rate = 100.0 * matched / tried

    if rate < 40:
        out.append(f"ALERT yield: last {tried} attempts matched {matched} ({rate:.0f}%), "
                   f"${spend:.2f} spent")

    # PER-BAND CAPS. The cap is no longer one number -- pull_worker sizes it to the function
    # ($1.50 / $3 / $5) -- so comparing every attempt against a single figure would call a $2.90
    # small-function failure "not truncated" when it blew through its $1.50 cap, and call a $4
    # large-function failure "truncated" when it had $5 to spend.
    def cap_of(size):
        return CAP_LARGE if size > 256 else CAP_MED if size > 64 else CAP_SMALL

    # ALERT ON MATCHES NEAR THE CAP, NOT FAILURES. The original fired when FAILURES hit the ceiling
    # and concluded "budget-truncated, not unmatchable" -- and I acted on it, raising CAP_LARGE 5->8.
    # It converted nothing: measured over 42 attempts, matches cost min $1.47 / median $2.44 / max
    # $4.91 while misses simply consume whatever ceiling exists (median $4.60, max $7.49 once given
    # $8). The two populations barely overlap, so a failure at the cap is NORMAL and says nothing.
    # What would genuinely mean the cap is too low is a MATCH landing right against it -- that is a
    # conversion nearly lost, and the only evidence that justifies more budget.
    near = [r for r in rows if r[1] == "MATCH" and r[3] >= 0.9 * cap_of(r[4])]
    if len(near) >= 2:
        _dm = ", ".join(f"{r[2]}@${r[3]:.2f}/${cap_of(r[4]):.2f}" for r in near[:4])
        out.append(f"ALERT cap: {len(near)} MATCHES landed within 10% of their cap ({_dm}) -- real "
                   f"conversions are nearly being cut off; raising that band's cap is justified")

    truncated = [r for r in rows if r[1] != "MATCH" and r[3] >= 0.95 * cap_of(r[4])]
    if False:  # retained for reference; see the note above on why failures-at-cap is not a signal
        out.append(f"ALERT cap: {len(truncated)} of {tried} failures hit the ${cap:.2f} per-function "
                   f"cap -- budget-truncated, not unmatchable")

    # Quitting early is INSTRUCTED behaviour -- the worker doc says "SKIP after ~5 tries" -- so on
    # its own it means triage is working, not that anything is wrong. Alerting on it unconditionally
    # would fire nearly every cycle and become the noise these checks exist to avoid. It is only a
    # signal when yield is also poor: lots of cheap give-ups AND few matches is the shape of workers
    # missing something they need (moving the recipes out of their doc produced exactly that).
    gaveup = [r for r in rows if r[1] != "MATCH" and r[3] < 0.6 * cap]
    if len(gaveup) >= 4 and rate < 55:
        out.append(f"ALERT giveup: {len(gaveup)} of {tried} failures quit under 60% of the cap "
                   f"(${cap:.2f}) at only {rate:.0f}% yield -- workers stopping early, not out of "
                   f"budget; check they still have what they need to match")

    by = {}
    for _t, verdict, _a, cost, size in rows:
        b = by.setdefault(band(size), [0, 0, 0.0])
        b[0] += 1
        b[1] += verdict == "MATCH"
        b[2] += cost
    for b, (t, m, c) in by.items():
        if t >= 4 and m == 0:
            out.append(f"ALERT band: {b} is {m}/{t} with ${c:.2f} spent -- nothing converting")
    return out


def main():
    if "--alerts" in sys.argv:
        sz = sizes()
        rows = []
        for p in sorted(glob.glob(f"{SP}/wlog/pull_*_s*.log"), key=os.path.getmtime):
            for line in open(p, encoding="utf-8", errors="replace"):
                m = LINE.search(line)
                if m:
                    rows.append((m.group(1), m.group(3), m.group(4), float(m.group(5)),
                                 sz.get(m.group(4), 0)))
        cap = 3.0
        try:
            cap = float(open(f"{SP}/PER_FUNC_CAP", encoding="utf-8").read().strip())
        except (OSError, ValueError):
            pass
        # SORT BY TIME. Walking files in mtime order and taking the last 16 gives the tail of the
        # last FILE, not the last 16 attempts -- which is why this stayed silent through a window
        # that was actually running at 12% yield.
        rows.sort()
        for a in alerts(rows[-16:], cap):      # recent behaviour, not the whole run
            print(a)
        return 0
    recent = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sz = sizes()
    rows = []
    for p in glob.glob(f"{SP}/wlog/pull_*_s*.log"):
        for line in open(p, encoding="utf-8", errors="replace"):
            m = LINE.search(line)
            if m:
                rows.append((m.group(1), m.group(3), m.group(4), float(m.group(5)),
                             sz.get(m.group(4), 0)))
    rows.sort()
    if recent:
        rows = rows[-recent:]
    if not rows:
        print("no pull attempts logged yet")
        return 0

    agg = {}
    for _t, verdict, _a, cost, size in rows:
        b = agg.setdefault(band(size), [0, 0, 0.0, []])
        b[0] += 1
        b[1] += verdict == "MATCH"
        b[2] += cost
        b[3].append(size)
    # MEDIAN SIZE IS PART OF THE RESULT, not decoration. A band label hides what is inside it: the
    # "small" band meant 4-byte secure-area stubs one hour and real 32-64B functions the next, so a
    # rate falling from 79% to 40% looked like a regression when the work had simply got harder.
    # Every comparison here must be read against the median, or it is comparing different pools.
    print(f"{'band':<14}{'tried':>6}{'matched':>9}{'rate':>7}{'spend':>9}{'$/match':>10}{'medB':>7}")
    for b in ("small <=64B", "med 65-256B", "large >256B"):
        if b not in agg:
            continue
        t, m, c, ss = agg[b]
        per = f"${c/m:.2f}" if m else "-"
        med = sorted(ss)[len(ss) // 2]
        print(f"{b:<14}{t:>6}{m:>9}{100*m/t:>6.0f}%{c:>9.2f}{per:>10}{med:>7}")
    t = sum(v[0] for v in agg.values())
    m = sum(v[1] for v in agg.values())
    c = sum(v[2] for v in agg.values())
    allsz = sorted(s for v in agg.values() for s in v[3])
    print(f"{'ALL':<14}{t:>6}{m:>9}{100*m/t:>6.0f}%{c:>9.2f}"
          f"{('$%.2f' % (c/m)) if m else '-':>10}{allsz[len(allsz)//2]:>7}")
    print("\nautotune all-tiers baseline for the batch fleet: $7.23/function")
    return 0


if __name__ == "__main__":
    sys.exit(main())
