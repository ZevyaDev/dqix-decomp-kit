"""List processes, with their full command lines, on any platform.

    python procs.py                     every process, `pid ppid age_min cmdline`
    python procs.py --match REGEX       only command lines matching REGEX
    python procs.py --kind work         the fleet's own script names (a curated list)
    python procs.py --kind watcher      monitors AND the tail/grep children they spawned
    python procs.py --count             just a number, for scripts that branch on it
    python procs.py --exclude REGEX     drop matching command lines
    python procs.py --exclude-self      drop this process and its ancestors
    python procs.py --workers           headless Claude Code workers only (` -p ` + DQIX)
    python procs.py --orphan-parent     drop entries whose parent pid is not alive

Replaces `powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process ..."`, which was
the only thing making the fleet scripts Windows-only. Two things it has to get right, both of
which the PowerShell versions were burned by:

SELF-MATCH. Any process listing itself by pattern text matches its own query -- the python
process, and under Git Bash the bash shells wrapping it. `psq.sh` once answered "4 processes
running" against a completely idle machine for 36 minutes because of exactly this.
`--exclude-self` drops the querying process and every ancestor up to init, by pid, so the
answer cannot depend on the pattern text. Use it by default in anything that asks "is the
fleet up?"; `--exclude` is the coarse text guard for the rest.

COMMAND LINES ARE THE POINT, NOT THE PROCESS NAME. `ps` without arguments on macOS, and
`ps -W` under Git Bash, do not print arguments, so matching a name or a truncated listing
finds nothing. This reads them directly: /proc/<pid>/cmdline on Linux, `ps -eo` elsewhere, and
WMI on Windows so the same tool works on all three.

On Linux a worker killed with SIGKILL leaves a ZOMBIE until its parent reaps it, and a zombie
keeps its /proc/<pid>/cmdline. Counting those reports work that died as still running. Zombies
are excluded, and their state is reported separately so `--verbose` can show them.
"""
import argparse
import os
import re
import subprocess
import sys
import time

import kitpaths as _kp

KIT = _kp.KIT
IS_WINDOWS = os.name == "nt"

# The fleet's own dispatchers, read off disk rather than hand-kept: a hand-kept list does not
# grow when a script is added, and a list that cannot go stale is the whole point.
FLEET = ("pull_all.sh", "pull_worker.sh", "supervise.sh", "run_all.sh", "run_module.sh",
         "integrate_fast.sh", "integrate_all.sh", "finish_wave.sh", "ov_recover.py",
         "repairsweep.py", "colorsweep.py", "proppurge.py", "transmassive.py")

WORKER_RE = re.compile(r"\s-p\s.*DQIX")

# The kit's own monitor loops. Read off disk for the reason FLEET is: a hand-kept list does not
# grow when a script is added, and then a stop leaves a watcher running and stacks another copy
# on the next restart.
WATCHER_RE = re.compile(
    "|".join(re.escape(n) for n in
             ("health.sh", "health_linux.sh", "pull_watch.sh", "watch_verdicts.sh", "leverwatch.sh",
              "nearmiss_watch.sh", "presweep_watch.sh", "verdictwatch.sh", "gatewatch.sh")))


def descendants(rows, pat, depth=8):
    """Every process matching `pat`, plus their descendants, transitively."""
    children = {}
    for pid, ppid, *_ in rows:
        children.setdefault(ppid, []).append(pid)
    seeds = {r[0] for r in rows if pat.search(r[2] or "")}
    out, stack = set(seeds), list(seeds)
    while stack:
        pid = stack.pop()
        for kid in children.get(pid, ()):
            if kid not in out:
                out.add(kid)
                stack.append(kid)
    return out


def _ps_etimes(pid, etimes):
    """Age in seconds: from ps when it gave us one, else from /proc."""
    if etimes and etimes >= 0:
        return etimes
    try:
        return int(time.time() - os.stat(f"/proc/{pid}").st_ctime)
    except OSError:
        return 0


def _read_linux():
    """(pid, ppid, cmdline, cpu_seconds, state) from /proc. Nothing else needed on Linux."""
    out = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                raw = fh.read()
            with open(f"/proc/{pid}/stat", "rb") as fh:
                stat = fh.read().decode("utf-8", "replace")
            with open(f"/proc/{pid}/status", "rb") as fh:
                status = fh.read().decode("utf-8", "replace")
        except OSError:
            continue                      # exited between listdir and open: normal under load
        # comm can contain spaces and parentheses, so fields are counted from the LAST ')'.
        tail = stat[stat.rfind(")") + 1:].split()
        ppid = int(tail[1]) if len(tail) > 1 else 0
        state = tail[0] if tail else "?"
        cpu = 0.0
        m = re.search(r"^VmRSS:\s+(\d+)", status, re.M)
        rss = int(m.group(1)) if m else 0
        utime = re.search(r"^utime:\s+(\d+)", status, re.M)
        stime = re.search(r"^stime:\s+(\d+)", status, re.M)
        if utime and stime:
            cpu = (int(utime.group(1)) + int(stime.group(1))) / os.sysconf("SC_CLK_TCK")
        cmd = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        out.append((pid, ppid, cmd, cpu, state, rss * 1024))
    return out


def _read_ps():
    """(pid, ppid, cmdline, cpu_seconds, state, rss) from ps, for BSDs and macOS."""
    fmt = "pid=,ppid=,etimes=,time=,state=,rss=,args="
    r = subprocess.run(["ps", "-axo", fmt], capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(["ps", "-ax", "-o", "pid=,ppid=,time=,state=,rss=,args="],
                           capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        f = line.split(None, 6)
        if len(f) < 6 or not f[0].isdigit():
            continue
        etimes = -1
        rest = f[2:]
        if rest and rest[0].isdigit():                 # etimes, only on the first attempt
            etimes = int(rest[0])
            rest = rest[1:]
        cputime, state, rss, args = (rest + ["", "", "", ""])[:4]
        cpu = _clock_to_s(cputime)
        out.append((int(f[0]), int(f[1]), args.strip(), cpu, state or "?", (int(rss) if rss.isdigit() else 0)))
    return out


def _clock_to_s(text):
    """ps `time` is [[dd-]hh:]mm:ss."""
    if not text or text == "?":
        return 0.0
    days = 0
    if "-" in text:
        d, text = text.split("-", 1)
        days = int(d) if d.isdigit() else 0
    parts = [int(p) for p in text.split(":") if p.isdigit()]
    while len(parts) < 3:
        parts.insert(0, 0)
    return float(days * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2])


def _read_windows():
    """(pid, ppid, cmdline, cpu_seconds, state, rss) from CIM, so this tool works there too."""
    ps = ("Get-CimInstance Win32_Process | ForEach-Object { "
          "'{0}|{1}|{2}|{3}|{4}|{5}|{6}' -f $_.ProcessId, $_.ParentProcessId, "
          "([int]((Get-Date) - $_.CreationDate).TotalSeconds), "
          "[int]($_.UserModeTime + $_.KernelTime), 'R', $_.WorkingSetSize, $_.CommandLine }")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True)
    out = []
    for line in r.stdout.replace("\r", "").splitlines():
        f = line.split("|", 6)
        if len(f) < 7 or not f[0].isdigit():
            continue
        try:
            age, cpu = int(f[2]), int(f[3]) / 10_000_000      # FILETIME is 100ns
            rss = int(f[5]) if f[5].isdigit() else 0
        except ValueError:
            age, cpu, rss = 0, 0.0, 0
        out.append((int(f[0]), int(f[1]), f[6], float(cpu), f[4], rss))
    return out


def snapshot():
    """Every live process. (pid, ppid, cmdline, cpu_seconds, state, rss_bytes)"""
    if IS_WINDOWS:
        return _read_windows()
    if os.path.isdir("/proc"):
        return _read_linux()
    return _read_ps()


def ancestors(rows):
    """The pids of this process and everything that spawned it, up to init."""
    ppid = {r[0]: r[1] for r in rows}
    self_set = set()
    pid = os.getpid()
    for _ in range(24):
        if pid in self_set or pid not in ppid:
            break
        self_set.add(pid)
        pid = ppid[pid]
    return self_set


def is_worker(cmd, name=None):
    """A headless Claude Code worker: ` -p ` AND the DQIX prompt. Never an interactive session.

    The prompt text is the discriminator, not the image name. The operator runs this kit beside
    their own Claude sessions, and killing those would be destroying unrelated work."""
    if not cmd:
        return False
    if WORKER_RE.search(cmd):
        return True
    return name == "claude.exe" and " -p " in cmd and "DQIX" in cmd


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--match", help="regex over the command line")
    ap.add_argument("--exclude", help="regex over the command line to drop")
    ap.add_argument("--exclude-self", action="store_true", default=True,
                    help="drop this process and its ancestors (default)")
    ap.add_argument("--no-exclude-self", dest="exclude_self", action="store_false")
    ap.add_argument("--kind", choices=("all", "work", "job", "watcher"), default="all",
                    help="watcher = the kit's monitor loops AND the children they spawned")
    ap.add_argument("--workers", action="store_true", help="headless Claude workers only")
    ap.add_argument("--orphan-parent", action="store_true",
                    help="drop entries whose parent pid is not alive")
    ap.add_argument("--include-zombies", action="store_true")
    ap.add_argument("--count", action="store_true", help="print only a number")
    ap.add_argument("--list", action="store_true", help="pid + command line")
    ap.add_argument("--verbose", action="store_true", help="print the table, whatever the mode")
    ap.add_argument("--pids", action="store_true", help="print pids only, one per line")
    args = ap.parse_args()

    rows = snapshot()
    alive = {r[0] for r in rows}
    self_set = ancestors(rows) if args.exclude_self else set()
    inc = re.compile(args.match) if args.match else None
    exc = re.compile(args.exclude) if args.exclude else None

    if args.kind == "work":
        pat = re.compile("|".join(re.escape(n) for n in
                                  ("pull_worker.sh", "pull_all.sh", "supervise.sh", "run_all.sh")))
    elif args.kind == "job":
        pat = re.compile("|".join(re.escape(n) for n in FLEET))
    elif args.kind == "watcher":
        # A MONITOR SPAWNS CHILDREN THAT NAME NOTHING OF THEIRS. A Monitor's `cd` runs in its
        # wrapper shell, so the `tail -f` it starts carries only the log path -- no script name,
        # no kit path. Matching command lines for the monitor's own name therefore finds the
        # monitor and misses every process it is actually holding open, which is the exact
        # failure that left watches live for six hours behind a kill-all that reported success.
        # A watcher is the monitor OR anything descended from one.
        pat = None
        watchers = descendants(rows, WATCHER_RE)
    else:
        pat = None

    zombies = 0
    hit = []
    for pid, ppid, cmd, cpu, state, rss in rows:
        if pid in self_set:
            continue
        if state.startswith("Z") and not args.include_zombies:
            zombies += 1
            continue                       # dead but unreaped: it is NOT still running
        if not cmd:
            continue                       # kernel thread
        if args.orphan_parent and ppid and ppid not in alive:
            continue
        if inc and not inc.search(cmd):
            continue
        if exc and exc.search(cmd):
            continue
        if pat and not pat.search(cmd):
            continue
        if args.workers and not is_worker(cmd):
            continue
        # A spawned child of a monitor, matched by ancestry rather than by its own text.
        if args.kind == "watcher" and pid not in watchers:
            continue
        hit.append((pid, ppid, cmd, cpu, state, rss))

    if args.pids:
        for h in hit:
            print(h[0])
    elif args.count:
        print(len(hit))
    elif args.verbose:
        print(f"{'pid':>8} {'ppid':>8} {'min':>7} {'cpu%':>7}  command")
        for pid, ppid, cmd, cpu, _s, _r in sorted(hit):
            mins = _ps_etimes(pid, -1) // 60
            print(f"{pid:>8} {ppid:>8} {mins:>7} {cpu:>7.0f}  {cmd[:110]}")
    elif args.list:
        for pid, _ppid, cmd, *_ in hit:
            print(f"{pid}  {cmd[:110]}")
    else:
        for pid, ppid, cmd, cpu, _s, _r in hit:
            mins = _ps_etimes(pid, -1) // 60
            print(f"{pid}@@@{ppid}@@@{mins}@@@{cpu:.0f}@@@{cmd}")
    if zombies and args.verbose:
        print(f"# {zombies} zombie(s) excluded: SIGKILLed, not yet reaped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())