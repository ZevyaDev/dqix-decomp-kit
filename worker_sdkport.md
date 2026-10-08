# Porting library functions from reference DS decompilations

You are matching functions in the Dragon Quest IX (NDS, USA) decomp at `$REPO` (`$DQIX_REPO`, default `../dqix-decomp`)
by **finding an existing human implementation** in another DS decompilation and porting it — not by
decompiling from scratch.

`SP` below means the kit root.

Four reference projects are already cloned under `$SP/refs/`: `pokediamond`, `pokeheartgold`,
`pokeplatinum`, `SonicRushAdventure-Decomp`. They share the same NitroSDK, the same Metrowerks C
runtime and the same BIOS syscall stubs that DQIX links, so a large amount of our unmatched code has
already been matched by somebody else.

## The one rule that matters

**Never write an `asm` block because C was hard.** Assembly is a conclusion, not a fallback. All
three of these must hold before you write one:

1. a reference project implements the same routine as assembly (`.s`, or `asm void` in a `.c`);
2. `sdkident.py` scores our function `EXACT` against it — our instruction sequence *is* theirs; and
3. **you tried C and it did not match**, or the code contains a tell that no compiler produces.

Point 3 is not a formality. A reference project writing assembly is evidence about *that project's*
authors, not proof about ours: they may simply have given up on matching it. Their asm tells you
what the routine is; only your own failed C attempt tells you it needs asm.

Tells that a routine really is hand-written assembly — a compiler will not emit these:

- an address-base register reused as a data operand (`str r12, [r12, #0x208]` zeroes IME by storing
  0x04000000, because bit 0 is clear — mwcc would materialise a literal 0 in a fresh register);
- `swi`/`svc`, `mrs`/`msr`, coprocessor `mcr`/`mrc`;
- register-block tricks: `ldm`/`stm` with a register set no ABI would choose, or a live `rrx`/carry
  chain crossing statement boundaries;
- a function that never sets up a frame yet uses r4-r11 freely.

If a reference implements it in **C**, port the C, even if that takes several attempts. If nothing
in the references implements it, report `NEEDS-RESEARCH` and move on. Do not transcribe our own
bytes. A previous sweep that did exactly that produced assembly for a game function and for
`WaitForVCountZero`.

## Per address

```
python $KIT/sdkident.py match main <addr>
```

Prints our size, ISA and instruction count, then every reference implementation ranked by how much
of our instruction sequence it reproduces:

- `EXACT 100%` — their sequence contains ours, instruction for instruction.
- `CLOSE 95-99%` — same routine, a few instructions differ (a different SDK point release, or a
  literal pool laid out differently). Usable as source material; still has to gate.
- `PARTIAL` — related but not the same build. Reference for names and types only.
- `NEEDS-RESEARCH` — nothing found. Report it and stop; someone will decompile it as C.

Read the reference implementation with:

```
python $KIT/sdkident.py show <path-fragment> <ReferenceName>
```

or just open the file under `$SP/refs/`. Read the header too — the reference project names the
parameters and types, and those names are the point of doing this.

## Writing the file

Write to `$SP/staging/main/<Name>.cpp`. It must carry the identity tag, or the integrator cannot
place it and the whole file is silently dropped:

```cpp
#include <globaldefs.h>

// KEEP-NAME: the ROM symbol is a curated name, not a func_ tag.
// USA: func_<addr>
//
// PROVENANCE: <project>/<file> — <ReferenceName>. <one line on what the reference is>
```

`KEEP-NAME` only when `symbols.txt` gives the address a curated (non-`func_`) name; that name is
binding and must be the name you define. Check with:
`grep "addr:0x<addr>" $REPO/config/${DQIX_REGION:-usa}/arm9/symbols.txt`

For ARM code prefix the definition with `ARM`, for Thumb with `THUMB` (macros for
`#pragma thumb off` / `on`). An assembly definition is `ARM asm void Name(args) { ... }` with mwcc
inline-assembly syntax: branch targets inside the function are local labels, and there is no `.s`
directive syntax.

## Gate before you claim anything

```
python $KIT/wgate.py main <addr> $SP/staging/main/<Name>.cpp
```

`MATCH` on the last line is the only success. Anything else (`COMPILE`, `OVERGEN`, `BYTEDIFF@...`,
`UNDEF-SYM`) means it is not matched yet. `wgate` masks relocation bytes exactly as the integrator
does, so a `MATCH` is integrable.

If it does not match, `python $KIT/wdiff.py main <addr> <file>` shows only the diverging instructions.

**Delete any file that does not gate MATCH.** A non-matching file left in `staging/` gets integrated,
fails the overlay checksum, and reds the wave for everyone.

## Report back

One line per address, nothing else:

```
<addr> MATCH <Name> <- <project>/<file>
<addr> NEEDS-RESEARCH <what you looked for and why nothing fit>
<addr> FAILED <best reference> :: <the wdiff verdict>
```
