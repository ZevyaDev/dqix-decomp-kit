"""Where the kit's code, its state and the decomp checkout live.

    KIT    this checkout: scripts, docs, skills. Nothing the pipeline produces is written here.
    SP     the state directory: attempts, logs, claims, staging, worker docs, knobs. $DQIX_STATE, else
           the path in KIT/state.path, else ../dqix-kit-state beside the checkout. Kept outside the
           checkout so no git command run in it can touch a single attempt.
    REPO   the decomp checkout: $DQIX_REPO, else ../dqix-decomp beside the checkout.

    python kitpaths.py kit|state|repo     print one of them, for shell scripts
    python kitpaths.py region             usa, jpn or eur; unset is usa; anything else exits 2
    python kitpaths.py require-usa        exit 2 unless the region is usa
    python kitpaths.py behind             commits the published kit is ahead of this checkout
"""
import os
import sys


def _norm(p):
    return os.path.abspath(p).replace("\\", "/")


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
_REGIONS = ("usa", "jpn", "eur")


def region():
    """The active region. Unset is usa. Anything else is an error, not a silent usa."""
    value = os.environ.get("DQIX_REGION", "usa").strip().lower()
    if value not in _REGIONS:
        print(f"DQIX_REGION={value} is not usa, jpn or eur", file=sys.stderr)
        raise SystemExit(2)
    return value


def require_usa():
    """Landing tools key state and `// USA:` tags by the USA address. Another region would
    write those addresses into that region's delinks."""
    got = region()
    if got != "usa":
        print(f"refusing DQIX_REGION={got}: this tool lands USA addresses", file=sys.stderr)
        raise SystemExit(2)


def ninja_matches(text, region_name):
    return f"config/{region_name}/" in text or f"config\\{region_name}\\" in text
DECOMP_URL = os.environ.get("DQIX_DECOMP_URL", "https://github.com/ZevyaDev/dqix-decomp.git")
DECOMP_BRANCH = os.environ.get("DQIX_DECOMP_BRANCH", "decomp-matching")
BUSY = ("pull_all.pid", "wave.lock", "claims/INTEGRATING")
FRESH_EVERY = 600


def busy():
    found = []
    for b in BUSY:
        p = os.path.join(SP, b)
        if os.path.isdir(p) or (os.path.isfile(p) and os.path.getsize(p) > 0):
            found.append(b)
    return found


def behind():
    """Commits the published kit is ahead of this checkout, fetched at most every FRESH_EVERY seconds."""
    import subprocess
    import time
    stamp = os.path.join(SP, "wlog", ".kit_fresh")
    try:
        count = int(open(stamp, encoding="utf-8").read().strip() or 0)
        age = time.time() - os.path.getmtime(stamp)
    except (OSError, ValueError):
        count, age = 0, FRESH_EVERY
    if age >= FRESH_EVERY:
        os.makedirs(os.path.dirname(stamp), exist_ok=True)
        open(stamp, "w", encoding="utf-8").write(str(count))
        run = lambda *a: subprocess.run(["git", "-C", KIT, *a], capture_output=True, text=True, timeout=30)
        if run("fetch", "-q", KIT_URL, KIT_BRANCH).returncode == 0:
            count = int(run("rev-list", "--count", "HEAD..FETCH_HEAD").stdout.strip() or 0)
            open(stamp, "w", encoding="utf-8").write(str(count))
    return count


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
    elif which == "region":
        print(region())
    elif which == "require-usa":
        require_usa()
    elif which in ("kit", "state", "repo"):
        print({"kit": KIT, "state": SP, "repo": REPO}[which])
    else:
        sys.exit(__doc__)
