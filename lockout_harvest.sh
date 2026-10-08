#!/bin/bash
# HARVEST A WEEKLY LOCKOUT. Runs zero-token work in a loop until a deadline, then returns.
#
# WHY THIS EXISTS — measured 2026-08-11. The weekly limit was exhausted on 08-05 (27 commits that day)
# and did not reset until 08-10 8pm. Commits on 08-06, 07, 08, 09: ZERO. Four dead days.
# That was NOT unavoidable. run_overlay.sh already harvests a *session* limit — the `WAIT>0` branch
# runs recover_sweep before sleeping. But a WEEKLY reset parses to more than RESET_MAXWAIT=8h, so
# until_reset.py returns -1, and the -1 path `touch USAGE_LIMIT_STOP; exit 42` — it exits WITHOUT
# running the sweep. So the single largest block of free compute in the project (4.5 days where no
# worker could possibly run, and therefore every CPU-second is strictly free) produced nothing at all.
# 75 log lines record that exact clean-stop, and supervise.sh dutifully relaunched into it every 30
# minutes for four days.
#
# The rule this encodes: a usage lockout is a REASON TO RUN THE FREE PIPELINE, not a reason to stop.
# Nothing in here spends a token. Everything in here is gated by the real `ninja check`, so a bad
# candidate costs CPU and nothing else.
#
# Usage: bash lockout_harvest.sh <seconds_to_harvest>
#   Workers must be quiesced before calling (both callers wait on every pid first) — the sweep takes
#   exclusive full builds and would corrupt a live wave's tree otherwise.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && { pwd -W 2>/dev/null || pwd; })"
SP="$(python "$KIT/kitpaths.py" state)"
REPO="$(python "$KIT/kitpaths.py" repo)"
LOG="$SP/wlog/harvest.log"
cd "$REPO" || exit 2
REGION=$(python "$KIT/buildcfg.py" --region)
DUR=${1:-3600}
END=$(( $(date +%s) + DUR ))
echo "=== lockout harvest $(date '+%m-%d %H:%M:%S'), ${DUR}s budget ===" >> "$LOG"

cycle=0
while [ "$(date +%s)" -lt "$END" ]; do
  cycle=$((cycle + 1))
  LEFT=$(( END - $(date +%s) ))
  echo "--- cycle $cycle, ${LEFT}s left" >> "$LOG"

  # 1. The standard sweep: harvest scratchpad matches, run the zero-token producers, commit whatever
  #    is recoverable per module. Its own 3h stamp keeps the producers from re-scanning every cycle.
  bash "$KIT/recover_sweep.sh" >> "$LOG" 2>&1
  [ "$(date +%s)" -ge "$END" ] && break

  # 2. PERMUTE THE NEAR-MISSES. This is the part that actually scales with a multi-day window, and it
  #    is the reason a lockout is worth harvesting at all rather than just sweeping once.
  #    quarantine/ and hold_*/ hold source a worker already wrote and a gate already rejected — 336
  #    files at the time this was written. Most are near-misses, and recipe #9 proved the largest
  #    blocking family is pure register colouring, which is a mechanical search over declaration and
  #    definition order: no model needed, a few hundred compiles each.
  #    Files are processed OLDEST-STAMP-FIRST via a per-file marker so successive cycles advance
  #    through the pool instead of re-grinding the same head of the list.
  for f in "$SP"/quarantine/*.cpp "$SP"/hold_*/*.cpp; do
    [ -f "$f" ] || continue
    [ "$(date +%s)" -ge "$END" ] && break
    mark="$SP/wlog/.permuted/$(echo "$f" | md5sum | cut -c1-16)"
    [ -f "$mark" ] && continue                     # already tried this exact file
    mkdir -p "$SP/wlog/.permuted"
    # addr = the 8 hex digits in the filename; module = the hold_ dir, or read from the file for
    # quarantine/. No addr -> nothing to gate against, skip rather than guess.
    a=$(basename "$f" | grep -oE '[0-9a-f]{8}' | head -1)
    [ -z "$a" ] && { touch "$mark"; continue; }
    case "$f" in
      *"/hold_main/"*) M=main ;;
      *"/hold_ov"*)    M=$(echo "$f" | grep -oE 'hold_ov[0-9]+' | grep -oE '[0-9]+$') ;;
      *)               M=$(python "$KIT/addr2mod.py" "$a" 2>/dev/null) ;;
    esac
    [ -z "$M" ] && { touch "$mark"; continue; }
    touch "$mark"
    timeout 600 python "$KIT/permute.py" "$M" "$a" "$f" 400 >> "$LOG" 2>&1
  done

  # 3. Breathe. A cycle that found nothing should not spin the disk for four days; the pool only
  #    changes when a sweep commits something or a producer writes a new candidate.
  LEFT=$(( END - $(date +%s) ))
  [ "$LEFT" -le 0 ] && break
  sleep $(( LEFT < 900 ? LEFT : 900 ))
done

python -c "import json;m=json.load(open('build/${REGION}/report.json'))['measures'];print('harvest end: %.2f%% (%d/%d)'%(m['matched_functions_percent'],m['matched_functions'],m['total_functions']))" >> "$LOG" 2>/dev/null \
  || echo "harvest end: (report unavailable)" >> "$LOG"
echo "=== harvest done after $cycle cycles $(date '+%m-%d %H:%M:%S') ===" >> "$LOG"
exit 0
