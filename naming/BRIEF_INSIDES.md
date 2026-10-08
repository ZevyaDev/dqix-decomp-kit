# Naming brief — the insides of a decompiled function

Dragon Quest IX (NDS), byte-exact decompilation. The functions you are given already have a good
name and a good comment. What they do not have is meaning **inside** the body: parameters called
`obj` and `arg1`, locals called `a` and `v3`, struct tags called `Struct0205e3ec`, fields called
`field16`, filler called `pad2`, and arrays declared `[1]` that really hold ten elements.

Your job is to name every one of those. A reader of the finished file must never have to consult
the comment to find out what an identifier is.

**You do not edit anything.** Read, decide, return a rename plan. A script applies it.

## Your input

A JSON file. Each entry has:

    file                path of the source, relative to the repo root — read it on disk
    function            the function's name; it is already correct, do not rename it
    module              main, or an overlay name
    address             the function's address in the ROM
    junk_identifiers    every identifier in the file that still looks machine-generated
    asset_strings       file paths the literal pool points at, when there are any

Repo: `$DQIX_LABEL_REPO`, branch `naming-pass` checked out. Do not switch branches. Your prompt
gives the paths `$DQIX_LABEL_REPO` and `$DQIX_REPO` stand for.

`junk_identifiers` is the checklist. Anything on it that you leave unnamed is work not done. It
already excludes global symbols, which are named elsewhere and are off limits here.

## Where the evidence is

- **The file itself.** Read it first, in full, including the comment. The comment is the previous
  round's conclusion and often already states what a field means — a comment saying "ten halfwords
  at +0x488" is exactly the evidence for `short equippedItemIds[10]`.
- **Other decompiled functions that touch the same object.** This is the strongest evidence for
  field names. `config/<region>/arm9/relocs.txt` records call edges as `from:0x… kind:… to:0x… module:…`;
  `config/<region>/arm9/symbols.txt` and `config/<region>/arm9/overlays/ovNNN/symbols.txt` map addresses to
  names. Read a caller's or callee's body with
  `git -C $DQIX_LABEL_REPO show labeling-pass:<path>` — the `labeling-pass` branch holds matched C
  for ten thousand functions. Find the path with
  `git -C $DQIX_LABEL_REPO ls-tree -r --name-only labeling-pass | grep <name>`.
  A field is named by what the code that writes it does, not by its offset.
- **The game's own files.** `$DQIX_REPO/extract/<region>/files/` is the extracted filesystem
  (`<region>` is `$DQIX_REGION`, default `usa`). Counts
  settle array extents: thirteen `level%d.bin` files means thirteen vocations.
- **Sibling functions at nearby addresses** usually operate on the same struct. Two accessors that
  read +0x454 and +0x49c of the same record name two fields at once.

## What to return, and the rules that bound it

Renames are pure text substitution over one file. They can never change codegen, so a rename that
is merely a judgement call is cheap. Two things are **not** renames and are dangerous:

- **Declaration order is load-bearing.** It drives register allocation. Never reorder anything,
  never merge or split a declaration, never move a field.
- **A type change is a type change.** `short entries[1]` to `short equippedItemIds[10]` changes the
  struct's size. So does widening a field or replacing `char pad[4]` with two shorts. These go in
  `edits`, are checked separately, and need real evidence for the count.

### renames

One entry per identifier: `{old, new, kind, evidence}`, plus `scope` where the spelling is reused.
`kind` is `param`, `local`, `struct`, `field` or `enum`.

- **Parameters and locals**: camelCase, say what the value is. `combatant`, `slotIndex`,
  `vocationLevels`, `queueHead`. Not `p`, not `value`, not `temp`. A loop counter that indexes
  something is named for what it indexes: `slot`, `vocation`, `channel` — plain `i` is acceptable
  only in a loop whose body ignores the counter.
- **Struct tags**: PascalCase, no address in the name. `Combatant`, `CharacterRecord`,
  `EventQueueNode`. A tag naming the object it describes, never the function it was found in.
  Tags are file-local, so two files may legitimately use the same tag for the same game object —
  that is a good thing, use the same spelling as an already-named file when it is the same object.
- **Fields**: camelCase, named by what the code does with them, e.g. `heldItemIds`,
  `vocationLevels`, `appearanceDirty`.
- **Filler**: a `pad` or `padN` member that spans unexamined bytes is named `unknown<offset>`,
  the hex offset it starts at with no `0x`: `unknown0`, `unknown50`, `unknown772`. Filler is not
  exempt from naming; `pad2` tells a reader nothing about where it sits.

A rename must be a genuine improvement. If the evidence does not establish what a field holds,
`unknown<offset>` is the correct answer for it and no evidence sentence is needed. Do not invent a
purpose. Do not rename an identifier that is already good.

**One name, one meaning per file.** A rename without a scope substitutes over the whole file, and
these bodies reuse a spelling constantly: `obj` is the function's own parameter *and* the parameter
of three unrelated prototypes above it, `pad` is a member of four different structs. Renaming such a
spelling unscoped stamps one meaning on all of them, which is worse than leaving it alone.

Give those renames a `scope`:

    "scope": "func"                       the function's own definition, its parameter list included
    "scope": "struct:EventQueueNode"      that struct's body, for a member name shared with another
    "scope": "line:func_ov023_021dde00"   one declaration line, matched by a unique substring

A prototype's parameter names are documentation and nothing else, so scoping each one to its own
line is the normal way to name them. Check what else in the file carries a spelling before you
propose it unscoped, and scope it whenever the answer is anything.

### edits

Literal line replacements, applied **after** the renames, so write `old` in its post-rename form.
Each `old` must occur exactly once in the file or the edit is dropped.

Use them for exactly two things: an array extent you can prove, and disambiguating two identical
member names in different structs. Include the evidence for a count.

    {"old": "short equippedItemIds[1];", "new": "short equippedItemIds[10];",
     "evidence": "func_020dd718 loops slot < 10 over this array"}

### comment

Return the comment block as it should stand after the rename, `//` lines included, in the existing
human style — plain sentence case prose, uncertainty stated plainly, no `///`, no banners.

Usually the existing comment is already right and only needs its prose brought in line with the new
identifiers. Keep its evidence and its hedging. Do not shorten it, do not restate what the code now
says for itself, and do not delete a caveat because the code got clearer. If you learned something
while naming the fields — an offset's meaning, a count, a mode value — add it.

If the comment needs no change at all, return it unchanged.

### confidence

`certain` when the body and a cited caller settle every name you propose; `probable` when some
field names rest on one reading; `partial` when you named what you could and left the rest as
`unknown<offset>`. `partial` is an honest and common answer.

## Return shape

    plans: [ { file, function, renames[], edits[], comment, confidence, notes } ]

`notes` is one sentence on anything the next reader should know — a field you could not settle, a
sibling function that would name more of this struct, a struct that plainly belongs in a shared
header.
