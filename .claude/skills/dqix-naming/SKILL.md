---
name: dqix-naming
description: Help with the DQIX naming pass — set up the melonDS fork and play data, reserve keys, name symbols with code and in-game evidence, get the rows audited, land them and open the pull request. Use when the user says "help with the naming pass", "name symbols", "naming", or invokes /dqix-naming.
---

# Help with the naming pass

    KIT   the kit checkout: $DQIX_KIT when set, else this session's working directory

Every step below is spelled out in `$KIT/naming/HANDOFF.md`; read it whole first, then
`$KIT/naming/BRIEF.md`. Both are binding.

1. `python kit_update.py`; re-read every file it prints as `RE-READ`.
2. Setup: the decomp as in `docs/SETUP.md` (your fork of ZevyaDev/dqix-decomp as `origin`, ZevyaDev as
   `zevya`, the USA base ROM extracted, `ninja check` green), then HANDOFF.md "Setup (required)": the
   ZevyaDev/melonDS `debug` headless build and its Python package, `python naming/play.py fetch`.
   Nothing else starts until `python naming/play.py check` prints `READY`; fix each `MISSING` line.
3. Reserve: pick a subsystem with `python naming/rank.py --top 50` (it leaves out keys others hold),
   then `python naming/reservations.py take KEY...` before any work on them. It refuses keys someone
   else holds and keeps your one `Naming:` kit issue; never work on a key it refused.
4. Name each key by BRIEF.md: `naming/dossier.py`, callers' source, `naming/dyn.py probe` in a scenario
   (write one in `naming/scenarios/` when none reaches the behavior), rows into
   `python naming/names.py import`.
5. Audit: a second agent that did not write the rows gets only the rows, the dossiers and BRIEF.md's
   "Audit" section; `names.py accept` what it passes, `names.py reject KEY WHY` the rest.
6. Land and send it as HANDOFF.md "Contributing names" says: `namesland.sh --dry`, `namesland.sh`,
   a kit pull request for new scenarios, then the decomp pull request with
   `python naming/names.py evidence <commit>` as its body; close the reservation issue naming it.
   When `origin` is ZevyaDev/dqix-decomp itself, `namesland.sh` has already landed the names: close
   the issue naming the commit instead.

Never edit source by hand, never add comments, never take a name from outside our own analysis.
