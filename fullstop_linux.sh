#!/bin/bash
# FULL STOP, in three tiers, on Unix. Same contract as the Windows fullstop.sh:
#
#   bash fullstop_linux.sh          stop TOKEN SPEND immediately; let CPU-only jobs finish
#   bash fullstop_linux.sh --hard   also kill the CPU-only jobs (integration, sweeps)
#   bash fullstop_linux.sh --dry    report what each tier would do, kill nothing
#   bash fullstop_linux.sh --monitors   only the watcher loops, leave the fleet alone
#
# TIER 1 -- SPENDERS, KILLED IMMEDIATELY. A headless `claude -p` worker spends money every second
# it lives, and every driver and supervisor is a spender too because its whole job is to launch
# more of them. They all die in ONE pass: killing the supervisor first and the workers last
# leaves a window in which the dying driver starts a fresh worker, and that worker is then
# outside the governor with nothing left to collect its output. We re-check twice after, because
# the race is real.
#
# TIER 2 -- CPU ONLY, ALLOWED TO FINISH. Integrations and the sweeps cost electricity and nothing
# else, and killing them is actively harmful: an integration killed between its clean and restore
# steps empties src/ and strands every matched file it was landing. Default is to report and leave
# them alone. --hard kills them, and then `git -C <repo> checkout -- src/` may be needed.
#
# TIER 3 -- MONITORS. TaskStop-style watch loops spend nothing, but a stop that leaves them running
# is not a stop the user can see, and restarting one stacks another copy on top.
#
# NEVER touches interactive Claude sessions: a worker is identified by ` -p ` AND the DQIX prompt
# on its command line. The operator runs this beside their own Claude sessions.
#
# WHY A SEPARATE FILE. The Windows fullstop.sh embeds four PowerShell programs with quoting that
# only survives inside its own file; porting it in place would mean rewriting the tiering that
# three emergencies depend on. This one is Unix-native end to end and shares the logic's intent,
# not its text. Both are inventoried; `--dry` on each is the check that they agree.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
. "$KIT/kitenv.sh"
MODE="${1:-soft}"
DRY=0; HARD=0; MONITORS=0
[ "$MODE" = "--dry" ] && DRY=1
[ "$MODE" = "--hard" ] && HARD=1
[ "$MODE" = "--monitors" ] && MONITORS=1

PROCS=("$PY" "$KIT/procs.py")
self_excl=(--exclude-self)

# Anything whose purpose is to run, or to launch, a paid session.
SPENDERS='supervise\.sh|run_all\.sh|run_module\.sh|run_overlay\.sh|run_main\.sh|pull_all\.sh|pull_fleet\.sh|pull_worker\.sh|restart_pull\.sh|resume_sweep\.sh|resume_one\.sh|smoke\.sh|watchdog\.sh|limit_guard\.sh'
# Local compute only: no API calls, no worker sessions. DERIVED, NOT ENUMERATED -- anything
# running out of the state dir that is not a spender and not a watcher is CPU work. A hand-kept
# list does not grow when a script is added, and a path match cannot go stale.
_cpunames=$(ls "$KIT"/*.py "$KIT"/*.sh 2>/dev/null | xargs -n1 basename 2>/dev/null \
            | sed 's/\./\\./g' | paste -sd'|' -)
CPUJOBS="dqix.sp|handwork.evo|permuter\.py${_cpunames:+|$_cpunames}"
WATCHERS='health\.sh|pull_watch\.sh|watch_verdicts\.sh|leverwatch\.sh|nearmiss_watch\.sh|presweep_watch\.sh|verdictwatch\.sh'
# Subtracted from TIER 2 because those run out of the state dir too and are killed by their own
# tiers. Assigned AFTER both halves: written above WATCHERS it expanded to a trailing `|`, and an
# empty alternative matches every string, so TIER 2 reported "none running" no matter what ran.
NOTCPU="$SPENDERS|$WATCHERS"
# The worker's own prompt, not the image name: the operator's interactive Claude must survive.
WORKER="claude .*-p .*DQIX|DQIX decomp worker"
# The watcher tier does NOT use this pattern: a monitor's `tail -f` child names no script, so a
# command-line match finds the monitor and misses what it holds open. procs.py --kind watcher
# walks the process tree instead. Kept only to name what NOT to rely on.

count() { "${PROCS[@]}" "$@" --count 2>/dev/null | head -1; }
list()  { "${PROCS[@]}" "$@" 2>/dev/null; }
# SIGTERM then SIGKILL, and re-check, because a driver killed mid-dispatch spawns one last worker.
killpat() {
  local pat="$1" excl="${2:---match-this-never-matches-anything}" n=0
  local pids
  pids=$("${PROCS[@]}" --match "$pat" --exclude "$excl" --pids 2>/dev/null)
  for p in $pids; do
    [ "$p" = "$$" ] && continue
    [ "$DRY" -eq 1 ] || kill -TERM "$p" 2>/dev/null
    n=$((n+1))
  done
  if [ "$DRY" -eq 0 ] && [ -n "$pids" ]; then
    sleep 1
    for p in $pids; do kill -KILL "$p" 2>/dev/null; done
  fi
  echo "$n"
}

# Kill a literal pid list. Used for anything already resolved by procs.py (the watcher tier),
# where re-matching by pattern would miss the children we specifically went looking for.
killpids() {   # $1 = whitespace-separated pids; echoes how many were signalled
  local n=0 p
  for p in $1; do
    [ "$p" = "$$" ] && continue
    [ "$DRY" -eq 1 ] || kill -TERM "$p" 2>/dev/null
    n=$((n+1))
  done
  if [ "$DRY" -eq 0 ] && [ "$n" -gt 0 ]; then
    sleep 1
    for p in $1; do kill -KILL "$p" 2>/dev/null; done
  fi
  echo "$n"
}

if [ "$MONITORS" -eq 1 ]; then
  echo "MONITORS ONLY $(date '+%H:%M:%S')"
  _w=$(count --kind watcher)
  [ "${_w:-0}" -eq 0 ] && { echo "  none running"; exit 0; }
  echo "  killed: $(killpids "$("$PY" "$KIT/procs.py" --kind watcher --pids 2>/dev/null)")"
  exit 0
fi

echo "FULL STOP $(date '+%H:%M:%S')${DRY:+ (dry)}"
[ "$DRY" -eq 1 ] && echo "  (dry run -- nothing will be killed)"

# Flags first and always: a loop that survives re-reads these at its next cycle and exits, and
# they stop a later launch from starting into a stop that was meant to last.
if [ "$DRY" -eq 0 ]; then
  touch "$SP/FLEET_STOPPED" "$SP/STOP_PULL" "$SP/STOP_RESUME"
  echo "  flags set: FLEET_STOPPED STOP_PULL STOP_RESUME"
else
  echo "  would set: FLEET_STOPPED STOP_PULL STOP_RESUME"
fi

echo
echo "TIER 1 -- token spenders (immediate)"
_found=$(list --match "$WORKER|$SPENDERS")
if [ -z "$_found" ]; then
  echo "  none running"
else
  echo "$_found" | awk -F'@@@' '{printf "  pid %-7s %3s min  %s\n", $1, $3, $5}'
  if [ "$DRY" -eq 0 ]; then
    echo "  killed: $(killpat "$WORKER|$SPENDERS")"
    for _i in 1 2; do
      sleep 2
      left=$(count --match "$WORKER|$SPENDERS")
      [ "${left:-0}" -eq 0 ] && break
      echo "  $left reappeared -- killing again"
      killpat "$WORKER|$SPENDERS" >/dev/null
    done
  fi
fi
left=$(count --match "$WORKER|$SPENDERS")
echo "  spenders remaining: ${left:-0}"

echo
echo "TIER 2 -- CPU-only jobs"
_cpu=$(list --match "$CPUJOBS" --exclude "$NOTCPU")
if [ -z "$_cpu" ]; then
  echo "  none running"
elif [ "$HARD" -eq 1 ] && [ "$DRY" -eq 0 ]; then
  echo "$_cpu" | awk -F'@@@' '{printf "  pid %-7s %3s min  %s\n", $1, $3, $5}'
  echo "  killed: $(killpat "$CPUJOBS" "$NOTCPU")"
  for _i in 1 2; do
    sleep 2
    _again=$(list --match "$CPUJOBS" --exclude "$NOTCPU")
    [ -z "$_again" ] && break
    echo "  $(echo "$_again" | wc -l) reappeared -- killing again"
    killpat "$CPUJOBS" "$NOTCPU" >/dev/null
  done
  echo "  CHECK THE REPO: an integration killed mid-flight empties src/."
  echo "    git -C $REPO status --short | head"
  echo "    git -C $REPO checkout -- src/      # if it shows mass deletions"
  _cpu=""
else
  echo "$_cpu" | awk -F'@@@' '{printf "  pid %-7s %3s min  %s   (left to finish)\n", $1, $3, $5}'
  echo "  These spend no tokens. Killing an integration pass loses matched work; let it land."
  echo "  Force with: bash \"$KIT/fullstop_linux.sh\" --hard"
fi

echo
echo "TIER 3 -- monitors and watcher children"
# --kind watcher, not a name match: a monitor's `tail -f` child carries no script name of its
# own, so matching command lines finds the monitor and misses every process it is holding open.
# procs.py walks the process tree and returns the children too.
_w=$(count --kind watcher)
if [ "${_w:-0}" -eq 0 ]; then
  echo "  none running"
elif [ "$DRY" -eq 1 ]; then
  list --kind watcher | awk -F'@@@' '{printf "  pid %-7s %3s min  %s\n", $1, $3, $5}'
  echo "  ${_w} watcher process(es) would be killed"
else
  echo "  killed: $(killpids "$("$PY" "$KIT/procs.py" --kind watcher --pids 2>/dev/null)")"
fi

# Locks belong to whatever is still holding them. Clearing wave.lock while an integration still
# runs is precisely the failure the lock exists to prevent.
if [ "$DRY" -eq 0 ] && [ -z "$_cpu" ]; then
  rm -f "$SP/run_all.lock" 2>/dev/null
  # `rm -f` only removes a FILE, and a live wave.lock is a directory holding its owner's pid file,
  # so this cleanup could never fire on a real lock -- the one case it exists for.
  if [ -d "$SP/wave.lock" ]; then
    rm -rf "$SP/wave.lock" 2>/dev/null && echo "  cleared wave.lock"
  fi
elif [ -n "$_cpu" ]; then
  echo "  locks left in place (a CPU job still holds them)"
fi

echo
_wleft=$(count --kind watcher)
echo "STOPPED. token spend: $([ "${left:-0}" -eq 0 ] && echo "halted" || echo "STILL RUNNING (${left})")\
 $([ "${_wleft:-0}" -eq 0 ] && echo "" || echo ", ${_wleft} watcher(s) STILL RUNNING")"