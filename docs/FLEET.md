# The autonomous fleet

The fleet runs the [WORKFLOW.md](WORKFLOW.md) loop unattended: Claude Code worker sessions match
one function each, scripts land the matches. It spends real money for as long as it runs. Windows
only; requires the `claude` CLI on PATH and logged in. Commands run from the kit checkout, with `KIT`,
`SP` and `DQIX_REPO` exported as in [WORKFLOW.md](WORKFLOW.md).

## Process tree

    supervise.sh                  relaunches pull_all.sh when it is not running and no stop flag exists
    └── pull_all.sh               keeps PULL_SLOTS slots busy; every 30 s refills, integrates, sweeps
        ├── pull_worker.sh <mod> <slot>    claim -> scaffold -> presweep -> doc -> one `claude -p` session -> verdict
        │   └── gatewatch.sh               kills a session still gating GATEWATCH_GRACE (180) s after the STOP banner
        ├── integrate_all.sh               detached: finish_wave.sh for every staged module, in the integration tree
        ├── repairsweep.py                 detached, every SWEEP_EVERY seconds: re-gates parked sources
        ├── presweep_watch.sh              colorsweeps the addresses about to be claimed
        └── progress.py                    rewrites STATE.md every STATE_EVERY seconds

`supervise.sh` checks every 15 minutes and backs off 30 minutes after `pull_all.sh` exits, so a
usage-limit stop resumes by itself. It does nothing while `STOP_PULL` or `FLEET_STOPPED` exists.
`pull_all.sh` refuses to start while `pull_all.pid` names a live process.

## Starting

    python build_worker_docs.py
    python selfcheck.py
    rm -f STOP_PULL FLEET_STOPPED
    echo 1 > PULL_SLOTS
    bash supervise.sh                     # detached; or bash pull_all.sh for one run without a supervisor

From Claude Code, launch it as a background Bash task. `bash pull_fleet.sh <main|NNN> <total_usd>
[slots]` is a bounded alternative for measuring one module; never run it alongside `pull_all.sh`.

## One worker session

`pull_worker.sh` repeats until `STOP_PULL` exists or the pool is empty:

1. `claim.py <mod>` claims one address.
2. `scaffold.py` writes `scaffold/<addr>.cpp`.
3. `presweep.py` runs colorsweep on the address's best saved artifact. MATCH stages it and no
   session is spawned; IMPROVED replaces the `clsbest/` artifact the session starts from.
4. `recipe_select.py` writes `doc_cache/<mod>_<addr>.md`: the procedure sections of
   `worker_src/core.md`, the recipes whose instruction shapes occur in this function, the
   `deadends.md` row for the address, and any handoff left by an earlier session. It stays under the
   ~58 KB a worker's file read is truncated at.
5. One `claude -p` session: tools Bash/Write/Read/Edit/Grep/Glob, `--max-budget-usd` from the size
   band, writes to `wip/<mod>/`, done only when `wgate.py` prints MATCH. It answers
   `PASS <addr>` or `BLOCKED <addr> <CLASS> <metric> <file>`. On a PASS it appends the closing lever
   to `wlog/levers.tsv`.
6. The script re-gates; the worker's own claim does not count. MATCH is copied to
   `staging/<mod>/` (or restored from `gated/`). A miss is post-swept with colorsweep, kept in
   `attempts/`, recorded by `blocker.py` in `wlog/blockers.tsv`, and `handoff.py` carries the
   session's findings into the doc for the next session on that address.

Every gate inside a session is logged to `wlog/gates/<mod>_<addr>.tsv`. `gatelog.py` stops a
session that has not improved for `STALL_NOCOMPILE` (6), `STALL_SIZE` (6) or `STALL_DIFF` (4) gates
in its phase; `wgate.py` then prints STOP and the worker must sign off.

Logs: `wlog/pull_<mod>_s<slot>.log` (claim, verdict and cost per function),
`wlog/pull_<mod>_s<slot>_<addr>.json` (session result, including `total_cost_usd`),
`wlog/pull_all.log`, `wlog/pull_integrate_<mod>.log`, `wlog/rec_<mod>.log`.

## Knobs

Files in `$SP`, re-read on every cycle or claim, so they change a running fleet without a restart.

| file | default | effect |
|---|---|---|
| `PULL_SLOTS` | 4 | concurrent worker sessions |
| `PULL_BUDGET` | 5 | passed to each slot and printed in its log; bounds nothing |
| `STOP_PULL` | absent | `pull_all.sh` exits; live slots finish their current function |
| `FLEET_STOPPED` | absent | `supervise.sh` stays down; `health.sh` alerts on anything still running |
| `CAP_SMALL` `CAP_MED` `CAP_LARGE` `CAP_LPLUS` `CAP_XL` `CAP_MASSIVE` | 1.5 3 8 12 18 25 | USD cap per session for functions of ≤64, ≤256, ≤1024, ≤2048, ≤4096, >4096 bytes |
| `CAP_NEARMISS` | 6 | lower cap when the address's recorded residue is ≤ `NEARMISS_MAXB` (16) bytes |
| `PULL_MODEL` + `PULL_MODEL_LEFT` | sonnet, 0 | model for every claim while the quota is above zero; clears itself at zero |
| `MODEL_LARGE` + `MODEL_LARGE_LEFT` | none, 0 | model for claims over 256 bytes while the quota lasts |
| `PULL_BAND` | none | `small`, `med` or `large`: serve one band only |
| `PULL_SMALL` `PULL_MED` `PULL_LMINUS` `PULL_L` `PULL_LPLUS` | open | `0` closes 1-64, 65-256, 257-512, 513-1024, 1025-2048 bytes |
| `PULL_XL` `PULL_MASSIVE` | closed | `1` opens 2049-4096 and >4096 bytes |
| `CLAIM_MAX_SIZE` | none | largest function size a slot may claim |
| `CLAIM_FOCUS` | none | `lo-hi` byte range to serve |
| `PULL_VARIETY` | 0 | with `CLAIM_FOCUS`, every Nth claim comes from outside the range |
| `BLOCKER_THRESH` | 8 | pending blockers of one class that hold claims |
| `CRACK_THRESH` | 4 | distinct open functions of one class that flag it for cracking |
| `EVOCAP_USD`, `EVOCAP_FLAT` | 150, 2 | evolve caps (below) |
| `wlog/priority_<main\|ovNNN>.txt` | none | addresses served before the band rotation; `nearmiss.py --write-priority` writes it |

Environment, read when the script starts:

| variable | default | effect |
|---|---|---|
| `INTEGRATE_EVERY` | 1800 | seconds between integration passes |
| `INTEGRATE_PENDING` | 8 | staged files that trigger an integration early |
| `SWEEP_EVERY` | 3600 | seconds between repair sweeps; 0 disables |
| `PRESWEEP_EVERY` | 300 | seconds between `presweep_watch.sh` passes |
| `STATE_EVERY` | 120 | seconds between `STATE.md` rewrites |
| `HANG_GUARD` | 7200 | wall-clock kill for a hung session; spend is limited by the cap, not this |
| `CLAIM_PRESWEEP_TIMEOUT`, `POSTSWEEP_TIMEOUT` | 240, 900 | presweep limits per claim |
| `GATEWATCH_GRACE` | 180 | seconds a session may keep gating after STOP |
| `STALL_NOCOMPILE`, `STALL_SIZE`, `STALL_DIFF` | 6, 6, 4 | unchanged gates per phase before STOP |
| `CLAIM_IGNORE_BLOCKED` | unset | re-serve addresses blocked since the last edit to `core.md` or `colorsweep.py` |

A model file takes effect only while its `_LEFT` quota is above zero; each claim decrements it and
the file empties itself at zero. Set both in one step, never above what was authorised:
`echo opus > MODEL_LARGE; echo 6 > MODEL_LARGE_LEFT`. The `PULL_MODEL` environment variable sets
the default model (sonnet).

## Holds: levers and blockers

The full loop these holds enforce is in [IMPROVEMENT_LOOP.md](IMPROVEMENT_LOOP.md).

Two checks stop claiming until knowledge reaches the doc every worker reads. `pull_all.sh` stops
refilling slots and `claim.py` serves nothing while either fails; integration continues.

- **Levers.** `levercheck.py` fails while a `wlog/levers.tsv` row, or a landed function whose
  `handwork/<addr>_board.md` carries an evolve `RULE:`/`MATCH` line, has an address that
  `worker_src/core.md` and `deadends.md` do not cite. To clear it: write the rule into `core.md` citing
  the address and run `build_worker_docs.py`, or decline it in `wlog/levers_declined.txt` as
  `<addr> <reason>`. `levercheck.py --verbose` lists them; `leverwatch.sh [--once] [interval]`
  announces each once.
- **Blockers.** `blockercheck.py` fails while one residue class has `BLOCKER_THRESH` pending rows in
  `wlog/blockers.tsv` recorded after the last `core.md` citation of one of its members. To clear it:
  crack one member and cite its address in `core.md`, or write `<CLASS> <reason>` in
  `wlog/blockers_declined.txt`. `blockercheck.py --verbose` ranks the classes.

## Kit updates under a running fleet

`kit_update.py` refuses while the fleet runs, so the fleet updates itself. Every 10 minutes
`pull_all.sh` checks the published kit. When it has moved, the dispatcher writes
`claims/UPDATE_WAITING`, and `claim.py` serves no new function: each slot ends after the function it
holds. Once no slot, integration or sweep is running, it runs `kit_update.py --dispatcher` and
restarts itself on the new code. `supervise.sh` and `presweep_watch.sh` restart themselves when the
kit's commit changes. Running work is never killed. A conflicting local kit commit stops the cycle
(`KIT UPDATE BLOCKED` in `pull_all.log`) until `kit_update.py` is run by hand.

## Integration

Slots only produce gated source. Every `INTEGRATE_EVERY` (600) seconds, or once `INTEGRATE_PENDING`
files are staged, `pull_all.sh` runs `integrate_all.sh` detached: `finish_wave.sh` for every module
with staged work, biggest first. Each runs in the integration worktree (`python integ_tree.py path`),
pushes, and fast-forwards the decomp checkout, so slots, sweeps and hand gating carry on meanwhile.
`finish_wave.sh` holds `wave.lock` for the whole run. A red gate costs one more build when the log
names the culprit (`culprits.py`); only an unnamed red bisects.

- One integration at a time. Never start `finish_wave.sh`, `integrate_fast.sh` or `integrate.py`
  (even `--dry`) by hand while `wave.lock` exists.
- Never kill a `finish_wave.sh` or `ov_recover.py` in its git phase. It spends no tokens; a kill
  mid-commit can leave a partial commit or an emptied `src/`.
- `bash integrate_fast.sh` clears the whole staged backlog with one build; run it with the fleet
  stopped.

## Evolve and crack

Two Claude Code workflows in `.claude/workflows/`, run from a session in the kit root. Both spend
subagent tokens on one function.

- **`dqix-evolve`** — population search on one function at a known residue. Arguments:
  `mod`, `addr`, `base` (file or list), `board` (a file in `handwork/` listing what was tried),
  `pop` (5), `width` (2 directed levers per generation), `explore` (0 random mutations), `cross` (1),
  `maxGens` (6), `plateau` (3), `sites`, `seedLevers`, `notes`, `seed`, `force`; `sp` and `repo` when
  the paths cannot be inferred. Every candidate is scored by `pad/evo_score.py <mod> <addr> <file>`
  (fitness 0 = MATCH; files with a pragma or inline attributes are rejected). Survivors keep the best
  file per residue signature, so a worse file that is wrong somewhere new stays alive.
- **`dqix-crack`** — independent levers in bounded rounds against one residue, sharing a board.
  Arguments: `mod`, `addr`, `base`, `board`, `baseDiff`, `roundSize` (3), `levers` (`[{key, prompt}]`),
  `sp`, `repo`.

Caps: the evolve scorer runs `python evocap.py <addr>` every generation. It sums every evolve run's
cost for the address from the workflow journals and agent transcripts and prints `EVOCAP STOP` once
the address has spent `EVOCAP_USD` (150) or its latest `EVOCAP_FLAT` (2) runs found no better best;
the workflow then returns `capped`. `force: true` bypasses it.

Routing:

1. A worker's `REGPERM` or `SCHED` residue goes to `frida/colorforce.py` (overlays) /
   `frida/schedforce.py` first; they cost CPU only.
2. Any residue left after that goes to evolve straight away. A hand probe may run beside it, never
   instead of it.
3. An evolve plateau or `EVOCAP STOP` goes to compiler research (Frida forcing of the backend,
   `pad/renum/`) grouped by blocker class, not to another evolve run. The result is a rule in
   `core.md` and a tool in `pad/renum/`.

## Watching

| command | shows |
|---|---|
| `bash health.sh` | loop; prints `ALERT <kind>: ...` lines (driver down, burn without output, hung worker, no commit, idle dispatcher, starvation, red gate, selfcheck failure, crack candidates); when quiet, an `OK` line every 30 minutes and a periodic band summary |
| `bash verdictwatch.sh [seconds]` | one line per worker MATCH/miss across every module |
| `bash leverwatch.sh --once` | exits on the first lever needing promotion |
| `bash psq.sh [--count\|--list\|--kind work\|job]` | live DQIX processes, excluding the querying process and its ancestors |
| `python progress.py --print` | rewrites and prints `STATE.md`: fleet, coverage in functions and bytes, remaining work per band, HEAD, staged-not-committed, selfcheck, recent verdicts |
| `python cov.py` | coverage from `build/<region>/report.json` (`DQIX_REGION`, default `usa`) |
| `python pullstat.py [recent_n]` | cost and conversion per size band, with median size |
| `python autotune.py [hours]` | $/function from real sessions |
| `python toolgripes.py [--hours N]` | tool complaints mined from worker verdicts |
| `python claim.py <mod> --status` | live claims in a module |

Keep an alert-only watch on a running fleet. To wait for a job, wait for the process to exit
(`until [ "$(bash psq.sh --kind job)" = "0" ]; do sleep 15; done`), not for a word in its log.

## Stopping

| command | effect |
|---|---|
| `touch STOP_PULL` | graceful: no new claims, live sessions finish their function |
| `bash fullstop.sh` | sets `FLEET_STOPPED`, `STOP_PULL`, `STOP_RESUME`; kills every worker and every driver that launches them in one pass, re-checks twice; reports CPU-only jobs (integration, sweeps) and leaves them running |
| `bash fullstop.sh --hard` | also kills integration and sweeps; then check `git -C "$DQIX_REPO" status` and `git -C "$DQIX_REPO" checkout -- src/` if `src/` was emptied |
| `bash fullstop.sh --dry` | reports both tiers, kills nothing |
| `bash killfleet.sh [--all\|--orphans\|--dry]` | escalation: workers only, or supervisor, drivers and workers |
| `bash stopat.sh '<date>'` | sleeps until the deadline, then `fullstop.sh --hard` |

`fullstop.sh` never touches an interactive `claude.exe` (workers carry ` -p `). It does not stop
monitors or `tail` watchers started by your own session; stop those separately. To resume, remove
`FLEET_STOPPED` and `STOP_PULL` and start `supervise.sh` again.

At a weekly usage limit, stop everything and do not respawn until the reset; a worker spawned into
a locked account pays its startup and dies. `limit_guard.sh` (sourced) records a lockout as a
deadline and offers `probe_limit` to test the account with one cheap call.

## Cost, measured on this project

These were measured on this pipeline at the dates shown; the remaining pool is harder than it was.

| measure | value | source |
|---|---|---|
| all tiers, 168 h to 2026-08-19 | 391 functions for $2,828.69 = $7.23/function | `autotune.py`, INVENTORY.md |
| cost per message by session length | $0.0623 at 10-39 messages, $0.1777 past 220 | INVENTORY.md |
| first pull run, 4-byte secure-area stubs | 6/6 matched, $2.73, $0.46/function (not comparable) | INVENTORY.md |
| opus, all bands, n=34 (2026-09-09) | 47% matched, $11.67 per match | session JSON |
| sonnet, all bands, n=152 (2026-09-09) | 18% matched, $29.76 per match; above 512 bytes 6 of 79 for $618 | session JSON |
| functions evolve worked, all spend included | ~47 KB landed for ~$1,200, ~$0.025/byte; typical $42-$111 per function | `evocap.py` + worker logs |
| evolve, worst case before `evocap.py` existed | ~$745 over 9 runs, never matched | `evocap.py` |

Choose the model on total pipeline cost per match: worker spend plus the evolve spend its misses
cause. Cost is dominated by context re-sent every turn, so one function per session is cheaper than
long sessions, and a cheaper per-token model that takes twice the turns is not cheaper.

## Operating rules

- Quiesce before editing any pipeline script: `touch STOP_PULL FLEET_STOPPED`, let slots finish or
  run `fullstop.sh`, confirm with `psq.sh`. Then edit, run `selfcheck.py` and `regress.py`
  (`--slow` after touching `colorsweep.py`, `wdiff.py` or `wgate.py`, `pipetest.py` after touching
  the gate), and relaunch.
- Never edit a running bash script; bash reads it by offset. Edit a copy and `mv` it over.
- Never kill a DQIX process by hand. A forked subshell carries its parent's whole command line under
  MSYS and looks like a second dispatcher. Count dispatchers only by `kill -0 $(cat pull_all.pid)`.
- After the first worker MATCH of a run, confirm a commit, not a log line or a staged file.
- After a change to a doc or prompt, confirm it reached a session: grep the worker transcript under
  `$CLAUDE_PROJECTS` for a distinctive string, and check `truncatedByTokenCap`.
- Archive `wlog/` logs under `wlog/<condition>/` whenever the harness changes, so one window
  measures one configuration.
- Read verdict prose for tool complaints (`toolgripes.py`). Fix the tool, then re-gate the saved
  attempt for free (`python presweep.py <mod> <addr> [file] --force` re-gates and sweeps it) before
  paying for another session.
- Before blaming a model or a size band, check the harness: which limits fire, which doc arrives,
  what the worker is told to give up on, and which functions it is actually being served.
- Any path that stops and waits for a human to resume is a bug unless `supervise.sh` watches it. A
  stop signal is a deadline, not a flag the resuming process clears.
