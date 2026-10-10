# DQIX matching worker

You turn each assigned function into C++ that `wgate.py` passes. You only write source files. The
coordinator (`team/team.py`) reserves, integrates and publishes. Your prompt gives your assignment
and three absolute paths:
- `KIT`, the kit checkout and your working directory
- `SP`, the state directory
- `REPO`, the decomp checkout

## Rules

1. Write only these:
   - `SP/wip/<main|ovNNN>/<addr>.cpp`, the assigned source
   - `SP/handwork/<addr>/`, your scratch and variants
2. Change files with your file-editing tool (Codex: `apply_patch`). Never write from the shell: on
   Windows, PowerShell 5's `>`, `Set-Content` and `Out-File` write ANSI or UTF-16.
3. Read `REPO` freely, but change nothing in it. No state-changing `git`, no `ninja`.
4. Never run anything that stages, integrates, commits, pushes, comments, claims or updates:
   - `finish_wave.sh`, `integrate*`, `ov_recover.py`, `kit_update.py`, `claim.py`, `fullstop.sh`
   - `team/team.py`
5. AGENTS.md rule 8 applies to every source: no asm, no codegen `#pragma`, no compiler override.
6. Work only on your assigned addresses. Never delete a file you did not create. That includes the
   shared `SP/_vt_*` and `SP/_cs_*` files.
7. Do not stop to ask. Make the reasonable choice and say so in `notes`.

## Loop, per function

Follow [docs/WORKFLOW.md](../docs/WORKFLOW.md) with these specifics:

1. If `SP/wip/<label>/<addr>.cpp` exists, an earlier worker left it: gate it and continue from it.
   Otherwise start from `python resumable.py <addr>`, then `python scaffold.py <mod> <addr> <abs.cpp>`.
2. Before writing, read the matched neighbours in `REPO/src` (`python srcdir.py <mod>`). Reuse
   their structs, callee declarations and headers from `REPO/include`.
3. Gate with `python wgate.py <mod> <addr> <abs.cpp>`, and read the difference with
   `python wdiff.py <mod> <addr> <abs.cpp>`.
4. Route on the `RESIDUE <CLASS>`:
   - Find the lever under its heading in `worker_src/core.md` (`rg -n "^##" worker_src/core.md`).
   - Check `worker_src/deadends.md` and `OPEN_RESIDUES.md` for the address.
   - Run `python colorsweep.py <mod> <addr> <abs.cpp> --apply` before calling a REGPERM or SCHED
     stuck.
5. When you use `vtry.py`, prefix variant names with your address (`0218dd18_a`).
6. After about 60 gate iterations with no progress, leave the best attempt in place and move on.

### Sandboxed hosts (Codex on Windows)

Inside Codex's Windows sandbox:
- `frida/colorforce.py` and `frida/schedforce.py` hang forever, holding the compiler open.
- Git Bash cannot start (`NtCreateDirectoryObject 0xC0000022`).

Run the two frida tools with escalated permissions and a 10-minute timeout; outside the sandbox
each takes seconds. Never run `.sh` scripts. Everything else in this file works sandboxed.

## Done means clean

When `wgate` prints MATCH:
1. Run `python pad/decomment.py <F> <F>.clean`, move the clean file over `<F>`, and gate again.
   The `// USA:` tag is the only comment that survives.
2. Make it read like the neighbouring matched files: typed structs, named members, no gratuitous
   casts. `volatile` is allowed only in a hardware-register define.
3. Gate after every cleanup edit. The file on disk must be the gated one. `team.py collect`
   re-gates it and rejects any comment, asm, codegen pragma or non-register `volatile`.

## Final message

Return only this JSON. `codex exec` checks it against `team/report.schema.json`. One entry per
assigned address:

    {"functions": [
      {"module": "017", "addr": "0218dd18", "verdict": "MATCH", "residue": "", "size": 568,
       "file": "<abs path>", "description": "Object/world-node collision push-out",
       "lever": "bound the add to its own local `int reach = a + b;` to fix the operand order",
       "lever_bytes": 4, "notes": "callee X signature guessed from its call site"}
    ]}

- `verdict` is `MATCH`, `RESIDUE` (put `wgate`'s last line in `residue`) or `NOT_STARTED`.
- `description` is a 3-8 word noun phrase; it becomes the function's row in the pull request.
- `lever` names the source transformation that closed the last residue, concretely
  ([IMPROVEMENT_LOOP.md](../docs/IMPROVEMENT_LOOP.md) §2). `lever_bytes` is the byte difference just
  before it. Leave `lever` empty (and `lever_bytes` 0) when the first natural source matched or
  only declaration order moved. `collect` records each lever in `$SP/wlog/levers.tsv`.
- `notes` lists any guessed signature, any struct duplicating a header type, and any symbol problem.
