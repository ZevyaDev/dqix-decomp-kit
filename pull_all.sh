#!/bin/bash
# CONTINUOUS budget-driven dispatch: keep N slots working, recycle each one as it spends its share,
# integrate what lands, and keep going until every module's pool is empty.
# Usage: bash pull_all.sh          (run detached; stop with `touch $SP/STOP_PULL`)
#
# WHY THIS REPLACES THE BATCH DRIVER. run_module fixed three things in advance -- functions per
# worker, seconds per worker, workers per wave -- and none of them bounded what actually matters.
# Two sessions took $1,135 of one week's $2,828 without exceeding any of them, because a fast worker
# burns turns inside its time limit. Here the only hard limit is money, per unit of work, and both
# knobs are live:
#
#   PULL_SLOTS    how many run at once   (burn rate)
#   PULL_BUDGET   dollars per slot-run   (how far one slot goes before it is recycled)
#
# Both are re-read every cycle, so either can be changed while this runs -- no restart, no redeploy.
# A slot that exhausts its budget exits and is respawned with a fresh one, which is the recycling:
# sessions stay short (cost per message climbs with length) while the slot keeps working.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && { pwd -W 2>/dev/null || pwd; })"
SP="$(python "$KIT/kitpaths.py" state)"
REPO="$(python "$KIT/kitpaths.py" repo)"
LOG="$SP/wlog/pull_all.log"
INTEGRATE_EVERY=${INTEGRATE_EVERY:-600}      # seconds between integration passes
# THE FREE SWEEP HAS TO RUN BY ITSELF. repairsweep re-gates every parked source and stages what a
# new colorsweep rule now closes -- 111 of 369 parked files turned out to be finished matches the
# one time it was run over the whole pool. Nothing has launched it automatically since run_all.sh
# was retired, so it only ever ran when someone remembered, which is not a pipeline.
SWEEP_EVERY=${SWEEP_EVERY:-3600}              # seconds between repair sweeps (0 disables)

# REFUSE TO BE THE SECOND DISPATCHER. supervise.sh starts pull_all whenever the pid file is absent
# or names a dead process -- correct on its own -- but an operator restart that deletes the pid file
# while the old loop is still alive gives you TWO dispatchers, each refilling its own slot. That
# doubles spend and silently breaks PULL_SLOTS=1. Measured 2026-09-08: two loops ran from 16:59.
if [ -f "$SP/pull_all.pid" ] && [ "$(cat "$SP/pull_all.pid" 2>/dev/null)" != "$$" ] \
   && kill -0 "$(cat "$SP/pull_all.pid" 2>/dev/null)" 2>/dev/null; then
  echo "$(date '+%H:%M') another pull_all is alive as $(cat "$SP/pull_all.pid") -- not starting a second" >> "$LOG"
  exit 0
fi
rm -f "$SP/STOP_PULL"
echo "=== pull_all up $(date '+%m-%d %H:%M:%S') (pid $$) ===" >> "$LOG"
echo $$ > "$SP/pull_all.pid"
trap 'rm -f "$SP/pull_all.pid"' EXIT

read_knob() {   # $1 = file, $2 = default
  local v; v=$(tr -dc "0-9." < "$SP/$1" 2>/dev/null)
  case "$v" in ''|*[!0-9.]*) echo "$2" ;; *) echo "$v" ;; esac
}

declare -A slot_pid
last_integrate=$SECONDS
last_sweep=$SECONDS
last_state=0                      # 0, not $SECONDS: write STATE.md on the very first loop
last_claimed=""
sweep_pid=""
update_wait=""; update_blocked=""; last_kitcheck=$((SECONDS - 600)); update_since=0
claim_held=""; last_claimnote=$((SECONDS - 600))
rm -f "$SP/claims/UPDATE_WAITING"

while :; do
  [ -e "$SP/STOP_PULL" ] && { echo "$(date '+%H:%M') stop flag" >> "$LOG"; break; }

  SLOTS=$(read_knob PULL_SLOTS 4)
  BUDGET=$(read_knob PULL_BUDGET 5)

  # Retire finished slots, then refill up to SLOTS. Lowering PULL_SLOTS takes effect by simply not
  # refilling -- running work is never killed mid-function, so no spend is ever thrown away.
  for s in "${!slot_pid[@]}"; do
    kill -0 "${slot_pid[$s]}" 2>/dev/null || unset "slot_pid[$s]"
  done

  # LEVER GATE -- fail closed, and it must stay that way. An unpromoted lever is a trick one worker
  # paid to discover that no later worker can reach, because recipe_select only ever offers core.md
  # sections. Every function claimed past that point pays full price to rediscover it.
  #
  # leverwatch + selfcheck invariant 21 + the STATE.md line already REPORTED this, and all three were
  # ignored seven times in one run while the fleet kept spending. A notification is not a control.
  # So the check now blocks the only thing that costs money: claiming the next function.
  #
  # Two deliberate ways out, both cheap: cite the address in core.md, or write it off in
  # wlog/levers_declined.txt with a reason. Doing nothing is not one of them.
  # A HOLD MUST NOT SKIP THE REST OF THE LOOP. `sleep 30; continue` restarts the iteration, and
  # integration lives BELOW here -- so a hold stopped matched work from ever landing while the
  # already-running slots, which claim through claim.py on their own, kept spending. Measured
  # 2026-09-08: held 03:02, last integration 01:07, three proven matches stranded for six hours and
  # ~$18 of further claims made during the hold. Hold the CLAIMS, never the landings.
  hold_claims=""
  if ! (python "$KIT/levercheck.py" >/dev/null 2>&1); then
    if [ -z "$lever_held" ]; then
      echo "$(date '+%H:%M') HOLDING: unpromoted lever(s) -- no new claims until core.md cites them" >> "$LOG"
      (python "$KIT/levercheck.py" --verbose 2>&1 | sed 's/^/  /') >> "$LOG"
      lever_held=1
    fi
    hold_claims=1
  elif [ -n "$lever_held" ]; then
    echo "$(date '+%H:%M') levers promoted -- claiming resumed" >> "$LOG"; lever_held=""
  fi

  if ! (python "$KIT/blockercheck.py" >/dev/null 2>&1); then
    if [ -z "$blocker_held" ]; then
      echo "$(date '+%H:%M') HOLDING: a blocker class is over threshold -- crack one member or decline the class" >> "$LOG"
      (python "$KIT/blockercheck.py" --verbose 2>&1 | sed 's/^/  /') >> "$LOG"
      blocker_held=1
    fi
    hold_claims=1
  elif [ -n "$blocker_held" ]; then
    echo "$(date '+%H:%M') blocker class addressed -- claiming resumed" >> "$LOG"; blocker_held=""
  fi

  if [ -z "$update_wait" ] && [ -z "$update_blocked" ] && [ $((SECONDS - last_kitcheck)) -ge 600 ]; then
    last_kitcheck=$SECONDS
    _behind=$(python "$KIT/kitpaths.py" behind 2>/dev/null | tr -dc '0-9')
    if [ "${_behind:-0}" -gt 0 ]; then
      update_wait=1
      update_since=$SECONDS
      mkdir -p "$SP/claims"; date > "$SP/claims/UPDATE_WAITING"
      echo "$(date '+%H:%M') KIT UPDATE WAITING ($_behind commit(s)): no new claims; updating once running work finishes" >> "$LOG"
    fi
  fi
  [ -n "$update_wait" ] && hold_claims=1

  for ((s=1; s<=SLOTS; s++)); do
    [ -n "$hold_claims" ] && break
    [ -n "${slot_pid[$s]}" ] && continue
    # claim.py EXITS 3 AND PRINTS NOTHING WHEN IT IS SERVING BY REFUSAL, NOT BECAUSE THE POOL IS
    # EMPTY. That is documented (AGENTS.md: "hands out no new work (exit 3) until you update") and it
    # happens on a stale kit, on a blocker, and on the lever gate. Reading that empty stdout as
    # "every pool drained" is what turns any transient refusal into a dead fleet: STOP_PULL is
    # touched, the dispatcher exits, and nothing restarts it. So the exit code is read BEFORE
    # concluding the pool is drained -- an empty result with a non-zero exit means SERVING NOTHING,
    # which must never stop the fleet.
    # `$?` AFTER A PIPELINE IS THE LAST STAGE'S STATUS, and there is no `set -o pipefail` here, so
    # `$(claim.py | tr); _rc=$?` reads TR's status -- always 0 -- and silently reintroduces the exact
    # bug this block exists to fix. Capture claim.py's own status FIRST, then clean the value.
    MOD=$(python "$KIT/claim.py" --best 2>/dev/null); _rc=$?
    MOD=$(printf '%s' "$MOD" | tr -d '\r\n ')
    if [ "$_rc" -eq 0 ] && [ -z "$MOD" ]; then
      echo "$(date '+%H:%M') every pool drained -- nothing left to claim" >> "$LOG"
      touch "$SP/STOP_PULL"; break
    fi
    if [ "$_rc" -ne 0 ] || [ -z "$MOD" ]; then
      # Refusal, not exhaustion. Log it once per cooldown and leave the slots unfilled so the next
      # iteration retries; a fleet that stops asking because it was told "no" never recovers.
      if [ -z "$claim_held" ] || [ $((SECONDS - last_claimnote)) -ge "${CLAIM_NOTE_EVERY:-300}" ]; then
        echo "$(date '+%H:%M') claim.py refusing (exit $_rc) -- not drained, retrying in ${CLAIM_NOTE_EVERY:-300}s" >> "$LOG"
        last_claimnote=$SECONDS; claim_held=1
      fi
      break
    fi
    claim_held=""
    bash "$KIT/pull_worker.sh" "$MOD" "$s" "$BUDGET" &
    slot_pid[$s]=$!
    echo "$(date '+%H:%M') slot $s -> $MOD \$$BUDGET (pid ${slot_pid[$s]})" >> "$LOG"
  done

  # INTEGRATION IS SEPARATE AND SERIALISED. Slots only produce gated source; finish_wave owns the
  # wave lock, the drift culling, the sha1 gate and the push. Running it on a timer rather than per
  # match keeps the ~6-minute build cost amortised over everything that landed since the last pass.
  # NEVER BLOCK THE WHOLE FLEET ON ONE INTEGRATION. This used to run finish_wave inline, so a
  # 20-minute main integration left every slot unrefilled and the fleet at zero workers -- observed
  # 17:40-18:00. Integration must exclude its own module (a worker writing into a module dir while
  # finish_wave moves files there is the hazard the quiesce rule exists for) but nothing stops slots
  # working OTHER modules meanwhile. So: run it detached, publish which module is busy, and let
  # claim.py steer new slots elsewhere until it clears.
  if [ -n "$integ_pid" ] && ! kill -0 "$integ_pid" 2>/dev/null; then
    integ_pid=""; rm -f "$SP/claims/INTEGRATING"
  fi
  # TIME IS NOT THE ONLY TRIGGER. A pure 30-minute timer never fires if the dispatcher is restarted
  # more often than that -- which is exactly what happened while tuning: 12 matched functions sat
  # unintegrated for 78 minutes and coverage stayed flat while the work was already done. Integrate
  # once enough has piled up, whichever comes first.
  # COUNT STAGED WORK, NOT UNTRACKED src/. Workers were moved to writing into staging/<module>/ so a
  # wave integrating one module could not sweep another's in-flight files -- but this trigger still
  # counted untracked files in src/, which is now always zero. Integration silently stopped firing
  # while 78 matched functions accumulated across ten modules. A trigger that can never fire is worse
  # than no trigger, because the pipeline looks healthy the whole time.
  _pending=$(ls "$SP"/staging/*/*.cpp 2>/dev/null | wc -l)
  if [ -z "$integ_pid" ] && { [ $((SECONDS - last_integrate)) -ge "$INTEGRATE_EVERY" ] \
       || [ "${_pending:-0}" -ge "${INTEGRATE_PENDING:-8}" ]; }; then
    last_integrate=$SECONDS
    _mods=$(ls -d "$SP"/staging/*/ 2>/dev/null \
            | while read -r d; do echo "$(ls "$d"*.cpp 2>/dev/null | wc -l) $(basename "$d")"; done \
            | sort -rn | awk '$1>0{print $2}' | sed 's/^ov//')
    if [ -n "$_mods" ]; then
      mkdir -p "$SP/claims"; echo $_mods > "$SP/claims/INTEGRATING"
      echo "$(date '+%H:%M') integrate $(echo $_mods) (detached, in the integration tree)" >> "$LOG"
      bash "$KIT/integrate_all.sh" >> "$SP/wlog/pull_integrate.log" 2>&1 &
      integ_pid=$!
    fi
  fi

  # KEEP THE ADVANCE SWEEPER ALIVE. presweep_watch is a LOOP, not a pass: started once by hand it
  # died with its session on 2026-09-08 and nothing noticed for a day, during which two paid workers
  # hand-derived r11 and r35 -- rules colorsweep already had and would have applied for a compile.
  # The script guards its own pid file, so calling it when it is already up is a no-op.
  if ! kill -0 "$(cat "$SP/presweep_watch.pid" 2>/dev/null)" 2>/dev/null; then
    bash "$KIT/presweep_watch.sh" "${PRESWEEP_EVERY:-300}" >> "$SP/wlog/presweep_watch.log" 2>&1 &
    echo "$(date '+%H:%M') presweep_watch (re)started" >> "$LOG"
  fi

  # THE FREE SWEEP, detached and never more than one at a time. It costs no tokens and it is the
  # only thing that revisits parked work after a new colorsweep rule lands, so it must not depend on
  # an operator remembering. Skipped while an integration holds the wave lock: both want the tree.
  if [ -n "$sweep_pid" ] && ! kill -0 "$sweep_pid" 2>/dev/null; then sweep_pid=""; fi
  if [ "$SWEEP_EVERY" -gt 0 ] && [ -z "$sweep_pid" ] && [ -z "$integ_pid" ] && [ -z "$update_wait" ] \
     && [ $((SECONDS - last_sweep)) -ge "$SWEEP_EVERY" ]; then
    last_sweep=$SECONDS
    echo "$(date '+%H:%M') repair sweep (detached)" >> "$LOG"
    python -u "$KIT/repairsweep.py" >> "$SP/wlog/repairsweep_auto.log" 2>&1 &
    sweep_pid=$!
  fi

  _claimed=$(ls -d "$SP"/claims/*/[0-9a-f]*/ 2>/dev/null | sort | tr '\n' ' ')
  if [ "$_claimed" != "$last_claimed" ]; then
    last_claimed=$_claimed
    python "$KIT/reserved.py" --publish >> "$LOG" 2>&1 &
  fi

  # STATE.md IS GENERATED, NEVER HAND-MAINTAINED. Sessions used to keep a "State as of <date>" block
  # inside the dqix-plan / dqix-continue skills and edit it by hand every time something moved --
  # which defeats the point of a skill and is stale the moment a wave commits. The skills now carry
  # procedure only and point at STATE.md; this keeps it current for free. Refreshed on a timer
  # rather than every loop because it shells out to the process list.
  if [ $((SECONDS - last_state)) -ge "${STATE_EVERY:-120}" ]; then
    last_state=$SECONDS
    python "$KIT/progress.py" >/dev/null 2>&1 || true
  fi

  # A KIT UPDATE MUST NOT BE ABLE TO LATCH THE FLEET OFF FOREVER.
  #
  # Two ways this used to strand the whole fleet, both observed on 2026-10-13:
  #
  #   1. EXIT 3 SET `update_blocked` AND NOTHING EVER CLEARED IT. `update_blocked` gates the kitcheck
  #      above, so once it was set the kit could never be retried -- while claim.py serves nothing at
  #      all while the kit is behind (exit 3, per AGENTS.md). A transient uncommitted-kit moment
  #      therefore became a PERMANENT stall: every slot asked claim.py for work, got nothing, and
  #      `claim.py --best` returning empty reads as "every pool drained", which touches STOP_PULL and
  #      ends the dispatcher. A latched flag plus a fail-closed claim server is a deadlock with no
  #      way out but a hand edit.
  #
  #   2. THE DISPATCH CONDITION REQUIRED EVERY SLOT TO BE EMPTY, WITH NO DEADLINE. A worker that
  #      runs long (they are budgeted in dollars, not seconds) keeps `${#slot_pid[@]}` non-zero, so
  #      `update_wait` never cleared and claiming stayed held for as long as that worker lived.
  #
  # The fix for both is the same shape as the levercheck fix: a gate that RECHecks rather than
  # latching. Blocked now gets a bounded cooldown and then retries on its own; the wait gets a
  # deadline after which we stop waiting for a clean tree and update anyway, because running on a
  # kit that is N commits behind is strictly better than running on no work at all.
  if [ -n "$update_blocked" ] && [ $((SECONDS - update_blocked)) -ge "${UPDATE_BLOCKED_RETRY:-900}" ]; then
    echo "$(date '+%H:%M') kit update retrying after block (${UPDATE_BLOCKED_RETRY:-900}s)" >> "$LOG"
    update_blocked=""
  fi

  # A slot that will not drain must not hold the fleet off. Past the deadline, proceed regardless:
  # kit_update.py --dispatcher is itself serialised against the wave lock, so attempting it while a
  # worker runs is safe -- it declines rather than racing.
  _slots_busy=${#slot_pid[@]}
  if [ -n "$update_wait" ] && [ $((SECONDS - update_since)) -ge "${UPDATE_WAIT_MAX:-1800}" ]; then
    echo "$(date '+%H:%M') KIT UPDATE WAITING exceeded ${UPDATE_WAIT_MAX:-1800}s ($_slots_busy slot(s) still running) -- updating anyway" >> "$LOG"
    update_wait=""
  fi

  if [ -n "$update_wait" ] && { { [ "$_slots_busy" -eq 0 ] && [ -z "$integ_pid" ] && [ -z "$sweep_pid" ]; } \
       || [ $((SECONDS - update_since)) -ge "${UPDATE_WAIT_MAX:-1800}" ]; }; then
    python "$KIT/kit_update.py" --dispatcher >> "$LOG" 2>&1
    case $? in
      0) echo "$(date '+%H:%M') kit updated -- restarting the dispatcher on the new code" >> "$LOG"
         rm -f "$SP/claims/UPDATE_WAITING"
         exec bash "$KIT/pull_all.sh" ;;
      3) echo "$(date '+%H:%M') KIT UPDATE BLOCKED by local kit changes -- retrying in ${UPDATE_BLOCKED_RETRY:-900}s, claiming stays OPEN" >> "$LOG"
         # NOT a claim hold: claiming continues, so a blocked kit costs throughput but cannot stop it.
         # Without the retry this flag was write-once and the fleet could never recover unattended.
         update_blocked=$SECONDS ;;
    esac
    update_wait=""; update_since=0; rm -f "$SP/claims/UPDATE_WAITING"
  fi

  sleep 30
done

echo "$(date '+%H:%M') pull_all exiting; waiting for live slots" >> "$LOG"
for p in "${slot_pid[@]}" $integ_pid; do wait "$p" 2>/dev/null; done
echo "$(date '+%H:%M') pull_all done" >> "$LOG"
