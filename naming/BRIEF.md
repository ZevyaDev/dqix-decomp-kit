# Naming brief

You name symbols in the DQIX decomp. You never edit source; you write ledger rows to the output file
you are given, one JSON object per line:

    {"key": "func_0205eaa0", "stem": "PlaySoundEffect", "evidence": ["src: ...", "call: ..."], "by": "<your id>"}

Read `$KIT/naming/HANDOFF.md` for the name forms. Get the facts with
`python $KIT/naming/dossier.py <key> --callers 12`; read more callers' source when the call sites
disagree. Run a scenario (`python $KIT/naming/dyn.py run <name>`) only when the brief allows it.

## What a name must be

- True for every caller, not one. A function called from 20 overlays with 20 argument types does one
  thing; name that thing.
- Specific as the evidence allows, no further. `GetZone3D` when it returns the `Zone3D` instance;
  `GetGameStateSub2a04` is not a name. If the evidence only shows shape, skip the key.
- In the upstream style: functions `VerbNoun` (`GetPartyMemberByIndex`, `PlaySoundEffect`), types
  nouns (`SoundManager`), globals `g` plus the noun (`gZone3D`), members camelCase nouns with a `p`
  prefix for pointers (`pAllocator_4c_` comes out of stem `pAllocator`), booleans `is`/`has`. A library
  function identified by `libid.py` keeps its library name (`NNS_SndArcGetSeqInfo`). No `Maybe`, `Unknown`, `Probably`, `Helper`, `Do`,
  `Handle` without an object, numbered stems.
- The same thing gets the same word everywhere. Check `names.py show` and the dossier's callee names
  before choosing a word another row already uses differently.

## Evidence

Each row needs at least one item a reviewer can check without trusting you:

- `src:` what the code does, citing the line (`src: returns &data_020fb3f0, declared Zone3D`)
- `call:` how named or obvious callers use the result (`call: Object3D::AdvanceAnimations_v0 passes
  loopEntry->maybeSoundEffect`)
- `upstream:` a human name the code touches (upstream types, methods, fields)
- `str:` a string the function loads
- `dyn:` a scenario observation (`dyn: menu 214496 calls, idle 117900: per-frame, not menu-specific`)
- `data:`, `save:`, `web:` a game table, save offset or a URL with the fact

A guess is not evidence. A name derived from another unlanded proposal says so (`call: depends on
func_X -> Y`).

## Insides

A function is done only when every parameter and local in every region's body is named, in the same
batch as the function (`func_X::arg0` -> `soundId`); the dossier's `PLAIN INSIDES` line lists what is
left. A loop index is `i` (`j` inside it); otherwise say what the value is. Name the members the
function touches whose meaning its code shows (`Struct_02108760::unknown_b4_` -> `currentBank`, final
`currentBank_b4_`), including the type itself; a member whose meaning shows only in other functions is
named in their batch, and the dossier keeps listing it until then.

## Audit

The auditor gets the rows and the dossiers, not the namer's reasoning. For each row: is every evidence
item true when checked against the source and the dossier, does the stem follow from it, does it hold
for every caller, is it consistent with landed names? Reply per key `accept` or `reject: <why>`. Reject
when in doubt.
