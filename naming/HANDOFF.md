# Naming pass

Every plain name in the decomp gets a name that says what the thing is, backed by recorded evidence.
Names land on `decomp-matching` through the ledger and `namesland.sh`; nothing edits source by hand.

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
(`ALIAS COLLIDES`). Library functions identified by signature are suffixed too. No source comments:
evidence lives in the ledger.

## Loop

    python naming/rank.py --top 50                 far-reaching first: distinct callers, modules, refs
    python naming/dossier.py <key> [--callers N]   source, callees, strings, call sites, dynamic, ledger
    python naming/dyn.py run <scenario>...         call counts per function from headless melonDS
    python naming/dyn.py only <scenario> <other>   functions one scenario reaches and the others do not
    python naming/names.py import rows.jsonl       {key, stem, evidence: [...], by}
    python naming/names.py accept KEY...           after the audit; reject KEY WHY otherwise
    python naming/names.py check                   keys exist, finals are free, locals have a named function
    bash naming/namesland.sh [--dry]               integration tree, prready, ninja check + sha1 x3, publish

The ledger is `$SP/names/ledger.jsonl` (`DQIX_NAMES_LEDGER` overrides it); the last row per key wins;
status runs proposed, accepted, landed (with the commit), or rejected (with why). `--dry` builds every
region and publishes nothing.

Evidence items start with their kind: `src:` (what the code does), `call:` (how callers use it),
`str:` (a string it loads), `upstream:` (a human name it touches), `dyn:` (a scenario observation),
`save:` (save-format offset), `data:` (a game table), `web:` (a URL).

## Scenarios

`naming/scenarios/<name>.py`: `START = {"save": ..., "state": ...}` relative to `$DQIX_PLAY`
(`../dqix-play`), and `play(F)` driving `dqix_auto.Field` (`hold`, `run`, `move_to`, `talk`,
`go_npc`; flows in `dqix_flows.py`; facts in `dqix_usa.json`). The save is copied first. More saves:
`D:/Downloads/dqvc/work/saves/manifest.md`; text codec `D:/Downloads/dqvc/work/tools/mestext.py`.
Results go to `$SP/names/dyn/<scenario>.json`, which `dossier.py` reads.

## Known traps

- `ov016` executes code at `0x021909cc`-`0x0219cfa4`, which its `delinks.txt` links as `.rodata`; those
  calls show as `unmapped` in a scenario file.
- Some structs view an object from an inner base and keep the full object's offsets in member names
  (`Struct_0206a3c0`); a key keeps whatever offset its plain name has.
- A global is often declared with a different type in every unit (`data_02108760`: `char[]`, `int`,
  `Struct_02108760`); the rename covers all of them.
- `prready.py` refuses only names on lines a change adds, so a rename touching hundreds of files is not
  blamed for older names in them.
