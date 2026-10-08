# DQIX naming pass — handoff

## The goal, stated properly

Take functions that are already byte-matched and make them **fully understood in the code itself**.
That means every identifier a reader sees carries meaning:

- the function name
- every parameter and local
- every struct tag and every field, including the `pad` filler between known fields
- array extents that reflect the real element count
- the comment, documenting what the code cannot say

Work so far named functions and wrote comments, and stopped there. That is roughly half the job. A
file like `src/Combat/Main/GetEquippedItemIds.cpp` currently reads:

```cpp
struct Field150Table02052e2c {
    char pad[0x488];
    short entries[1];
};

// Returns a character's equipped item ids: ten halfwords at +0x488 of the record hung off the
// combatant at +0x150.
extern "C" ARM short* GetEquippedItemIds(struct Field150Holder02052e2c* obj) {
```

The comment knows it is ten equipment slots on a character record. The code still says `entries[1]`,
`obj` and `Field150Table02052e2c`. Both halves have to carry the understanding.

## Where things are

    $DQIX_LABEL_REPO    label clone of ZevyaDev/dqix-decomp, branch `naming-pass` checked out;
                        default `dqix-label` beside the kit root
    $DQIX_REPO          the matching clone (`kitpaths.REPO`), default `dqix-decomp` beside the kit
                        root; the matching track works in it, so read it and never write to it
    naming/             the pipeline described below

Setting up the label clone, beside the kit root:

    git clone https://github.com/ZevyaDev/dqix-decomp.git dqix-label
    git -C dqix-label checkout naming-pass
    git -C dqix-label fetch https://github.com/DQIX/dqix-decomp.git main:upstream-main

It also needs `labeling-pass` as a local branch, and must build per the repo's README.

Branches in the label clone:

- **`naming-pass`** — the deliverable. Sits on `upstream-main`, six commits, pushed. Contains
  **only** files under `src/`, `include/` and `config/`. No markdown, no TSV, no tooling. Keep it
  that way; a doc file was pushed once and had to be stripped with `filter-branch`.
- **`labeling-pass`** — the full worker tree, 10,877 matched functions with source. This is the
  quarry: every function ported to `naming-pass` is read out of here.
- **`upstream-main`** — `main` from DQIX/dqix-decomp, 88 source files.

## State at handoff

439 source files on `naming-pass`, 356 functions ported over four commits. `ninja check` and
`ninja sha1` both pass — the built ROM is byte-identical to the retail cart.

**10,240 matched functions remain portable.**

## Build

In the label clone:

    python tools/configure.py "${DQIX_REGION:-usa}"     # after adding or removing any source file
    ninja check                       # the matching gate
    ninja sha1                        # full ROM SHA-1, needs arm7_bios.bin at the repo root

Never run bare `ninja`. `ninja check` and `ninja sha1` must both pass before any commit.

## The pipeline

Everything lives in `naming/`. The Python scripts find both clones through `namingpaths.py`, which
imports the kit's `kitpaths.py`; set `DQIX_LABEL_REPO` and `DQIX_REPO` to override the defaults.
Run them from `naming/`: round directories and plan files given as arguments are relative to the
working directory, and the workflows read rounds from `naming/`.

The workflow scripts take `naming`, `label` and `repo` in their args — absolute paths to `naming/`,
the label clone and the matching clone. Each falls back to `DQIX_NAMING_DIR`, `DQIX_LABEL_REPO` or
`DQIX_REPO` where the runtime exposes the environment, then to `naming`, `../dqix-label` and
`../dqix-decomp`, which resolve only when the session runs from the kit root. The briefs write
`$DQIX_LABEL_REPO` and `$DQIX_REPO`; every prompt that hands out a brief says what they stand for.

Two briefs are handed to agents. Both say what counts as evidence, what a proper name is, what a
proper comment is, with worked good and bad examples.

- `BRIEF.md` — naming a function that has none: its name, its comment, **and every identifier
  inside it**. The "Naming the insides" section carries the conventions.
- `BRIEF_INSIDES.md` — naming the insides of a function that already has a good name and comment.

Both use the same conventions: camelCase parameters and locals that say what the value is,
PascalCase struct tags with no address in them, fields named for what the code does with them,
filler named `unknown<offset>`, and array extents only where a count is cited.

Workflow scripts, each a naming pass followed by an adversarial audit, pipelined so an audit starts
as soon as its own naming batch lands:

    wf_inside.js      track 1: name the insides of already-ported functions
    wf_naming4.js     track 2: name a new function and its insides, then port it

Agents in the current scripts **write their own output file** under the round directory and return
only a summary. Nothing else may be written; the repo is never touched by an agent. Reading a whole
round back through the workflow's return value cost far more than reading it off disk.

Porting and landing:

    port2.py <plan.json> [--apply]    port sources from labeling-pass onto the checked-out branch
    propagate.py                      rewrite every reference after renames, across all sources
    autodrop.py <plan> <out>          port, build, bisect out whatever breaks the link, repeat
    rename_apply.py <plan> [--apply]  apply an insides plan: renames, then edits, then the comment
    land_insides.py <plan> [out]      apply an insides plan, build, bisect out whatever reds
    fillcomments.py <in> <out>        carry a source's existing comment block into a plan

Queues and merges:

    queue_insides.py <dir> [per]      batches of ported files, ranked by how much junk is left
    queue2.py <dir> [per] [batches]   batches of unnamed functions with their labeling-pass source
    queue.py                          REVIEW_QUEUE.tsv: unnamed functions with asset strings or 50+ callers
    merge_insides.py <round> [final]  plan minus whatever the audit rejected
    merge_names.py <chunks> <round>   plan.json for porting, insides.json for rename_apply

Strings:

    strxref.py <out.json>             the strings each function's literal pool points at
    namestrings.py <repo> [--apply]   rename `data_*` symbols holding a C string to `str<Text>`, and
                                      their references; writes renames.json

Generated inputs, kept in `naming/` and never committed:

    strxref.json    `python strxref.py strxref.json`, from `$DQIX_REPO/config` and
                    `$DQIX_REPO/extract/<region>` (`DQIX_REGION`, default `usa`); read by queue.py, queue2.py and queue_insides.py
    cg.json         `python callgraph.py`, the call graph `{callers, callees}` from the label
                    clone's `relocs.txt`, keys `module|address|name`; read by queue.py and queue2.py

A naming plan entry is `{address, current_name, name, comment, module, labeling_source}`.
An insides plan entry is `{file, function, renames:[{old,new}], edits:[{old,new}], comment}`.

A rename may carry a `scope`: `func` for the function's own definition and parameter list,
`struct:Tag` for one struct's body, `line:<unique substring>` for a single declaration line.
Without one the substitution covers the whole file, which is wrong whenever a spelling means more
than one thing there — `obj` as both the function's parameter and three prototypes' — and these
bodies reuse spellings constantly. The audit repairs an unscoped collision with `fix_renames`
rather than rejecting it.

Do not edit a brief or a workflow script while a round is running.

`rename_apply.py` is what makes the insides safe. It substitutes identifiers over one file with
string and comment text masked, so it cannot reorder a declaration or change a type. It refuses to
rename a global symbol, refuses a target already spelled in the code, and reports any `old` it never
found. Anything that really is a type change — an array extent, a widened field — has to be written
as an `edits` entry, a literal line replacement applied after the renames and matched exactly once.

## How a round runs

All commands run from `naming/`.

Track 1, the insides of what is already ported:

1. `queue_insides.py inside_all 9` — 39 batches, most junk first.
2. `Workflow wf_inside.js` with `{dir, out, batches}` plus the path args. Agents propose only;
   they write `plan<NN>.json` and the audit writes `verdict<NN>.json` into the round directory.
3. `merge_insides.py <round> <final.json>` — drops every rename and edit the audit rejected, and
   takes `better_comment` when the audit supplied one. An unaudited file is dropped, not landed.
4. `land_insides.py <final.json>` — applies, builds, bisects out anything that reds the gate.
5. `ninja check` + `ninja sha1`, commit, push.

Track 2, porting more functions:

1. `queue2.py chunks4 11 12` — candidates that have a source on labeling-pass and no name yet,
   asset-string evidence first, then fan-in.
2. `Workflow wf_naming4.js` with `{dir, out, batches}` plus the path args.
3. `merge_names.py chunks4 final4` — writes `plan.json` for porting and `insides.json` for the
   identifiers inside the ported files.
4. `autodrop.py final4/plan.json final4/keep.json` to port and build.
5. `rename_apply.py final4/insides.json --apply`, then `ninja check` again.
6. `ninja sha1`, commit, push.

## What must be added for full naming

Renaming parameters, locals, struct tags and field names is **source-only** — those identifiers
exist nowhere but the `.cpp`, so no config changes and no symbol matching. They never reach codegen.

Two real constraints:

- **Declaration order and types must not change.** Order drives register allocation. A pure rename
  is safe; reordering is not.
- **Changing an array extent or a field type is a type change**, not a rename. `entries[1]` →
  `entries[10]` may alter codegen, so gate those per batch rather than in bulk.

`ninja check` proves either way, so the cost of being wrong is a red gate, not a bad commit.

The naming agents already derive far more than they are asked to report. The audit for
`GetCombatantWithFlag0x100` established that every decompiled caller dereferences `combatant+0x150`
and reads a gender bit at `record+0x49c`, held items at `record+0x454`, thirteen per-vocation levels
at `record+0x16c`. That is field-level knowledge that never reached a struct definition. Extend the
output schema to carry it: parameter names, local names, struct tag names, per-field names with
their offsets, and array extents where the count is established.

## Hard-won gotchas

- **The C runtime region of `main` cannot be delinked.** 36 functions — `memset`, `memcpy`,
  `sprintf`, `strlen`, `strcmp`, `rand`, `abs`, `_s32_div_f`, `_fls`, `_fgeq`, plus BIOS veneers and
  matrix helpers — all fail the link with `sum of all symbol sizes exceed section size` in a
  delinked leftover object. They take names in `symbols.txt` but not their source. `autodrop.py`
  finds them automatically.
- **Renames must propagate.** Renaming a symbol without rewriting every reference breaks the link.
  `propagate.py` after every port, always.
- **Mangled versus plain linkage.** A C++ source spells `GetBattleStruct` and lets the compiler
  mangle it; a plain C symbol needs `extern "C"`. `port2.py` distinguishes an exact symbol match
  from a demangled-base match and only rewrites the latter when the target is a plain name.
- **Never write code through a shell heredoc.** A propagation script written that way had its `\b`
  word boundaries eaten, matched nothing, and reported success.
- **Agents sometimes narrate caller names from memory.** Audits caught evidence citing
  `ApplyThreatOverrideAndFlag_02163070`, which exists in neither branch. Require citations to be
  read off the tree.
- **The audit is not optional.** It rejects 27-51% of proposed names, including the highest-value
  ones. A round whose audits died to a usage limit must not be landed unaudited.
- **Workflow resume is cheap.** `resumeFromRunId` replays completed agents from cache; only the
  failed ones re-run. A limit hit costs the unfinished half, not the whole round.
- **An opaque archive name stays opaque.** `percol`, `attnpc`, `loola`, `ouen` keep their spelling
  in function names; the comment says what is suspected and why it is not established.

## Conventions

Comments follow the human-written upstream style — plain `//`, sentence case, ordinary prose as long
as it needs to be, uncertainty stated plainly. Read `src/Filesystem/CardReadManager.cpp` and
`src/Graphics/AtmosphericEffect.cpp` before writing any. Here comments are the deliverable.
