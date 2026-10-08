"""Which platform is this, and how does a Windows tool get run on it?

Every other module asks this one question instead of guessing. The decomp itself is already
cross-platform: `tools/configure.py` takes `-w <wine|wibo>` and only prefixes the compiler on
non-Windows, and `tools/get_platform.py` drops the `.exe` suffix off `dsd` and `objdiff-cli`
there. The kit sat on top of all that and hardcoded Windows anyway, so `buildcfg.py` named
`mwccarm.exe` and every tool that spawned it failed with an exec error on Linux.

    IS_LINUX        False on Windows, True on Linux and every other Unix.
    TOOL(name)      the platform's name for a decomp tool: `dsd.exe` vs `dsd`.
    runner_cmd()    the argv prefix a Windows binary needs here: [] on Windows, [wibo] on Linux.
    wine_runner()   the resolved runner path, or None if none is installed.
    shim_for(exe)   a POSIX wrapper script that execs `exe` through the runner.

Why a shim and not a prefix threaded through 25 call sites: `buildcfg.CC` is used as
`[CC] + FLAGS + [...]` by `wgate.py`, `wdiff.py`, `classify.py`, `integrate.py`, `regress.py`,
`sdiff.py`, `tucheck.py`, `pad/*.py` and more. On Windows that string is the executable itself
and every one of those lines is correct as written. Rather than change twenty-five call sites
and risk a silent Windows regression in the one path that decides what a match is, Linux gets a
wrapper executable at the same path: `[shim] + FLAGS` is still a correct argv, and the twenty-five
lines are untouched.

    DQIX_WINE       override the runner. Bare name (`wine`) is looked up on PATH; a path is used
                    as-is. `DQIX_WINE=none` disables the prefix entirely, for a decomp that has
                    been taught to run its own binaries (binfmt_misc, a native rebuild).
    DQIX_NO_SHIM=1  do not write shims; report the plain path instead. Only for debugging a
                    runner problem -- `wgate.py` will then fail to exec on Linux, as it should.
"""
import os
import platform
import shutil
import stat
import subprocess
import sys

import kitpaths as _kp

REPO = _kp.REPO
SP = _kp.SP

SYS = platform.system()
IS_WINDOWS = SYS == "Windows"
# Every Unix is treated the same: Linux, the BSDs and macOS all have /proc-less process
# enumeration through `ps` and the same missing .exe suffix. No per-distro branch anywhere.
IS_UNIX = not IS_WINDOWS

SHIM_DIR = os.path.join(SP, "toolchain")
# wibo is what the decomp downloads and defaults to: a small Win32 loader, no wine prefix, no
# daemon, seconds per invocation instead of tens. wine works and is the fallback.
WIBO = os.path.join(REPO, "wibo")
WINE_NAMES = ("wibo", "wine", "wine64")

_cached = None
_problem = None


def _resolve_runner():
    """-> argv prefix for running a Windows binary here. [] on Windows."""
    if IS_WINDOWS:
        return []
    override = os.environ.get("DQIX_WINE")
    if override is not None:
        if override.strip().lower() == "none":
            return []
        if os.path.sep in override or os.path.exists(override):
            return [override]
        found = shutil.which(override)
        if found:
            return [found]
        return _fail(f"DQIX_WINE={override!r} is neither an existing path nor on PATH.")
    for name in WINE_NAMES:
        found = shutil.which(name)
        if found:
            return [found]
    if os.path.exists(WIBO) and os.access(WIBO, os.X_OK):
        return [WIBO]
    return _fail(
        "no Win32 runner found, so the decomp's mwccarm.exe cannot run here: install wibo (what "
        f"the decomp downloads: cd {REPO} && python tools/configure.py usa && ninja min, which "
        f"fetches {WIBO}) or `sudo apt install wine`, or set DQIX_WINE=<path> to choose one")


def _fail(message):
    """Record why this platform cannot compile and report no prefix.

    Deliberately NOT an exception: `buildcfg` is imported by `claim.py`, `progress.py` and the
    rest, none of which compile anything. A missing runner has to fail the tools that need it
    with a readable line, not stop the ones that do not from starting. `kit_init.py` prints
    this as a FAIL, and `check_runner` repeats it at the point of use.
    """
    global _problem
    _problem = message
    return []


def runner_problem():
    """Why this platform cannot compile, or None. Safe to call anywhere; never raises."""
    runner_cmd()
    return _problem


def runner_cmd():
    global _cached
    if _cached is None:
        _cached = _resolve_runner()
    return list(_cached)


def wine_runner():
    """The resolved runner path, or None on Windows."""
    cmd = runner_cmd()
    return cmd[0] if cmd else None


def TOOL(name, repo=REPO):
    """A decomp tool's path on this platform: dsd.exe on Windows, dsd everywhere else."""
    base = name if os.path.splitext(name)[1] else name + (".exe" if IS_WINDOWS else "")
    return os.path.join(repo, base)


def _write(path, text):
    """Write a wrapper script and make it executable. Returns True if it changed."""
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                if fh.read() == text:
                    return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, os.stat(tmp).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, path)
    return True


def shim_for(exe, name=None):
    """A runnable path for `exe` on this platform.

    On Windows this is `exe` itself: nothing is written and every caller behaves exactly as
    before. On Unix it is a generated wrapper under `$SP/toolchain/` that execs the real
    binary through the runner. Falls back to the bare path if shims are disabled, which is
    what a natively-executable mwccarm.exe needs.
    """
    if IS_WINDOWS or os.environ.get("DQIX_NO_SHIM") == "1":
        return exe
    prefix = runner_cmd()
    if not prefix:
        return exe             # no runner: return the real path, so the exec error names the .exe
    tag = (name or os.path.basename(exe)).replace(".exe", "")
    out = os.path.join(SHIM_DIR, tag)
    # `exec` so the wrapper IS the compiler: the pid, the signals and the exit status are the
    # compiler's, not a shell's. A worker that SIGKILLs a hung gate has to kill the compiler.
    body = "#!/bin/sh\n# generated by linuxenv.py -- runs %s through %s\nexec %s %s \"$@\"\n" % (
        os.path.basename(exe), " ".join(prefix), " ".join(prefix), _q(exe))
    try:
        _write(out, body)
    except OSError as e:
        return exe                     # unwritable state dir: the caller reports the exec error
    return out


def _q(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def describe():
    """One line for the `kit_init.py` header and for a bug report."""
    if IS_WINDOWS:
        return "windows"
    runner = wine_runner()
    return "%s (runner: %s)" % (SYS.lower(), runner or "none")


def check_runner():
    """-> list of human-readable problems, empty when this platform can build."""
    if IS_WINDOWS:
        return []
    prefix = runner_cmd()
    if not prefix:
        return [_problem or "no Win32 runner configured"]
    runner = prefix[0]
    problems = []
    if not os.path.exists(runner):
        problems.append(f"runner {runner} does not exist")
        return problems
    compiler = os.path.join(REPO, "tools", "mwccarm")
    if not os.path.isdir(compiler):
        problems.append(f"no mwccarm build in {compiler}; run `ninja min` in the decomp")
    # Prove the runner can actually load the compiler. `mwccarm.exe -help` needs no ROM, no
    # wineprefix and no configuration, so this is the cheapest honest end-to-end check there
    # is: it fails loudly here instead of as an unexplained COMPILE-FAIL in every gate.
    exe = os.path.join(compiler, "2.0", "sp2p2", "mwccarm.exe")
    if not os.path.exists(exe):
        versions = sorted(d for d in _subdirs(compiler) if os.path.isdir(os.path.join(compiler, d)))
        if not versions:
            problems.append(f"no mwccarm build under {compiler}")
            return problems
        exe = os.path.join(compiler, versions[-1], "sp2p2", "mwccarm.exe")
    try:
        r = subprocess.run([runner, exe, "-help"], capture_output=True, timeout=60,
                           cwd=REPO)
        # mwccarm exits non-zero on -help; it is the absence of a loader error that matters.
        blob = (r.stdout + r.stderr).decode("utf-8", "replace").lower()
        for marker in ("not a valid win32", "cannot open", "err:module", "image not found",
                       "was not found", "no such file"):
            if marker in blob:
                problems.append(f"{os.path.basename(runner)} cannot load mwccarm.exe: "
                                f"{blob.strip()[:160]}")
                break
    except subprocess.TimeoutExpired:
        problems.append(f"{os.path.basename(runner)} hung for 60s running mwccarm.exe -help")
    except OSError as e:
        problems.append(f"cannot run {runner}: {e}")
    return problems


def _subdirs(path):
    try:
        return os.listdir(path)
    except OSError:
        return []


if __name__ == "__main__":
    # `--tool NAME` prints one bare path, so a shell script can use it without parsing this
    # report. Every other invocation is the human-facing description below.
    if len(sys.argv) > 2 and sys.argv[1] == "--tool":
        print(TOOL(sys.argv[2]))
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--runner":
        print(wine_runner() or "")
        raise SystemExit(0)
    print("platform   " + describe())
    print("kit        " + _kp.KIT)
    print("state      " + SP)
    print("repo       " + REPO)
    print("runner     " + (wine_runner() or "(none)"))
    for tool in ("dsd", "objdiff-cli"):
        path = TOOL(tool)
        print(f"{tool:<10} " + path + ("  [present]" if os.path.exists(path) else "  [MISSING]"))
    problems = check_runner()
    for p in problems:
        print("FAIL  " + p)
    if not problems:
        print("ok    this platform can run the decomp's compiler")
    raise SystemExit(1 if problems else 0)