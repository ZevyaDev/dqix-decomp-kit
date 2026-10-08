# Naming brief — Dragon Quest IX (NDS) decompilation

You are naming functions in a byte-exact decompilation of Dragon Quest IX: Sentinels of the Starry
Skies. Every function already matches the ROM. What is missing is understanding: the names are
machine-generated and say nothing about the game.

**You do not edit anything.** Read, decide, and return findings. No Write, no Edit, no git commands
that change state.

## Your input

A JSON file of 11 entries. Each has `address`, `current_name`, `module`, `size`, `source` (a path,
or `-`), `asset_strings`, and `labeling_source` — a path that exists on the `labeling-pass` branch.

## Where the evidence is

Repo: `$DQIX_LABEL_REPO` (branch `naming-pass` is checked out; do not switch it). Your prompt gives
the paths `$DQIX_LABEL_REPO` and `$DQIX_REPO` stand for.

- **The decompiled body.** `git -C $DQIX_LABEL_REPO show labeling-pass:<labeling_source>`
  Read this first, always. It is real C, matching the ROM.
- **Asset strings.** Already in your input; they are the file paths the function's literal pool
  points at. Exact, not inferred.
- **The call graph.** `config/<region>/arm9/relocs.txt` records every call edge as
  `from:0x… kind:… to:0x… module:…`. `config/<region>/arm9/symbols.txt` (and
  `config/<region>/arm9/overlays/ovNNN/symbols.txt`) map addresses to names. `<region>` is
  `$DQIX_REGION`, default `usa`. Who calls a function, and
  what it calls, is often what settles its purpose.
- **The game's own files.** `$DQIX_REPO/extract/<region>/files/` is the extracted filesystem. If a
  function reads `data/prm/level%d.bin`, list that directory — thirteen files numbered 0..12 told
  us it is per-vocation. Count things. Sizes and counts are evidence.
- **Sibling functions.** Nearby addresses often form a family. If three functions differ only in
  which archive they name, they are wrappers over one worker, and naming one names all of them.
- **Overlay roles.** ov000 battle, ov001 event, ov002 topmenu, ov003 shisetsu, ov004 menucallback,
  ov005 equipmenu, ov006 renkin (alchemy), ov008 jourecode, ov011 menusys, ov012 prof, ov013
  skillup, ov014 subjugation, ov015 charaview, ov016 movieview, ov017 gamemain, ov020 title, ov021
  charamake, ov023-030 the sub_* family, ov031 wifi, ov033/034 bgload.

## What a proper name is

The name must say **what game thing the function acts on**, taken from evidence you can cite.

Good, and all real from this project:

    LoadMonsterDataTable        pulls mon_data_<LG>.nat out of data/prm/mon_data.gp2
    RunSpellTableScript         hands data/prm/spelltable.bin to Script::Execute
    LoadLevelTableForVocation   formats level%d.bin; the ROM holds level0..level12
    CopyItemNameString          wraps the localized-string worker on itemname.gp2
    GetZoneState                first halfword is the zone id every event record compares against

Bad, and all names this project has to replace:

    DispatchIfCountPositive     describes an if-statement
    SetupContextForMode         describes nothing
    InitObjWithAllocator        true of hundreds of functions
    HandleQueuedEntry           shape, not subject
    ApplyCounterIfValid         shape, not subject

A shape name is not an improvement over `func_020dcf7c`. If the evidence does not establish the
game subject, say so — `confidence: "insufficient"` is a correct and useful answer, and far better
than a plausible invention. Do not pad a shape name with a domain word you cannot cite.

When an archive's name is opaque (`percol`, `attnpc`, `loola`), keep that spelling in the function
name rather than guessing its expansion, and say in the comment what you suspect and why it is not
established.

## What a proper comment is

Match the existing human style in this repo. Read
`git -C $DQIX_LABEL_REPO show labeling-pass:src/Filesystem/CardReadManager.cpp` for a sample.
Plain `//` lines, sentence case, ordinary prose, as long as it needs to be, sitting above the thing
it describes. No `///`, no doc blocks, no banners.

Write 2 to 6 lines that tell a reader what the code cannot:

- what the function is for, and the evidence that establishes it
- the meaning of a magic constant, an archive name, or a mode value where you worked it out
- mechanism worth knowing — a lock discipline, a shared buffer, a format quirk
- uncertainty, stated plainly. "Seems to", "presumably", "not established" are all in keeping with
  the existing comments. Never write a confident sentence about something you inferred.

Do not restate the code. `// loops over the entries` is worthless; it is visible.

## Naming the insides

The function's own name is half the job. The body you read is machine-generated inside: parameters
called `obj` and `arg1`, locals called `a` and `v3`, struct tags called `Struct0205e3ec`, fields
called `field16`, filler called `pad2`, arrays declared `[1]` that hold ten elements. You worked out
what the object is in order to name the function; write that down as identifiers too, or it is lost.

You are naming identifiers **in the decompiled body you read**, so quote them exactly as they are
spelled there.

- **Parameters and locals**: camelCase, saying what the value is — `combatant`, `slotIndex`,
  `vocationLevels`. Not `p`, not `value`, not `temp`. A loop counter is named for what it indexes;
  plain `i` is fine only where the body ignores the counter.
- **Struct tags**: PascalCase, no address in the name — `Combatant`, `CharacterRecord`,
  `EventQueueNode`. Named for the game object, never for the function it was found in. Tags are
  file-local, so use the same spelling another file already uses for the same object.
- **Fields**: camelCase, named by what the code does with them — `heldItemIds`, `appearanceDirty`.
- **Filler**: a `pad`/`padN` member spanning unexamined bytes becomes `unknown<offset>` — the hex
  offset it starts at, no `0x`: `unknown0`, `unknown50`, `unknown772`. Filler is not exempt.

`unknown<offset>` is the correct name for a field nobody has read. Do not invent a purpose for one.

Two hard limits. **Declaration order is load-bearing** — it drives register allocation, so never
reorder, merge or split a declaration. **A type change is not a rename**: `short entries[1]` to
`short equippedItemIds[10]` changes the struct's size, and so does widening a field. Those go in
`edits`, with the evidence for the count, and are gated separately.

**One name, one meaning per file.** A rename without a scope substitutes over the whole file, and
these bodies reuse a spelling constantly: `obj` is the function's own parameter *and* the parameter
of three unrelated prototypes above it, `pad` is a member of four different structs. Renaming such a
spelling unscoped stamps one meaning on all of them, which is worse than leaving it alone. Give
those renames a `scope`:

    "scope": "func"                       the function's own definition, its parameter list included
    "scope": "struct:EventQueueNode"      that struct's body, for a member name shared with another
    "scope": "line:func_ov023_021dde00"   one declaration line, matched by a unique substring

A prototype's parameter names are documentation and nothing else, so scoping each one to its own
line is the normal way to name them.

## Return

For each of your 11 entries:

    address           as given, e.g. "0x020dcf7c"
    current_name      as given
    proposed_name     PascalCase, or null when confidence is "insufficient"
    confidence        "certain" | "probable" | "insufficient"
    evidence          one or two sentences, citing the specific string, callee, caller count or
                      file listing that supports the name
    comment           the comment block as it should appear above the function, "//" lines included
    renames           [{old, new, kind, evidence}] over the identifiers inside the body, where
                      kind is "param", "local", "struct", "field" or "enum", plus "scope" on any
                      spelling the file reuses
    edits             [{old, new, evidence}] literal declaration-line replacements, applied after
                      the renames, so spell `old` in its post-rename form

`certain` means a cited string or callee proves it. `probable` means the evidence points one way
with a gap you name in the comment. `insufficient` means say nothing and leave the name alone — but
an insufficient function name does not excuse the insides. Name the parameters, locals and fields
you can regardless; that work stands on its own.
