# Naming pass

Every plain name in the decomp gets a name that says what the thing is, backed by recorded evidence.
Names land on `decomp-matching` through the ledger and `namesland.sh`; nothing edits source by hand.
Rules for a name and its evidence: [BRIEF.md](BRIEF.md).

## Setup (required)

A name is checked against the running game, not only the code: every function whose meaning is not
plain from a few lines needs `dyn:` evidence from our melonDS fork. Without the setup below you
cannot produce an acceptable row.

1. The decomp and kit as in [docs/SETUP.md](../docs/SETUP.md), with the USA base ROM extracted in
   `dqix-decomp/extract/`. Probes run on USA; names land in all three regions.
2. **ZevyaDev/melonDS, branch `debug`**, cloned beside the kit (`../melonDS`, or set `DQIX_MELONDS`).
   No other emulator or melonDS build works: `dyn.py` drives the fork's headless library
   (`melonds_headless`) through its Python package, and the savestates are in the fork's format.

       git clone -b debug https://github.com/ZevyaDev/melonDS ../melonDS
       cd ../melonDS
       cmake -B build/headless -G Ninja -DBUILD_QT_SDL=OFF -DBUILD_HEADLESS=ON -DENABLE_OGLRENDERER=OFF
       cmake --build build/headless
       python -m pip install -e tools/melonds-mcp

   Install the build packages listed in the fork's `BUILD.md` first (Windows: MSYS2 UCRT64, plus
   `mingw-w64-ucrt-x86_64-ninja`; run the cmake lines in the UCRT64 shell). On Windows the library
   loads with `C:\msys64\ucrt64\bin` on the DLL path (`MELONDS_DLL_DIRS` overrides it).
   For looking around by hand, the fork's Qt debugger build is under
   [Releases](https://github.com/ZevyaDev/melonDS/releases) (Debug menu: breakpoints, memory, call
   stack, source view; `DEBUGGER.md` in the fork).
3. The play data: the saves and savestates every scenario starts from (~250 MB unpacked).

       python naming/play.py fetch

   It goes to `$DQIX_PLAY`, else `$SP/play`, and is checked against `naming/play/data.json`.
4. `python naming/play.py check` must print `READY`: Python packages, the fork at the required
   commit, the ROM, every file a scenario starts from, and a savestate that loads and runs. Fix each
   `MISSING` line it prints.

## Name forms (`namerules.py`)

| key in the tree | becomes |
|---|---|
| `func_[ovNNN_]<addr>`, `inline_<addr>` | `<Stem>_[ovNNN_]<addr>` (PascalCase stem) |
| `data_[ovNNN_]<addr>` | `<Stem>_[ovNNN_]<addr>` |
| `Struct_/Enum_/Type_<addr>[_N]` | `<Stem>_<addr>[_N]` |
| `Owner::unknown_<off>_` | `<stem>_<off>_` (camelCase; the offset is the key's) |
| `Function::arg<i>`, `Function::var<i>` | `<stem>` (camelCase; only once the function is named) |

Every region's symbol carries the USA address: one name per function in all three regions. A function
or global with no USA symbol carries its region and its own address (`Stem_jpn_<addr>`,
`Stem_ov004_jpn_<addr>`). A source alias `#define func_<usa> func_<jpn>` is deleted when its function is
named and the JPN symbol takes the USA name; an alias whose JPN name is also a USA symbol is refused
(`ALIAS COLLIDES`). Every name comes from our own analysis; no identifier is taken from an external
source (other decomps, SDK or NitroSystem names, fan tools, docs). No source comments:
evidence lives in the ledger.

## Loop

    python naming/rank.py --top 50                 far-reaching first: distinct callers, modules, refs
    python naming/dossier.py <key> [--callers N]   source, callees, strings, call sites, dynamic, ledger
    python naming/dyn.py run <scenario>...         call counts per function from headless melonDS
    python naming/dyn.py only <scenario> <other>   functions one scenario reaches and the others do not
    python naming/dyn.py probe <scenario> <key>... arguments, callers, returns, memory, screenshots
    python naming/dyn.py show <key> [scenario]     what probes recorded (the dossier shows it too)
    python naming/names.py import rows.jsonl       {key, stem, evidence: [...], by}
    python naming/names.py accept KEY...           after the audit; reject KEY WHY otherwise
    python naming/names.py check                   keys exist, finals are free, locals have a named function
    bash naming/namesland.sh [--dry]               integration tree, prready, ninja check + sha1 x3, publish

The ledger is `$SP/names/ledger.jsonl` (`DQIX_NAMES_LEDGER` overrides it); the last row per key wins;
status runs proposed, accepted, landed (with the commit), or rejected (with why). A new row for a landed
key revises its name: it records the landed name as `was` and goes through the same audit and landing. `--dry` builds every
region and publishes nothing.

Evidence items start with their kind: `src:` (what the code does), `call:` (how callers use it),
`str:` (a string it loads), `upstream:` (a human name it touches), `dyn:` (a scenario observation),
`save:` (save-format offset), `data:` (a game table), `web:` (a URL).

## Scenarios

`naming/scenarios/<name>.py`: `START = {"save": ..., "state": ...}` relative to the play data, and
`play(F)` driving `naming/play/dqix_auto.Field` (`hold`, `run`, `move_to`, `talk`, `go_npc`; flows in
`dqix_flows.py`). The save is copied first. Results go to `$SP/names/dyn/<scenario>.json`, which
`dossier.py` reads.

`naming/play/dqix_usa.json` is what driving the game has taught us: RAM addresses, coordinates and
walk speed, input and boot timings, routes, NPC spots, menus, battle and multiplayer facts, and what
each save and savestate holds. Read it before writing a scenario, and add every new fact you learn
while playing to it in the same change as the scenario.

| play data | holds |
|---|---|
| `saves/story/NNN - <story point>.sav` | 85 story saves, 001-084, hero Laura; `dqix_usa.json` `saves.story_saves` gives each start map |
| `saves/dq9ds_*.sav` | post-game saves (Kheg Lv88 party, Ayla Lv26 party, ...) |
| `states/host.sav`, `guest.sav` + `*.mst` | Quester's Rest, a local-wireless session (`mp_joined.0/1`, host and guest), a field battle, an event, a ladder, a grotto, ... (`dqix_usa.json` `multiplayer`) |

A scenario starts from the play data and reaches its state by playing, so anyone can rerun it and get
the same calls. A new savestate goes into the next data release: `play.py pack DIR TAG`
(maintainers) uploads it and rewrites `data.json`.

## Contributing names

Names reach `ZevyaDev/dqix-decomp` as pull requests, like matches
([docs/CONTRIBUTING.md](../docs/CONTRIBUTING.md): your fork as `origin`, ZevyaDev as `zevya`).

1. Pick far-reaching keys first (`rank.py`), whole subsystems at a time, so the words agree.
   `rank.py` already leaves out keys someone else holds.
2. Reserve them before any work: `python naming/reservations.py take KEY...`. It refuses a key held
   in another person's open kit issue or open decomp pull request (a listed function holds its
   parameters and locals too), and keeps your ONE open kit issue `Naming: N keys` (AGENTS.md rule 20).
   `python naming/reservations.py` lists every held key and its owner; `drop KEY...` releases yours.
   `names.py import` and `namesland.sh` refuse keys someone else holds.
3. Write rows by [BRIEF.md](BRIEF.md), with `dyn:` evidence from `dyn.py probe`, and
   `names.py import` them.
4. Audit: someone who did not write the rows (a second agent with only the rows, the dossiers and the
   BRIEF's Audit section) checks each one; `names.py accept` what passes, `names.py reject` the rest.
5. Land on your fork: `git pull --rebase zevya decomp-matching` in the decomp, push it to your fork,
   then `bash naming/namesland.sh --dry` and, when it prints GREEN, `bash naming/namesland.sh`. It
   renames in every region, runs `prready.py`, builds usa, eur and jpn, and pushes the commit to your
   fork's `decomp-matching`.
6. New scenarios first: a kit pull request with every scenario your rows cite that is not on kit
   `main`, plus the facts you added to `dqix_usa.json`. A new savestate goes in a zip attached to
   that pull request.
7. Open the decomp pull request with `python naming/names.py evidence <commit>` as its body (the
   commit `namesland.sh` printed); past GitHub's 65,536-character limit, continue in comments. Keep
   one pull request under about 100 names. Close the reservation issue naming the pull request.

Review (maintainers): land the kit pull request, `gh pr view N --json body -q .body > prN.md`,
`names.py import prN.md --by <login>`, rerun every probe the rows cite and audit them afresh. A row
whose probe does not reproduce or whose evidence does not hold is not landed. When every row holds,
`bash landpr.sh N`, then `names.py accept` and `names.py landed <merge commit>` the keys.

## Known traps

- `ov016` executes code at `0x021909cc`-`0x0219cfa4`, which its `delinks.txt` links as `.rodata`; those
  calls show as `unmapped` in a scenario file.
- Some structs view an object from an inner base and keep the full object's offsets in member names
  (`Struct_0206a3c0`); a key keeps whatever offset its plain name has.
- A global is often declared with a different type in every unit (`data_02108760`: `char[]`, `int`,
  `Struct_02108760`); the rename covers all of them.
- `prready.py` refuses only names on lines a change adds, so a rename touching hundreds of files is not
  blamed for older names in them.
