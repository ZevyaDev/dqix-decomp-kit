@AGENTS.md

## Claude Code

Skills in `.claude/skills/` and workflows in `.claude/workflows/` load when Claude Code opens this
directory.

| name | use |
|---|---|
| `/dqix-plan` | run the standing plan: one function at a time, gate it, land it or record why, automate each crack |
| `/dqix-continue` | a fresh session after a limit, a crash or a long session: clear orphans, read state off disk, repair, re-enter the plan |
| `/dqix-status` | where things are: fleet, coverage, what moved, what needs a decision |
| `/dqix-stop` | stop everything now and verify nothing survived |
| `/dqix-hand-match <addr>` | close one function in this session |
| `/dqix-naming` | help with the naming pass: setup, reserve, name, audit, land, pull request |
| `dqix-evolve` workflow | population search on one function at a known residue; capped by `evocap.py` |
| `dqix-crack` workflow | independent levers in rounds against one residue |

Create and change files with the Write and Edit tools.
