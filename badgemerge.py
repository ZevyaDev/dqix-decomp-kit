import os
import re
import subprocess
import sys

DRIVER = "badges"
ATTRIBUTE = f"README.md merge={DRIVER}"
RAW = re.compile(r"raw\.githubusercontent\.com%2F([^%]+)%2F([^%]+)%2F([^%]+)%2F")
ACTIONS = re.compile(r"github\.com/([^/]+)/([^/]+)/actions/")


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def is_badge(line):
    return "img.shields.io/endpoint" in line


def source(text):
    for line in text.splitlines():
        m = RAW.search(line) if is_badge(line) else None
        if m:
            return m.groups()
    return None


def retarget(text, src):
    owner, repo, branch = src
    out = []
    for line in text.splitlines(keepends=True):
        if is_badge(line):
            line = RAW.sub(lambda _: f"raw.githubusercontent.com%2F{owner}%2F{repo}%2F{branch}%2F", line)
            line = ACTIONS.sub(lambda _: f"github.com/{owner}/{repo}/actions/", line)
        out.append(line)
    return "".join(out)


def merge(base, ours, theirs, marker="7"):
    src = source(read(ours))
    if src:
        for path in (base, theirs):
            write(path, retarget(read(path), src))
    rc = subprocess.run(["git", "merge-file", f"--marker-size={marker}", "-L", "ours", "-L", "base",
                         "-L", "theirs", ours, base, theirs]).returncode
    return 0 if rc == 0 else 1


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def driver_command():
    script = os.path.abspath(__file__).replace("\\", "/")
    python = sys.executable.replace("\\", "/")
    return f'"{python}" "{script}" %O %A %B %L'


def install(repo):
    git(repo, "config", f"merge.{DRIVER}.name", "keep the README badge source this branch points at")
    git(repo, "config", f"merge.{DRIVER}.driver", driver_command())
    path = git(repo, "rev-parse", "--path-format=absolute", "--git-path", "info/attributes").stdout.strip()
    if not path:
        return False
    lines = read(path).splitlines() if os.path.isfile(path) else []
    if ATTRIBUTE not in lines:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write(path, "".join(f"{line}\n" for line in lines + [ATTRIBUTE]))
    return installed(repo) is None


def installed(repo):
    attr = git(repo, "check-attr", "merge", "--", "README.md").stdout.strip()
    if not attr.endswith(f": {DRIVER}"):
        return f"README.md has no merge={DRIVER} attribute in {repo}"
    driver = git(repo, "config", f"merge.{DRIVER}.driver").stdout.strip()
    script = os.path.abspath(__file__).replace("\\", "/")
    if f'"{script}"' not in driver:
        return f"merge.{DRIVER}.driver in {repo} does not run {script}"
    return None


def published(repo, url, ref):
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    workflow = git(repo, "show", f"{ref}:.github/workflows/publish-badges.yml").stdout
    b = re.search(r"git push\b[^\n]*\borigin\s+(\S+)", workflow)
    return (m[1], m[2], b[1]) if m and b else None


def main(argv):
    if argv[:1] == ["install"]:
        if len(argv) > 1:
            return 0 if install(argv[1]) else 1
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kitpaths
        return 0 if install(kitpaths.REPO) else 1
    if len(argv) in (3, 4):
        return merge(*argv)
    print("usage: badgemerge.py install [REPO] | %O %A %B [%L]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
