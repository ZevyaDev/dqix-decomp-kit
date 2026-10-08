#!/bin/bash
# FLEET HEALTH CHECK, Unix edition. Same checks, same thresholds, same alerts as health.sh.
#
#   bash health_linux.sh            loop forever, alerting when something is wrong
#   bash health_linux.sh --once     one pass and exit (cron, a CI job, a manual look)
#
# WHY A SEPARATE FILE. health.sh measures the fleet with six PowerShell expressions, one per
# question it asks. Translating them in place would mean re-verifying the calibration of every
# threshold in a script whose whole value is that those thresholds were calibrated against
# observed incidents; this file asks the same questions of `procs.py` instead, which returns the
# same fields (pid, ppid, age, cpu seconds, command line) on every platform. The alert TEXT is
# copied verbatim, so an on-call operator sees the same message and can grep this project's
# history for it either way.
#
# WHAT CHANGED IN THE MEASUREMENT, and it matters in both directions:
#
# AGE IS NOT STUCKNESS. Neither age alone nor source mtime is a liveness signal -- a 300-byte
# function legitimately takes an hour, and a worker spends long stretches compiling and gating
# without writing. The only honest test is whether the process is still BURNING CPU, so total
# consumed CPU is compared against the previous cycle: a hung worker's total stops moving while
# a working one climbs. That is what the WORKER check does, and it is why the CPU figure has to
# come from the kernel (utime+stime from /proc) rather than from a name match.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
. "$KIT/kitenv.sh"
PROG="$SP/PROGRESS.log"
STATE="$SP/wlog/health_state.txt"
INTERVAL=${HEALTH_INTERVAL:-120}
ZERO_WAVE_MIN=${ZERO_WAVE_MIN:-10}      # a wave that produced 0 files
WORKER_MAX_MIN=${WORKER_MAX_MIN:-75}    # a single headless worker running this long
STARVE_MIN=${STARVE_MIN:-150}
REPEAT_MIN=${REPEAT_MIN:-30}
ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

cd "$REPO" 2>/dev/null || { echo "ALERT repo missing: $REPO"; exit 2; }

now() { date +%s; }
mtime() { [ -f "$1" ] && stat -c %Y "$1" 2>/dev/null || echo 0; }
mins_since() { echo $(( ( $(now) - $1 ) / 60 )); }
cov_now() { "$PY" "$KIT/cov.py" 2>/dev/null || echo "(cov unavailable)"; }
commit_age_min() {
  local t; t=$(git -C "$REPO" log -1 --format=%ct 2>/dev/null)
  [ -z "$t" ] && { echo 0; return; }
  echo $(( ( $(now) - t ) / 60 ))
}

# Counts of the fleet's own processes, and total worker CPU seconds.
count() { "$PY" "$KIT/procs.py" "$@" --count 2>/dev/null | head -1; }
workers() { count --workers; }
dispatchers() { count --kind work; }
# Total CPU across every worker, in whole seconds. Compared with the previous cycle to tell a
# working session from a hung one; a rising total is a session doing something.
worker_cpu() {
  "$PY" "$KIT/procs.py" --workers 2>/dev/null | awk -F'@@@' '{s+=$4} END {printf "%d", s+0}'
}
# A worker older than $WORKER_MAX_MIN. Age from the kernel, never from a log line.
old_workers() {
  local max="$1"
  "$PY" "$KIT/procs.py" --workers 2>/dev/null | awk -F'@@@' -v m="$max" \
    '($3+0) > m { printf "%s ", $1 }'
}

stall_limit() {
  [ -n "${STALL_MIN:-}" ] && { echo "$STALL_MIN"; return; }
  # PULL_SLOTS only exists once the fleet has been configured; an absent file means "unknown
  # size", and the fallback below is the conservative reading of that. Reading it unguarded
  # prints a shell error into the monitor's own output every cycle, which trains an operator to
  # ignore the lines around it.
  local s; s=$([ -f "$SP/PULL_SLOTS" ] && tr -dc '0-9' < "$SP/PULL_SLOTS" 2>/dev/null)
  case "$s" in ''|0) s=4 ;; esac
  [ "$s" -gt 4 ] && s=4
  echo $(( 360 / s ))
}

last_ok=0
echo "health: Unix TIGHT mode (stall>$(stall_limit)m, zero-wave>${ZERO_WAVE_MIN}m, worker>${WORKER_MAX_MIN}m, every ${INTERVAL}s)"

run_cycle() {
  local alerts="" stalled commit_age

  # 1. THE FLEET IS SUPPOSED TO BE DOWN. When the operator has said so, silence is correct and
  # any alert is a false one. Checked first so a stopped fleet cannot page anybody.
  if [ -f "$SP/FLEET_STOPPED" ]; then
    echo "OK $(date '+%H:%M') fleet deliberately stopped (FLEET_STOPPED)"
    return 0
  fi

  # 2. NO COMMIT FOR TOO LONG. Calibrated per fleet size: at four slots 90m means something is
  # wrong, at one slot it is a normal gap between landings. A threshold that fires every cycle on
  # healthy work is an alert nobody reads, which is how a stray driver survives unnoticed.
  stalled=$(commit_age_min)
  if [ "$stalled" -gt "$(stall_limit)" ]; then
    alerts="${alerts}ALERT stall: no commit for ${stalled}m (limit $(stall_limit)m) and $(workers) worker(s) up"$'\n'
  fi

  # 3. A WAVE THAT RAN AND PRODUCED NOTHING. The expensive failure is not "the driver died", it
  # is "workers are burning tokens and producing nothing", and that shows up here first.
  for f in "$SP"/wip/*.log "$SP"/wlog/*wave*.log; do
    [ -f "$f" ] || continue
    [ "$(mins_since $(mtime "$f"))" -gt "$ZERO_WAVE_MIN" ] && continue
    hit=$(tail -6 "$f" 2>/dev/null | grep -oE "0 files[^\"]*|back off [0-9]+s, retry|no limit string" | tail -1)
    [ -n "$hit" ] && alerts="${alerts}ALERT burn: $(basename "$f" .log) -- ${hit} (workers ran, nothing produced)"$'\n'
  done

  # 4. A HEADLESS WORKER BURNING NOTHING. Age alone alerted every cycle while a 492-byte function
  # worked normally for 76 minutes, so the only honest liveness test is whether the process is
  # still consuming CPU: compare its own total against the previous cycle.
  local _old _cpu _prev _cpuf
  _old=$(old_workers "$WORKER_MAX_MIN" | wc -w)
  _cpuf="$SP/wlog/health_worker_cpu.txt"
  if [ "${_old:-0}" -gt 0 ]; then
    _cpu=$(worker_cpu)
    _prev=$(cat "$_cpuf" 2>/dev/null)
    if [ -n "$_cpu" ] && [ "$_cpu" = "$_prev" ]; then
      alerts="${alerts}ALERT worker: $_old headless worker(s) >${WORKER_MAX_MIN}m and burning no CPU since the last check -- hung"$'\n'
    fi
    [ -n "$_cpu" ] && echo "$_cpu" > "$_cpuf"
  else
    rm -f "$_cpuf"
  fi

  # 5. A DISPATCHER IS UP BUT SERVING NOBODY. Every other check measures activity that a HELD
  # fleet still has -- the driver is alive, the last commit is recent, the logs were touched --
  # so the one state that costs a whole afternoon (pull_all holding on an unpromoted lever, with
  # a full queue and zero workers) was watched by nothing. The hold itself is CORRECT and must
  # stay; the silence is the bug.
  local _idlef _wn _pw _since
  _idlef="$SP/wlog/.zero_workers_since"
  _wn=$(workers); [ -z "$_wn" ] && _wn=0
  _pw=$(dispatchers); [ -z "$_pw" ] && _pw=0
  if [ "$_wn" -gt 0 ] 2>/dev/null || [ "$_pw" -gt 0 ] 2>/dev/null; then
    rm -f "$_idlef"
  else
    [ -f "$_idlef" ] || date +%s > "$_idlef"
    _since=$(cat "$_idlef" 2>/dev/null); case "$_since" in ''|*[!0-9]*) _since=$(now) ;; esac
    if [ $(( ( $(now) - _since ) / 60 )) -gt "$STARVE_MIN" ]; then
      alerts="${alerts}ALERT starve: dispatcher up but zero workers for >${STARVE_MIN}m -- a queue is not being served"$'\n'
      rm -f "$_idlef"
    fi
  fi

  # 6. REPEATED LIMIT ERRORS mean the cost cap is being hit every session, not occasionally.
  local _rl="$SP/wlog/limit_guard.log"
  if [ -f "$_rl" ] && [ "$(mins_since $(mtime "$_rl"))" -le "$REPEAT_MIN" ]; then
    local n; n=$(grep -c "limit\|429\|quota" "$_rl" 2>/dev/null || echo 0)
    [ "${n:-0}" -ge 3 ] && alerts="${alerts}ALERT limit: $n limit errors in the last ${REPEAT_MIN}m -- cost caps are being hit every session"$'\n'
  fi

  if [ -n "$alerts" ]; then
    printf '%s' "$alerts"
    last_ok=0
    return 1
  fi
  if [ $(( $(now) - last_ok )) -ge 1800 ]; then
    echo "OK $(date '+%H:%M') cov $(cov_now) · workers $(workers) · last commit ${stalled}m ago"
    last_ok=$(now)
  fi
  return 0
}

if [ "$ONCE" -eq 1 ]; then
  run_cycle
  exit $?
fi

while true; do
  run_cycle
  sleep "$INTERVAL"
done