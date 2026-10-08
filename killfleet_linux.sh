#!/bin/bash
# THE kill for this project, on Unix. Use nothing else.
#
#   bash killfleet_linux.sh              kill workers only (leave supervisor/drivers running)
#   bash killfleet_linux.sh --all        kill supervisor, drivers and workers
#   bash killfleet_linux.sh --orphans    kill only workers whose parent is gone
#   bash killfleet_linux.sh --dry        report what would be killed, kill nothing
#
# WHY A SEPARATE FILE. The Windows killfleet.sh exists because of a specific Windows failure:
# `kill -9` on a `claude` worker killed the POSIX wrapper but left the real `claude.exe` alive,
# reparented to PID 1 and still spending tokens. Only a Windows process enumeration can find
# those, which is why it reaches for PowerShell. On Unix there is no such gap -- the process you
# signal IS the process that spends -- so the whole two-sided design collapses into one honest
# enumeration. The matching is kept deliberately identical: the WORKER PROMPT text, never the
# image name, so the operator's own interactive Claude session is never a candidate.
#
# Order matters: supervisor FIRST, or it relaunches the driver mid-kill; then drivers; then
# workers. Each group is SIGTERM'd, then SIGKILL'd after a grace period, because a driver killed
# while dispatching spawns one last worker and that one must not survive the stop.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
. "$KIT/kitenv.sh"
MODE="${1:-workers}"
DRY=0
case "$MODE" in
  --dry) DRY=1; MODE=workers ;;
  --all|--orphans|workers|report) ;;
  *) MODE=workers ;;
esac

say() { [ "$DRY" -eq 1 ] && echo "  would kill: $*" || echo "  killed: $*"; }

# The worker prompt. Matching this and not `claude` is what keeps an interactive session alive:
# the operator runs this kit beside their own Claude sessions.
WORKER='DQIX decomp worker|claude .*-p .*DQIX'

kill_group() {   # $1 = pattern, $2 = label, $3 = extra exclude (optional)
  local pat="$1" label="$2" excl="${3:-}" pids p n=0
  if [ -n "$excl" ]; then
    pids=$("$PY" "$KIT/procs.py" --match "$pat" --exclude "$excl" --pids 2>/dev/null)
  else
    pids=$("$PY" "$KIT/procs.py" --match "$pat" --pids 2>/dev/null)
  fi
  for p in $pids; do
    [ "$p" = "$$" ] && continue
    [ "$DRY" -eq 1 ] || kill -TERM "$p" 2>/dev/null
    n=$((n+1))
  done
  if [ "$DRY" -eq 0 ] && [ "$n" -gt 0 ]; then
    sleep 2
    for p in $pids; do kill -KILL "$p" 2>/dev/null; done
  fi
  [ "$n" -gt 0 ] && say "$n $label"
  return 0
}

echo "killfleet: mode=$MODE"
case "$MODE" in
  --all)
    kill_group "supervise\.sh" "supervisor"          # first, or it relaunches the driver mid-kill
    rm -f "$SP/supervise.pid"
    # THE DRIVER IS pull_all.sh. An earlier version of this list named only run_all/run_overlay/
    # run_main, all since deleted, so `--all` killed the supervisor, reported success, and left
    # the actual fleet spending. The old names stay because a stale checkout can still have them.
    kill_group "pull_all\.sh" "pull_all driver"
    kill_group "pull_worker\.sh" "pull workers"
    rm -f "$SP/run_all.lock" "$SP/pull_all.pid"
    kill_group "$WORKER" "workers"
    ;;
  --orphans)
    # An orphan's parent is gone, so nothing else will ever reap or supervise it.
    for p in $("$PY" "$KIT/procs.py" --match "$WORKER" --orphan-parent --pids 2>/dev/null); do
      [ "$p" = "$$" ] && continue
      [ "$DRY" -eq 1 ] || kill -KILL "$p" 2>/dev/null
      say "orphan pid $p"
    done
    ;;
  workers|report)
    kill_group "$WORKER" "workers"
    ;;
  *)
    echo "usage: killfleet_linux.sh [--all|--orphans|--dry]"; exit 2;;
esac

sleep 2
left=$("$PY" "$KIT/procs.py" --match "$WORKER" --count 2>/dev/null | head -1)
echo "  verify: ${left:-?} worker claude still alive (want 0)"
[ "${left:-1}" = "0" ] || echo "  WARNING: workers survived — investigate before assuming the fleet is down"