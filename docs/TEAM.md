# Matching as a team of agents

`team/team.py` runs batch matching for one coordinator session and its subagent workers. The
`dqix-team` skill is the procedure; `team/WORKER.md` is each worker's brief.

It is how one Codex session produced decomp PRs #85, #86, #87 and #88 in an afternoon: 177
functions, all landed.

It adds no new gate or landing path:
- `wgate.py` decides a match.
- `finish_wave.sh` lands it, in the integration worktree.
- `prready.py decomp` must print READY before `gh pr create`.

What it adds is the bookkeeping around them:
- a ledger in `$SP/team/`
- one reservation issue, kept in step with the ledger
- groups of four for workers
- a re-gate and quality check of every reported match
- one integration per batch, in a private state directory
- a pull request body listing every function

## Setup

The decomp, built, and the kit, initialised, as in [SETUP.md](SETUP.md). Then:

| host | do |
|---|---|
| Claude Code | nothing more: the skill spawns Agents with the printed worker prompt |
| Codex | open Codex in the kit checkout; mark it trusted; run `python team/setup_codex.py` with the Python that has the kit's dependencies |

`setup_codex.py` writes `.codex/config.toml`, which is untracked. It sets up every Codex command
and subagent in this checkout:
- that Python environment, with the `DQIX_*` paths
- git trust for the folder, since the Windows sandbox user does not own the checkout
- git's OpenSSL TLS backend, since schannel fails inside the sandbox
- write access to the folder that holds the kit, the decomp and the state
- network access
- a cap of 6 subagents

`.codex/agents/dqix-matcher.toml` is the worker. `.codex/hooks.json` mirrors
`.claude/settings.json`: it runs `kit_update.py` at session start, and `prready.py --hook` refuses
`gh pr create`. Review them once with `/hooks`.

Codex's Windows sandbox cannot see the GitHub login, start Git Bash, or run frida (it hangs). The
skill and `team/WORKER.md` say which commands to run with escalated permissions.

## Configuration

`$SP/team/config.json` holds:
- `tag`, the issue and PR title prefix, default `[Codex]`
- `branch_prefix`, default `codex/overlay-batch-`
- `commit_trailer` and `pr_footer`
- `min_size` and `max_size` for `candidates`

The fork owner comes from the decomp checkout's `origin`, and the repositories from `kitpaths.py`.
