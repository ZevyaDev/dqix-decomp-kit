"""Where the kit's code, its state and the decomp checkout live.

    KIT    this checkout: scripts, docs, skills. Nothing the pipeline produces is written here.
    SP     the state directory: attempts, logs, claims, staging, worker docs, knobs. $DQIX_STATE, else
           the path in KIT/state.path, else ../dqix-kit-state beside the checkout. Kept outside the
           checkout so no git command run in it can touch a single attempt.
    REPO   the decomp checkout: $DQIX_REPO, else ../dqix-decomp beside the checkout.

    python kitpaths.py kit|state|repo     print one of them, for shell scripts
    python kitpaths.py behind             commits the published kit is ahead of this checkout
"""
import os
import sys


def _norm(p):
    return os.path.abspath(p).replace("\\", "/")


def bash(base=None):
    import shutil
    env = dict(os.environ if base is None else base)
    if os.name != "nt":
        found = shutil.which("bash")
        if not found:
            raise FileNotFoundError("bash is not on PATH")
        env["PATH"] = os.pathsep.join(p for p in (os.path.dirname(found), env.get("PATH")) if p)
        return found, env
    roots = [os.path.join(os.environ[k], "Git") for k in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")
             if os.environ.get(k)]
    if os.environ.get("LOCALAPPDATA"):
        roots.append(os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Git"))
    for exe in (shutil.which("git"), shutil.which("bash")):
        if exe:
            d = os.path.dirname(os.path.abspath(exe))
            while os.path.basename(d).lower() in ("cmd", "bin", "usr", "mingw32", "mingw64"):
                d = os.path.dirname(d)
            roots.append(d)
    for root in roots:
        sh = os.path.join(root, "usr", "bin", "bash.exe")
        if os.path.isfile(sh):
            env["PATH"] = os.pathsep.join([os.path.join(root, "usr", "bin"),
                                           os.path.join(root, "mingw64", "bin"), env.get("PATH", "")])
            return _norm(sh), env
    raise FileNotFoundError("no Git Bash found: install Git for Windows")


KIT = _norm(os.path.dirname(os.path.abspath(__file__)))


def _state():
    env = os.environ.get("DQIX_STATE")
    if env:
        return _norm(env)
    try:
        with open(os.path.join(KIT, "state.path"), encoding="utf-8") as fh:
            line = fh.readline().strip()
        if line:
            return _norm(line if os.path.isabs(line) else os.path.join(KIT, line))
    except OSError:
        pass
    return _norm(os.path.join(os.path.dirname(KIT), "dqix-kit-state"))


SP = _state()
REPO = _norm(os.environ.get("DQIX_REPO", os.path.join(os.path.dirname(KIT), "dqix-decomp")))
CLAUDE_PROJECTS = _norm(os.environ.get("CLAUDE_PROJECTS", os.path.expanduser("~/.claude/projects")))
KIT_URL = os.environ.get("DQIX_KIT_URL", "https://github.com/ZevyaDev/dqix-decomp-kit.git")
KIT_BRANCH = os.environ.get("DQIX_KIT_BRANCH", "main")
DECOMP_URL = os.environ.get("DQIX_DECOMP_URL", "https://github.com/ZevyaDev/dqix-decomp.git")
DECOMP_BRANCH = os.environ.get("DQIX_DECOMP_BRANCH", "decomp-matching")
UPSTREAM_URL = os.environ.get("DQIX_UPSTREAM_URL", "https://github.com/DQIX/dqix-decomp.git")
UPSTREAM_BRANCH = os.environ.get("DQIX_UPSTREAM_BRANCH", "main")


def module_label(mod):
    m = str(mod).strip()
    if m == "main":
        return "main"
    if m.isdigit():
        return "ov%03d" % int(m)
    if m[:2].lower() == "ov" and m[2:].isdigit():
        return "ov%03d" % int(m[2:])
    return m
BUSY = ("pull_all.pid", "wave.lock", "claims/INTEGRATING")
FRESH_EVERY = 600


def busy():
    found = []
    for b in BUSY:
        p = os.path.join(SP, b)
        if os.path.isdir(p) or (os.path.isfile(p) and os.path.getsize(p) > 0):
            found.append(b)
    return found


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def _resolve(gitdir, common, ref):
    for _ in range(8):
        if not ref.startswith("ref: "):
            return ref if len(ref) in (40, 64) and all(c in "0123456789abcdef" for c in ref) else None
        name = ref[5:].strip()
        for root in (gitdir, common):
            if os.path.isfile(os.path.join(root, name)):
                ref = _read(os.path.join(root, name))
                break
        else:
            try:
                with open(os.path.join(common, "packed-refs"), encoding="utf-8") as fh:
                    found = [l.split()[0] for l in fh if l.rstrip().endswith(" " + name)]
            except OSError:
                found = []
            return found[0] if found else None
    return None


def head(repo=None):
    import subprocess
    repo = repo or KIT
    try:
        gitdir = os.path.join(repo, ".git")
        if os.path.isfile(gitdir):
            gitdir = os.path.join(repo, _read(gitdir).split("gitdir:", 1)[1].strip())
        common = os.path.join(gitdir, _read(os.path.join(gitdir, "commondir"))) \
            if os.path.isfile(os.path.join(gitdir, "commondir")) else gitdir
        if not os.path.isdir(os.path.join(common, "reftable")):
            sha = _resolve(gitdir, common, _read(os.path.join(gitdir, "HEAD")))
            if sha:
                return sha
    except (OSError, IndexError):
        pass
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True,
                          timeout=30).stdout.strip()


def behind():
    """Commits the published kit is ahead of this checkout, fetched at most every FRESH_EVERY seconds."""
    import subprocess
    import time
    stamp = os.path.join(SP, "wlog", ".kit_fresh")
    run = lambda *a: subprocess.run(["git", "-C", KIT, *a], capture_output=True, text=True, timeout=30)
    head_sha = head()
    try:
        count, seen = (open(stamp, encoding="utf-8").read().split() + [""])[:2]
        count, age = int(count), time.time() - os.path.getmtime(stamp)
    except (OSError, ValueError):
        count, seen, age = 0, "", FRESH_EVERY
    if age >= FRESH_EVERY or seen != head_sha:
        os.makedirs(os.path.dirname(stamp), exist_ok=True)
        open(stamp, "w", encoding="utf-8").write(f"{count if seen == head_sha else 0} {head_sha}")
        if run("fetch", "-q", KIT_URL, KIT_BRANCH).returncode == 0:
            count = int(run("rev-list", "--count", "HEAD..FETCH_HEAD").stdout.strip() or 0)
            open(stamp, "w", encoding="utf-8").write(f"{count} {head_sha}")
        elif seen != head_sha:
            count = 0
    return count


def result_path(name):
    return os.path.join(SP, "wlog", name + ".txt")


def record(name, lines):
    path = result_path(name)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(line + "\n" for line in lines))
        os.replace(tmp, path)
    except OSError:
        pass


def stale_message(count):
    return (f"KIT IS {count} COMMIT(S) BEHIND the published kit: run `python {KIT}/kit_update.py` now "
            "(it keeps your own unpublished commits on top)")


def _freshness():
    count = behind()
    if count and not busy():
        print(stale_message(count), file=sys.stderr)


if os.environ.get("DQIX_NO_FRESHNESS") != "1":
    try:
        _freshness()
    except Exception:
        pass

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which == "behind":
        print(behind())
    elif which in ("kit", "state", "repo"):
        print({"kit": KIT, "state": SP, "repo": REPO}[which])
    else:
        sys.exit(__doc__)
