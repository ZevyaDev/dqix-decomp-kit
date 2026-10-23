"""Refuse a pull request built on a stale kit or a stale decomp.

    python prready.py kit       last step before a pull request on ZevyaDev/dqix-decomp-kit
    python prready.py decomp    last step before a pull request on ZevyaDev/dqix-decomp
    python prready.py --hook    Claude Code PreToolUse hook: blocks `gh pr create` until READY, and
                                `gh pr merge` on the decomp, which lands through landpr.sh

Fetches the published kit and decomp-matching and compares your commits with them. Exit 0: READY.
1: NOT READY, one line per problem saying what to do. 2: a fetch failed, or the hook blocked.
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

os.environ["DQIX_NO_FRESHNESS"] = "1"
import delinked
import gitread
import kitpaths
import plausible
from pragmas import codegen_pragmas

KIT, REPO = kitpaths.KIT, kitpaths.REPO
MATCH_PATHS = ("src/", "include/", "config/")
SOURCE = (".c", ".cpp", ".s")
ADDR = re.compile(r"\b(02[0-9a-fA-F]{6})\b")
FUNCTION = re.compile(r"\bkind:function\S*\s+addr:0x([0-9a-fA-F]+)")
SYMBOLS = re.compile(r"^config/([^/]+)/(.+/symbols\.txt)$")
MARKER = re.compile(r"(?m)^(<{7}|>{7})( |\r?$)")
USA_TAG = re.compile(r"(?m)^// USA: \S+")
REGION_ONLY = re.compile(r"(?m)^#if defined\((jpn|eur)\)\s*$")


MANGLED_FREE = re.compile(r"^_Z(\d+)")
DEFAULT_NAME = re.compile(r"^(func|data)_(ov\d{3}_)?(jpn_|eur_)?[0-9a-f]{8}(_\w+)?$")


def own_ident(name):
    if not name.startswith("_Z"):
        return name
    if name.startswith("_ZN"):
        i, last = (4 if name.startswith("_ZNK") else 3), None
        while i < len(name) and name[i] != "E":
            m = re.match(r"\d+", name[i:])
            if not m:
                return None
            j = i + len(m.group())
            last, i = name[j:j + int(m.group())], j + int(m.group())
        return last
    m = MANGLED_FREE.match(name)
    return name[m.end():m.end() + int(m.group(1))] if m else None


def toolchain_name(name):
    return name.startswith(("@", ".", "__sinit", "_ZZ", "_ZT", "_ZGV")) or "$" in name


def upstream_names(tip):
    paths = [p for p in files(REPO, tip, "config") if p.endswith("symbols.txt")]
    texts = gitread.blobs(REPO, [f"{tip}:{p}" for p in paths]).values()
    full = set().union(*(names(t) for t in texts))
    idents = {own_ident(n) for n in full} | {c for n in full for c in re.findall(r"\d+([A-Za-z_]\w*)", n)}
    return full, idents


def not_upstream(name, full, idents):
    if DEFAULT_NAME.match(name) or toolchain_name(name) or name in full:
        return False
    ident = own_ident(name)
    return not ident or not (DEFAULT_NAME.match(ident) or ident in idents)


def signature_only(old, new):
    a, b = MANGLED_FREE.match(old), MANGLED_FREE.match(new or "")
    if not a or not b or a.group(1) != b.group(1):
        return False
    n = int(a.group(1))
    return old[a.end():a.end() + n] == new[b.end():b.end() + n] and old != new


def region_tagged(text):
    if USA_TAG.search(text):
        return True
    m = REGION_ONLY.search(text)
    return bool(m) and bool(re.search(r"(?m)^// %s: \S+" % m.group(1).upper(), text))


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def published(repo, url, branch):
    if git(repo, "fetch", "-q", url, branch).returncode != 0:
        print(f"FETCH FAILED {url} {branch} in {repo}", file=sys.stderr)
        sys.exit(2)
    return git(repo, "rev-parse", "FETCH_HEAD").stdout.strip()


def behind(repo, tip):
    return int(git(repo, "rev-list", "--count", f"HEAD..{tip}").stdout.strip() or 0)


def gained(pair):
    return plausible.gained(*pair)


def plausible_gained(pairs):
    if len(pairs) < 200:
        return [gained(p) for p in pairs]
    with ProcessPoolExecutor(min(8, os.cpu_count() or 1)) as pool:
        return list(pool.map(gained, pairs, chunksize=32))


class Tree:
    def __init__(self, repo):
        self.repo, self.cache = repo, {}

    def prefetch(self, rev, paths):
        specs = [f"{rev}:{p}" for p in paths if f"{rev}:{p}" not in self.cache]
        self.cache.update(gitread.blobs(self.repo, specs))

    def show(self, rev, path):
        self.prefetch(rev, [path])
        return self.cache.get(f"{rev}:{path}", "")


def files(repo, rev, root):
    return git(repo, "ls-tree", "-r", "--name-only", rev, root).stdout.split()


def delinks(tree, rev, root):
    names = [n for n in files(tree.repo, rev, root) if n.endswith("delinks.txt")]
    tree.prefetch(rev, names)
    return [tree.show(rev, n) for n in names]


def landed_functions(repo, rev, root):
    tree, found = Tree(repo), set()
    names = [n for n in files(repo, rev, root) if n.endswith("delinks.txt")]
    tree.prefetch(rev, names + [n[:-len("delinks.txt")] + "symbols.txt" for n in names])
    for n in names:
        texts = [tree.show(rev, n)]
        funcs = FUNCTION.findall(tree.show(rev, n[:-len("delinks.txt")] + "symbols.txt"))
        found |= {int(a, 16) for a in funcs if delinked.covers(int(a, 16), texts)}
    return found


def diff_lines(repo, tip, path, sign):
    return gitread.diff_lines(repo, [f"{tip}...HEAD"], [path]).get(path, ([], []))[sign == "-"]


def names(text):
    return {l.split()[0] for l in text.splitlines() if l.strip()}


def addrs(text):
    return {l.split()[0]: a.group(1).lower() for l in text.splitlines()
            if l.strip() and (a := re.search(r"\baddr:(0x[0-9a-fA-F]+)", l))}


def staleness():
    problems = []
    kit_tip = published(KIT, kitpaths.KIT_URL, kitpaths.KIT_BRANCH)
    n = behind(KIT, kit_tip)
    if n:
        problems.append(f"KIT BEHIND by {n} commit(s): run python kit_update.py, re-run selfcheck.py and "
                        "regress.py, re-gate what you changed")
    decomp_tip = published(REPO, kitpaths.DECOMP_URL, kitpaths.DECOMP_BRANCH)
    n = behind(REPO, decomp_tip)
    if n:
        problems.append(f"DECOMP BEHIND by {n} commit(s): in {REPO} run git pull --rebase "
                        f"{kitpaths.DECOMP_URL} {kitpaths.DECOMP_BRANCH}, then python tools/configure.py usa "
                        "&& ninja check")
    return problems, kit_tip, decomp_tip


def kit(kit_tip, decomp_tip):
    problems = []
    if git(KIT, "diff", "--name-only", f"{kit_tip}...HEAD", "--", "worker_src/deadends.md").stdout.strip():
        problems.append("NO DEAD ENDS: the kit takes no worker_src/deadends.md change; record the miss in $SP "
                        "(blocker.py, the handoff) and open the pull request from a branch without it")
    landed = landed_functions(REPO, decomp_tip, "config/usa/arm9")
    cited = dict.fromkeys(a.lower() for l in diff_lines(KIT, kit_tip, "worker_src/core.md", "+") for a in ADDR.findall(l))
    for addr in cited:
        if int(addr, 16) not in landed:
            problems.append(f"UNPROVEN CITATION {addr} in core.md: not matched on {kitpaths.DECOMP_BRANCH}; "
                            "land the match first or cite a landed address")
    return problems


def decomp(decomp_tip):
    problems = []
    changed = git(REPO, "diff", "--name-only", f"{decomp_tip}...HEAD").stdout.split()
    lines = gitread.diff_lines(REPO, [f"{decomp_tip}...HEAD"], ["src", "include", "config"])
    plus = lambda path: lines.get(path, ([], []))[0]
    minus = lambda path: lines.get(path, ([], []))[1]
    regions = [p.rstrip("/").split("/")[-1] for p in git(REPO, "ls-tree", "-d", "--name-only", "HEAD", "config/").stdout.split()]
    tree = Tree(REPO)
    symbols = [m for m in map(SYMBOLS.match, changed) if m]
    tree.prefetch("HEAD", [p for p in changed if p.startswith(MATCH_PATHS)]
                  + [f"config/{r}/{m.group(2)}" for m in symbols for r in regions])
    tree.prefetch(decomp_tip, [p for p in changed if p.startswith(("src/", "config/usa/"))])
    show = lambda repo, rev, path: tree.show(rev, path)
    reviewed = set(filter(None, os.environ.get("PRREADY_REVIEWED", "").split(os.pathsep)))
    for path in changed:
        if not path.startswith(MATCH_PATHS):
            if path not in reviewed:
                problems.append(f"OUTSIDE A MATCH {path}: differs from {kitpaths.DECOMP_BRANCH}; restore it with "
                                f"git checkout {decomp_tip[:10]} -- {path}, or send it as its own pull request")
        elif MARKER.search(show(REPO, "HEAD", path)):
            problems.append(f"CONFLICT MARKERS in {path}")
    wired = "\n".join(delinks(tree, "HEAD", "config"))
    added = git(REPO, "diff", "--name-only", "--diff-filter=A", f"{decomp_tip}...HEAD", "--", "src").stdout.split()
    for path in added:
        if path.endswith(SOURCE) and f"{path}:" not in wired:
            problems.append(f"DEAD FILE {path}: no delinks.txt entry names it; delete it")
        elif path.endswith((".c", ".cpp")) and not region_tagged(show(REPO, "HEAD", path)):
            problems.append(f"NO USA TAG {path}: put `// USA: <USA symbol>` on the line above the definition")
    sources = [p for p in changed if p.startswith("src/") and p.endswith((".c", ".cpp"))]
    for path, new in zip(sources, plausible_gained([(show(REPO, decomp_tip, p), show(REPO, "HEAD", p)) for p in sources])):
        if new:
            problems.append(f"IMPLAUSIBLE {path}: adds {', '.join(new)}; write what a developer wrote "
                            f"(worker_src/core.md, NATURAL FORMS THAT MATCH WHERE A TRICK DID)")
    named = [p for p in changed if p.startswith(("src/", "include/")) and p.endswith((".c", ".cpp", ".h"))
             and os.path.isfile(f"{REPO}/{p}")]
    if named:
        import plainnames
        for line in plainnames.check(REPO, named):
            problems.append(f"{line} (python plainnames.py fix {line.split()[4].rsplit(':', 1)[0]})")
    for path in changed:
        if path.startswith("src/"):
            gained = (len(codegen_pragmas("\n".join(plus(path)), path))
                      - len(codegen_pragmas("\n".join(minus(path)), path)))
            if gained > 0:
                problems.append(f"CODEGEN PRAGMA {path}: adds {gained}; a match never lands behind one "
                                f"(AGENTS.md rule 8): remove it and find what the source lacks")
        if path.startswith(("src/", "include/")):
            gained = sum(l.count("reinterpret_cast") for l in plus(path)) - \
                sum(l.count("reinterpret_cast") for l in minus(path))
            if gained > 0:
                problems.append(f"REINTERPRET-CAST {path}: adds {gained}; give the value the type it really has "
                                f"instead of casting it")
    if any(SYMBOLS.match(p) for p in changed):
        full, idents = upstream_names(published(REPO, kitpaths.UPSTREAM_URL, kitpaths.UPSTREAM_BRANCH))
        for path in changed:
            if not SYMBOLS.match(path):
                continue
            before = names(show(REPO, decomp_tip, path))
            for line in plus(path):
                name = line.split()[0] if line.strip() else ""
                if name and name not in before and not_upstream(name, full, idents):
                    problems.append(f"NOT AN UPSTREAM NAME {name} in {path}: keep the default func_/data_ name; "
                                    "only names already on upstream main are taken")
    for path in changed:
        m = SYMBOLS.match(path)
        if not m:
            continue
        removed = "\n".join(minus(path))
        gone = names(removed) - names(show(REPO, "HEAD", path))
        was_at = addrs(removed)
        now_named = {a: n for n, a in addrs(show(REPO, "HEAD", path)).items()}
        for region in regions:
            other = f"config/{region}/{m.group(2)}"
            if other != path:
                theirs = names(show(REPO, "HEAD", other))
                for name in sorted(gone & theirs):
                    renamed = now_named.get(was_at.get(name))
                    if renamed in theirs or signature_only(name, renamed):
                        continue
                    problems.append(f"HALF RENAME {name}: gone from {path}, still in {other}; rename it there too")
    return problems


def hooked_target():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return None
    command = str(event.get("tool_input", {}).get("command", ""))
    action = re.search(r"\bgh\s+pr\s+(create|merge)\b", command)
    if not action:
        return None
    if "dqix-decomp-kit" in command:
        target = "kit"
    elif "dqix-decomp" in command:
        target = "decomp"
    else:
        cwd = os.path.abspath(event.get("cwd") or os.getcwd()).replace("\\", "/").lower()
        target = "decomp" if cwd.startswith(REPO.lower()) else "kit"
    if action.group(1) == "merge":
        return "land" if target == "decomp" else None
    return target


def main():
    hook = sys.argv[1:] == ["--hook"]
    if hook:
        target = hooked_target()
        if target is None:
            sys.exit(0)
        if target == "land":
            print("gh pr merge skips the strip, the region ports and the three-region build; "
                  "land decomp pull requests with: bash landpr.sh <number>...", file=sys.stderr)
            sys.exit(2)
    elif sys.argv[1:] in (["kit"], ["decomp"]):
        target = sys.argv[1]
    else:
        sys.exit(__doc__)
    problems, kit_tip, decomp_tip = staleness()
    problems += kit(kit_tip, decomp_tip) if target == "kit" else decomp(decomp_tip)
    report = "\n".join(problems + [f"NOT READY: {len(problems)} problem(s)" if problems else "READY"])
    if hook:
        if problems:
            print(f"prready.py {target}: fix these before opening the pull request.\n{report}", file=sys.stderr)
            sys.exit(2)
        sys.exit(0)
    print(report)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
