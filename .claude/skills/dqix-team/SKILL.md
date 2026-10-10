---
name: dqix-team
description: Coordinate a DQIX matching team of subagent workers, from the reservation issue to the published decomp pull request and the release. Use when asked to match many functions, run a team, use up a usage budget on matching, open a batch PR, or wrap up and release reservations.
---

# Coordinate a matching team

You coordinate; workers match. `team/team.py` performs every shared step, so there is one writer:
the ledger, the reservation issue (rule 20), integration and the pull request (rule 21). Workers
follow `team/WORKER.md` and only write `$SP/wip/`.

The loop is:
- reserve about two groups per worker
- keep every worker on a group of 4 functions
- re-gate everything workers report
- publish 40-120 matches per pull request

## 0. Session start

    python kit_update.py
    python team/team.py sync         fast-forward the decomp checkout
    python team/team.py status
    gh pr list -R ZevyaDev/dqix-decomp --author @me --state open

Answer review comments on your open pull requests first.

## 1. Reserve

    python team/team.py candidates --limit 40
    python team/team.py reserve --take 24 [--module 017]
    python team/team.py issue --publish     creates or edits the team's ONE open issue

`candidates` skips:
- anything delinked on `decomp-matching`
- anything in another open kit issue or changed by an open decomp PR
- skiplisted and `OPEN_RESIDUES.md` addresses

It ranks game code before library overlays, functions next to matched code first (siblings to
copy from), and 300-600 byte functions first.

Publish before anyone works on an address.

## 2. Dispatch, one worker per group of 4

    python team/team.py next --label <worker>   marks 4 rows assigned and prints the worker prompt

Hand the printed prompt, verbatim, to a subagent:
- Codex: the `dqix-matcher` agent in `.codex/agents/`
- Claude Code: an Agent

Keep 4-6 running, and refill a slot as soon as its worker returns.

For an unattended Codex run, `python team/team.py dispatch --workers 4` instead runs each group as
`codex exec`. It checks each report against `team/report.schema.json` and collects the group when
its worker exits.

## 3. Collect

    python team/team.py collect [ADDR ...]

`collect` re-gates every wip file and rejects:
- a comment other than `// USA:`
- asm or a codegen pragma
- `volatile` outside a register define

Only then does a row become MATCH. Read each MATCH before publishing it. Fix descriptions with
`team.py describe ADDR "text"`. Give a RESIDUE at most one more worker, with its residue line and
notes, then leave it for release.

## 4. Publish (every 40-120 matches, and before stopping)

    python team/team.py integrate --archive    background, long timeout
    python team/team.py pr                     dry run: title, body, prready verdict
    python team/team.py pr --open              push, gh pr create, close the issue with the PR link,
                                               open the successor issue for unfinished rows

`integrate` builds `<prefix><N>` from the current `decomp-matching` in the integration worktree,
through `finish_wave.sh` per module, in a private state directory (`<state>-integ`). This keeps
in-progress wip files out of the batch.

Without the ARM7 BIOS, each module ends `RED: sha1 mismatch`. The commit is already made, and only
the four header bytes differ. A function `finish_wave` defers stays MATCH and goes into the next
batch.

Once a pull request is open, leave its branch as it is. Do not merge or rebase
`decomp-matching` into it, and do not close it to fold it into a bigger batch: maintainers resolve
`delinks.txt` conflicts at landing. Send the next batch as a new pull request.

## 5. Promote what the batch taught

`collect` writes each worker's reported lever to `$SP/wlog/levers.tsv`. After a batch lands, run
`python levercheck.py`. For each landed lever it lists:

1. Check that `worker_src/core.md` does not already teach it.
2. Isolate the cause: the landed source with only that construct removed must stop matching.
3. Send it as a `core.md` rule citing the address, one per kit pull request, or decline it in
   `$SP/wlog/levers_declined.txt`.

[IMPROVEMENT_LOOP.md](../../../docs/IMPROVEMENT_LOOP.md) has the loop.

## 6. Stop

1. Publish what is matched (step 4).
2. Then run `python team/team.py release`. It closes the issue and frees every unfinished row.
3. If integration fails, do not release the matches. Leave the issue open and report the failing
   command and its log.
4. `team.py reclaim --matches-only` re-reserves released matches nobody took.

## Sandboxed hosts (Codex on Windows)

The sandbox cannot see the GitHub login, start Git Bash, or run frida. Run these with escalated
permissions on the first attempt:
- `kit_update.py`
- `team.py sync`, `candidates`, `reserve`, `issue`, `integrate`, `pr`, `release` and `reclaim`
- `gh`, `git fetch` and `git push`

Setup is in [docs/TEAM.md](../../../docs/TEAM.md).
