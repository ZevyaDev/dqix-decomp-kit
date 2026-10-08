# Contributing

Two repositories take contributions:

| what | where |
|---|---|
| matched functions | [ZevyaDev/dqix-decomp](https://github.com/ZevyaDev/dqix-decomp), branch `decomp-matching` |
| tool fixes, new levers, docs | [ZevyaDev/dqix-decomp-kit](https://github.com/ZevyaDev/dqix-decomp-kit) |

## Avoid duplicate work

`claim.py` claims are local to one machine. An address is reserved when it is:

- listed in an OPEN issue in the kit repository, or
- changed by an OPEN pull request on ZevyaDev/dqix-decomp.

An address listed only in a CLOSED issue that has no pull request, and that is not landed in
`decomp-matching`, is free: its owner stopped or failed. Take it.

Keep ONE open issue for everything you are actively working on, never one per function:

1. Skip every reserved address, then open a single issue listing each address you are taking, one
   per line (`main 0205faf4`, `ov017 021bb000-021bc000`).
2. Edit that issue as you add or drop addresses.
3. The moment you open the pull request for those addresses, close the issue with a comment naming
   it (`PR: ZevyaDev/dqix-decomp#27`). Do not wait for the merge; the open pull request now holds
   the reservation. If you stop without a pull request, close the issue saying so.
4. Open a new issue for the next batch.

## Matched functions

1. Fork `ZevyaDev/dqix-decomp` and set it up as in [SETUP.md](SETUP.md): your fork as `origin`,
   ZevyaDev as `zevya`, branch `decomp-matching`.
2. Start from the current branch: `git pull --rebase zevya decomp-matching` on a clean tree.
3. Match and land as in [WORKFLOW.md](WORKFLOW.md). `finish_wave.sh` commits and pushes to your
   fork's `decomp-matching`.
4. Pull both again, right before the pull request, every time (AGENTS.md rule 21):

       python kit_update.py                                  # in the kit
       git pull --rebase zevya decomp-matching               # in the decomp; rebase, never merge
       python tools/configure.py usa && ninja check
       python prready.py decomp                              # in the kit; must print READY

   Push the rebased branch to your fork (`git push --force-with-lease origin decomp-matching`).
5. Open a pull request from your fork's `decomp-matching` against `ZevyaDev/dqix-decomp`
   `decomp-matching`. Send the next batch on a new branch and pull request; never add commits to
   one already open.

A pull request is accepted when:

- every commit leaves `ninja check` green, and `ninja sha1` OK when you have the BIOS dump
- each function is byte-exact and wired into `symbols.txt` / `delinks.txt` (`integrate.py` does this
  through the landing scripts)
- definitions export the names `symbols.txt` binds, and each carries its `// USA:` tag
- there is no hand assembly outside `asm_allow.txt`, no codegen `#pragma`, and nothing added to
  `tools/cc_overrides.txt` or `tools/cc_flag_overrides.txt`
- the source reads like code a developer wrote: typed structs and members, no comments beyond the
  `// USA:` tag unless a line needs one
- it changes nothing outside the functions it lands, apart from header or config changes those
  functions need; never `.github/`, `tools/` or another file a merge resolved to your older copy
- a symbol renamed in one region's `symbols.txt` is renamed in every region that has it
- `python prready.py decomp` prints `READY` against the current `decomp-matching`

USA stays the matching reference, and acceptance checks `usa`.

A near miss is not a pull request to the decomp. If you spent real effort ruling forms out, send a
row for `worker_src/deadends.md` to the kit; if you found a lever, send the rule (below).

## Tool fixes and new levers

Every recipe, rule, repair, tool fix and automation an agent finds comes back here, in the session
that found it. Where each belongs and what proof it needs: [IMPROVEMENT_LOOP.md](IMPROVEMENT_LOOP.md).

1. Commit on your kit checkout; `kit_update.py` keeps unpublished commits on top of every update, so
   you never have to choose between sharing and staying current.
2. Push to your fork of the kit and open the pull request against `ZevyaDev/dqix-decomp-kit` `main`
   (`gh pr create -R ZevyaDev/dqix-decomp-kit`).

Before opening it, in this order, every time (AGENTS.md rule 21):

    python kit_update.py           # your commits are rebased onto the published kit
    git -C "$(python kitpaths.py repo)" pull --rebase zevya decomp-matching
    python selfcheck.py
    python regress.py              # add --slow after touching colorsweep.py, wdiff.py or wgate.py
    python pipetest.py             # after touching wgate.py, classify.py or integrate.py
    python prready.py kit          # must print READY

`prready.py kit` refuses a dead-end row for an address already matched and a `core.md` rule citing an
address that is not landed: land the match first, then send the rule.

- A new script gets a line in `INVENTORY.md`; `selfcheck.py` fails on an uninventoried script.
- A fix for a fault that happened gets a `regress.py` case that fails without the fix.
- A new `colorsweep.py` rule gets a `regress.py` case and an instance in `pad/ruleprobe.cpp`.
- A lever goes into `worker_src/core.md` as a rule citing the address it was found on, stated in a
  few lines with no history. Run `python build_worker_docs.py` and confirm the text appears in the
  built `worker_*.md`.
- Fix the shared code path; never fork a script per module.
- Read paths through `kitpaths.py`, the compiler and flags through `buildcfg.py`, source directories
  through `srcdir.py`. No machine-specific paths.
- Write files with an editor, not a shell heredoc.
- Edit skills in `.claude/skills/` and agent instructions in `AGENTS.md`. `.agents/skills/` is
  generated by `kit_init.py`; a skill that uses no Claude Code-only tool belongs in
  `PORTABLE_SKILLS` there.
