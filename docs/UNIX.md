# Running the kit on Linux, the BSDs and macOS

The kit is developed on Windows but runs anywhere Unix does. Ubuntu and Debian derivatives
(including **MX Linux**, which is Debian-based and behaves identically here) are the tested
targets; the same three files carry the whole port, so nothing branches per distribution.

Read this instead of guessing. The one thing that cannot be worked around is the compiler: the
decomp's `mwccarm.exe` is a 2007 Windows binary, and running it is the entire difference between
"works on Linux" and "every gate fails".

## What changed, and what did not

| | Windows | Unix |
|---|---|---|
| the compiler | `mwccarm.exe`, run directly | the same `.exe`, run through **wibo** |
| `wgate.py`, `wdiff.py`, `colorsweep.py`, `classify.py`, `integrate.py`, `regress.py` and every other tool | unchanged | unchanged |
| `psq.sh` `fullstop.sh` `killfleet.sh` `health.sh` | PowerShell, unchanged | Unix twins: `psql.sh` `fullstop_linux.sh` `killfleet_linux.sh` `health_linux.sh` |

Almost nothing in the kit was ported, because almost nothing needed to be. The tools that matter
call `buildcfg.CC`, and the port is entirely in what `buildcfg.CC` resolves to.

**The compiler shim.** On Windows `buildcfg.CC` is the path to `mwccarm.exe` and the twenty-odd
`[CC] + FLAGS + [...]` call sites are correct as written. On Unix it is a generated wrapper under
`$SP/toolchain/` that `exec`s the same `.exe` through wibo. Twenty-odd call sites stay untouched,
and the Windows path keeps its exact semantics — which matters, because this is the code that
decides whether a function is a match. `exec`, not a subshell: the pid, the signals and the exit
status must be the compiler's, so that killing a hung gate kills the compiler.

**`procs.py`.** The fleet scripts found processes with
`powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process ..."`, which is why they were
Windows-only. `procs.py` reads `/proc/<pid>/cmdline` on Linux, `ps -axo` on BSD and macOS, and CIM
on Windows, and returns the same fields everywhere. One implementation, so a stop procedure
verified on one platform is verified on all of them.

**`kitenv.sh`.** A stock Debian, Ubuntu or MX Linux has **no `python` binary** — only `python3`.
Every kit script and every doc calls `python`, so on a fresh box they fail with "command not
found" before any of this project's logic runs. `kitenv.sh` resolves `$PY` for you; the fix at the
system level is `sudo apt install python-is-python3`.

## Setup

```bash
git clone -b decomp-matching https://github.com/<you>/dqix-decomp.git
git clone https://github.com/ZevyaDev/dqix-decomp-kit.git

cd dqix-decomp
python3 -m pip install -r tools/requirements.txt ninja
python3 tools/configure.py usa
ninja min          # this fetches ./wibo, the Win32 runner. No wine needed.

cd ../dqix-decomp-kit
bash setup_unix.sh              # checks everything, installs nothing, prints the next command
python3 -m pip install --user capstone pyelftools
python3 kit_init.py --slow
python3 selfcheck.py
```

`setup_unix.sh --install` will `apt-get install` what it finds missing. It never supplies the
base ROM: that is yours, placed at `extract/baserom_dqix_usa.nds` as the decomp README says.

Verify the port end to end at any time:

```bash
python3 linuxenv.py     # platform, runner, whether the runner can load mwccarm.exe
```

## The Win32 runner

`mwccarm.exe` is a Windows PE binary. The decomp already knows how to run it on Linux and
`linuxenv.py` follows the decomp's own choice rather than inventing a second policy.

| runner | what it is | notes |
|---|---|---|
| **wibo** | a small Win32 loader | what the decomp downloads and defaults to. No prefix, no daemon, seconds per compile. Preferred. |
| wine | the full compatibility layer | works and is more widely packaged, but much slower per compile and needs a prefix initialised. Fallback. |

Resolution order: `DQIX_WINE` if set, then `wibo`/`wine`/`wine64` on `PATH`, then `$REPO/wibo`.

| variable | effect |
|---|---|
| `DQIX_WINE=<path or name>` | use this runner |
| `DQIX_WINE=none` | no prefix at all — correct if your `.exe` files are natively executable (`binfmt_misc`, or a native rebuild of mwccarm). Nothing in the kit needs changing. |
| `DQIX_NO_SHIM=1` | do not write shims; report the plain path. Debugging only — gates will then fail to exec. |
| `DQIX_PY=<path>` | the python to use, for a venv or a pyenv shim |

Missing runner is a `FAIL` from `kit_init.py` and from `setup_unix.sh`, with the fix in the
message. It is not an exception at import: `buildcfg` is imported by `claim.py`, `progress.py` and
others that never compile anything, and a missing runner must not stop those from starting.

## The fleet

The autonomous fleet works, with the Unix twins in place of the PowerShell four:

| instead of | use |
|---|---|
| `psq.sh` | `psql.sh` |
| `fullstop.sh` | `fullstop_linux.sh` |
| `killfleet.sh` | `killfleet_linux.sh` |
| `health.sh` | `health_linux.sh` |

Everything else — `pull_all.sh`, `pull_worker.sh`, `supervise.sh`, `finish_wave.sh`,
`integrate_fast.sh` — is already POSIX bash and runs unchanged. They do call `python`; either
install `python-is-python3` or prefix with `kitenv.sh`'s `$PY`.

**Workers are native here.** The Windows scripts kill on both sides because `kill -9` on a
`claude` worker left the reparented `claude.exe` still spending tokens, and only Windows
enumeration can find that. On Unix the process you signal is the process that spends, so
`killfleet_linux.sh` collapses to one enumeration. It still matches the worker **prompt**, never
the image name — run this beside your own interactive Claude sessions, which must survive.

**`frida/` and `pad/renum/` do not work here.** They inject into the compiler to force its
colouring and scheduling decisions, and they spawn `mwccarm.exe` expecting a native Windows
process to attach to. wibo is a loader, not an attachable target. The gate, the diff, the sweeps,
`colorsweep.py` and all of integration are unaffected.

## Keeping the state directory on real Linux storage

`$SP` (default `../dqix-kit-state`) holds the only copy of every attempt and every matched source.
Keep it on a real filesystem — not `/tmp`, not a network mount, not the decomp's `build/`. On
WSL that means the Linux filesystem (`~/...`), not `/mnt/c/...`: compiling under `/mnt/c` is
dramatically slower and a `tmpfs` is wiped on reboot.

## What is not covered

Stated plainly rather than discovered later:

- `frida/*.py` and `pad/renum/*.py` — need a native Windows compiler process (above).
- `dsd.exe` and `objdiff-cli.exe` are fetched by the decomp for your platform automatically;
  `countfix.py` and `merge_human.sh` now resolve them through `linuxenv.TOOL`. Nothing else names
  them.
- No macOS or BSD build has been run end to end. The code paths are written for them (`ps -axo`,
  no `.exe`, no `/proc` dependence in the fallbacks) but only Linux has been exercised.

## Reporting a problem

Paste the output of:

```bash
python3 linuxenv.py
python3 kit_init.py
```

The first line says which platform and which runner are in play, and whether that runner can load
the compiler; the second says what is missing. Both are the fastest route to a diagnosis, because
a Unix failure is nearly always one of: no `python`, no runner, or a state directory on a
filesystem that is not there.