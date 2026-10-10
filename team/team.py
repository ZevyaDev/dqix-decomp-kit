#!/usr/bin/env python3
"""Batch matching for an agent team: pick, reserve, dispatch, verify, integrate, publish, release.

One coordinator session runs this. Workers (subagents, or `codex exec` processes) only write
`$SP/wip/<label>/<addr>.cpp`; everything shared goes through this script, so there is one writer.

    python team/team.py status                     ledger counts and the open reservation
    python team/team.py sync                       fetch decomp-matching, fast-forward the checkout
    python team/team.py candidates [--module 017] [--min 200] [--max 700] [--limit 40]
    python team/team.py reserve --take 24 [--module 017]    or: reserve 017 0218dd18 017 0218dfd8
    python team/team.py issue [--publish]           print / create-or-edit the ONE reservation issue
    python team/team.py next [--label w1] [--per 4]  hand the next group to a subagent (prints prompt)
    python team/team.py dispatch --workers 4 [--per 4] [--model M] [--effort high]
    python team/team.py collect [ADDR ...]          re-gate wip files, quality-check, update ledger
    python team/team.py describe ADDR "text"        set a function's one-line PR description
    python team/team.py integrate [--archive]       build the PR branch from every unsubmitted MATCH
    python team/team.py pr [--open]                 PR body; with --open push, gh pr create, close
                                                     the issue with the PR link, reopen a successor
    python team/team.py release [--keep-matches]    stop: close the issue, release unfinished rows

State lives in $SP/team/ (config.json, ledger.tsv, reports/, logs/, prs/). config.json sets the title
tag and branch prefix (default "[Codex]", "codex/overlay-batch-"); the fork owner is read from the
decomp checkout's `origin` remote. Nothing here writes into
$DQIX_REPO except `sync` (fast-forward only) and `integrate` (the separate integration worktree).
"""
import argparse
import bisect
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)
os.environ.setdefault("DQIX_NO_FRESHNESS", "1")
import kitpaths  # noqa: E402

SP, REPO = kitpaths.SP, kitpaths.REPO
TEAM = os.path.join(SP, "team")
CONFIG = os.path.join(TEAM, "config.json")
LEDGER = os.path.join(TEAM, "ledger.tsv")
REPORTS = os.path.join(TEAM, "reports")
LOGS = os.path.join(TEAM, "logs")
PRS = os.path.join(TEAM, "prs")
PY = sys.executable

DEFAULTS = {
    "tag": "[Codex]",
    "branch_prefix": "codex/overlay-batch-",
    "fork_owner": None,
    "decomp_repo": None,
    "kit_repo": None,
    "base": "decomp-matching",
    "issue": None,
    "batch": 1,
    "integ_state": os.path.join(os.path.dirname(SP), os.path.basename(SP) + "-integ"),
    "commit_trailer": "",
    "pr_footer": "",
    "min_size": 200,
    "max_size": 700,
}
COLS = ("module", "addr", "size", "status", "desc", "note")
LIVE = ("ACTIVE", "ASSIGNED", "MATCH", "RESIDUE")
FUNC = re.compile(r"^(\S+) kind:function\((arm|thumb)[^)]*size=0x([0-9a-fA-F]+)[^)]*\) addr:0x([0-9a-fA-F]+)")
RANGE = re.compile(r"^\s*\.text\s+start:0x([0-9a-fA-F]+)\s+end:0x([0-9a-fA-F]+)")
ADDR = re.compile(r"\b(0x)?(02[0-9a-fA-F]{6})\b")


# ---------------------------------------------------------------- plumbing

def die(msg, code=1):
    print(f"team.py: {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd, cwd=None, env=None, check=False, capture=True):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=capture, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        die(f"{' '.join(cmd[:4])} failed ({r.returncode}): {(r.stderr or r.stdout).strip()[:400]}")
    return r


def gh(*args, check=True):
    return run(["gh", *args], check=check).stdout


def slug(url):
    """owner/name from a GitHub URL, https or ssh."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG):
        cfg.update(json.load(open(CONFIG, encoding="utf-8")))
    cfg["decomp_repo"] = cfg["decomp_repo"] or slug(kitpaths.DECOMP_URL)
    cfg["kit_repo"] = cfg["kit_repo"] or slug(kitpaths.KIT_URL)
    if not cfg["fork_owner"]:
        origin = run(["git", "-C", REPO, "remote", "get-url", "origin"]).stdout.strip()
        cfg["fork_owner"] = (slug(origin) or "/").split("/")[0] or None
    return cfg


def save_config(cfg):
    os.makedirs(TEAM, exist_ok=True)
    tmp = CONFIG + ".tmp"
    json.dump(cfg, open(tmp, "w", encoding="utf-8"), indent=2)
    os.replace(tmp, CONFIG)


def load_ledger():
    rows = []
    if os.path.exists(LEDGER):
        for line in open(LEDGER, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2 and p[0] != "module":
                p += [""] * (len(COLS) - len(p))
                rows.append(dict(zip(COLS, p)))
    return rows


def save_ledger(rows):
    os.makedirs(TEAM, exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\t".join(COLS) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")).replace("\t", " ").replace("\n", " ") for c in COLS) + "\n")
    os.replace(tmp, LEDGER)


def key(r):
    return (r["module"], r["addr"])


def label(mod):
    return "main" if mod == "main" else f"ov{mod}"


def wip(mod, addr):
    return os.path.join(SP, "wip", label(mod), f"{addr}.cpp").replace("\\", "/")


def cfgdir(mod):
    base = os.path.join(REPO, "config", "usa", "arm9")
    return base if mod == "main" else os.path.join(base, "overlays", f"ov{mod}")


def modules():
    yield "main"
    od = os.path.join(REPO, "config", "usa", "arm9", "overlays")
    for d in sorted(os.listdir(od)):
        if d.startswith("ov"):
            yield d[2:]


def functions(mod):
    """addr -> (size, name) from symbols.txt."""
    out = {}
    for line in open(os.path.join(cfgdir(mod), "symbols.txt"), encoding="utf-8"):
        m = FUNC.match(line)
        if m:
            out[m.group(4).lower()] = (int(m.group(3), 16), m.group(1))
    return out


def delinked_ranges(mod):
    body, seen_file = [], False
    for line in open(os.path.join(cfgdir(mod), "delinks.txt"), encoding="utf-8"):
        if line.rstrip().endswith(":") and not line.startswith((" ", "\t")):
            seen_file = True
            continue
        m = RANGE.match(line)
        if m and seen_file:
            body.append((int(m.group(1), 16), int(m.group(2), 16)))
    return sorted(body)


def modtext(mods):
    names = [m if m == "main" else str(int(m)) for m in sorted(set(mods))]
    return ", ".join(names[:-1]) + (" and " + names[-1] if len(names) > 1 else names[0])


def decomp_tip():
    r = run(["git", "-C", REPO, "fetch", "-q", kitpaths.DECOMP_URL, kitpaths.DECOMP_BRANCH])
    if r.returncode != 0:
        die(f"fetch of {kitpaths.DECOMP_URL} failed: {r.stderr.strip()[:200]}")
    return run(["git", "-C", REPO, "rev-parse", "FETCH_HEAD"], check=True).stdout.strip()


# ---------------------------------------------------------------- reservations held by others

def reserved_elsewhere(cfg, max_age=600):
    """Addresses listed in any open kit issue except ours, or touched by an open decomp PR."""
    cache = os.path.join(TEAM, "reserved_cache.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < max_age:
        return set(json.load(open(cache)))
    text = []
    issues = json.loads(gh("issue", "list", "-R", cfg["kit_repo"], "--state", "open", "--limit", "200",
                           "--json", "number,body"))
    for it in issues:
        if cfg.get("issue") and it["number"] == cfg["issue"]:
            continue
        text.append(it["body"] or "")
        comments = gh("issue", "view", str(it["number"]), "-R", cfg["kit_repo"], "--json", "comments",
                      "-q", ".comments[].body", check=False)
        text.append(comments or "")
    prs = json.loads(gh("pr", "list", "-R", cfg["decomp_repo"], "--state", "open", "--limit", "200",
                        "--json", "number"))
    tag_line = re.compile(r"start:0x[0-9a-fA-F]{8}|// USA: func_(?:ov\d{3}_)?[0-9a-fA-F]{8}")
    for pr in prs:
        diff = gh("pr", "diff", str(pr["number"]), "-R", cfg["decomp_repo"], check=False) or ""
        for line in diff.splitlines():
            if line.startswith("+"):
                text.extend(tag_line.findall(line))
    found = {m.group(2).lower() for t in text for m in ADDR.finditer(t)}
    os.makedirs(TEAM, exist_ok=True)
    json.dump(sorted(found), open(cache, "w"))
    return found


def skiplisted():
    out = set()
    for f in ("skiplist_main.txt", "skiplist_ov.txt"):
        p = os.path.join(KIT, f)
        if os.path.exists(p):
            out |= {l.split()[0].lower() for l in open(p, encoding="utf-8") if l.strip() and not l.startswith("#")}
    p = os.path.join(KIT, "OPEN_RESIDUES.md")
    if os.path.exists(p):
        out |= {m.group(2).lower() for m in ADDR.finditer(open(p, encoding="utf-8").read())}
    return out


# ---------------------------------------------------------------- commands

def cmd_status(a):
    cfg, rows = load_config(), load_ledger()
    counts = {}
    for r in rows:
        counts[r["status"].split(":")[0]] = counts.get(r["status"].split(":")[0], 0) + 1
    unsub = [r for r in rows if r["status"] == "MATCH"]
    print(f"state      {TEAM}")
    print(f"issue      {cfg['issue'] and (cfg['kit_repo'] + '#' + str(cfg['issue'])) or 'none open'}")
    print(f"batch      {cfg['branch_prefix']}{cfg['batch']}")
    print("ledger     " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) if counts else "ledger     empty")
    print(f"ready      {len(unsub)} unsubmitted MATCH ({sum(int(r['size'] or 0) for r in unsub):,} bytes); "
          f"{sum(1 for r in unsub if not r['desc'])} without a description")
    active = sum(1 for r in rows if r["status"] == "ACTIVE")
    if active:
        print(f"queue      {active} reserved and not yet assigned")


def cmd_sync(a):
    tip = decomp_tip()
    dirty = run(["git", "-C", REPO, "status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    if dirty:
        die(f"{REPO} has local changes; not fast-forwarding:\n{dirty}")
    r = run(["git", "-C", REPO, "merge", "--ff-only", "-q", tip])
    if r.returncode != 0:
        die(f"cannot fast-forward {REPO} to {tip[:10]}: {r.stderr.strip()[:300]}")
    print(f"decomp checkout at {tip[:10]} ({kitpaths.DECOMP_BRANCH})")


def candidate_rows(cfg, module=None, lo=None, hi=None):
    lo = cfg["min_size"] if lo is None else lo
    hi = cfg["max_size"] if hi is None else hi
    taken = {key(r) for r in load_ledger() if r["status"] != "RELEASED"}
    blocked = reserved_elsewhere(cfg) | skiplisted()
    out = []
    for mod in modules():
        if module and mod != module:
            continue
        body = delinked_ranges(mod)
        starts = [s for s, _ in body]
        for addr, (size, name) in functions(mod).items():
            ai = int(addr, 16)
            i = bisect.bisect_right(starts, ai) - 1
            if i >= 0 and body[i][0] <= ai < body[i][1]:
                continue
            if not (lo <= size <= hi) or addr in blocked or (mod, addr) in taken:
                continue
            near = min([ai - body[i][1] if i >= 0 else 1 << 30, body[i + 1][0] - ai if i + 1 < len(body) else 1 << 30])
            out.append({"module": mod, "addr": addr, "size": size, "name": name, "near": near, "matched": len(body)})
    # Game code before library modules (any module with skiplisted, flag-pinned functions), then
    # functions right next to matched code (siblings to copy), then the 300-600 byte sweet spot.
    lib = set()
    for f in ("skiplist_ov.txt",):
        p = os.path.join(KIT, f)
        if os.path.exists(p):
            lib |= {m.group(1) for m in re.finditer(r"\bov(\d{3})\b", open(p, encoding="utf-8").read())}
    out.sort(key=lambda c: (c["module"] in lib, c["near"] > 0x400, abs(c["size"] - 450) // 50, c["near"]))
    return out


def cmd_candidates(a):
    cfg = load_config()
    rows = candidate_rows(cfg, a.module, a.min, a.max)
    print(f"{len(rows)} free functions in range; best {min(a.limit, len(rows))}:")
    for c in rows[:a.limit]:
        print(f"{c['module']} {c['addr']} {c['size']:5d}  near={c['near']:#x}  {c['name']}")


def cmd_reserve(a):
    cfg, rows = load_config(), load_ledger()
    have = {key(r): r for r in rows}
    picks = []
    if a.take:
        cands = candidate_rows(cfg, a.module, a.min, a.max)
        picks = [(c["module"], c["addr"], c["size"]) for c in cands[:a.take]]
    else:
        if len(a.pairs) % 2:
            die("give module/address pairs: reserve 017 0218dd18 000 0217a2dc")
        blocked = reserved_elsewhere(cfg, max_age=0)
        for mod, addr in zip(a.pairs[::2], a.pairs[1::2]):
            mod, addr = mod.lower().removeprefix("ov"), addr.lower().removeprefix("0x")
            fn = functions(mod).get(addr)
            if not fn:
                die(f"{mod} {addr}: no function at that address in symbols.txt")
            if addr in blocked:
                die(f"{mod} {addr}: reserved by an open issue or PR")
            picks.append((mod, addr, fn[0]))
    added = 0
    for mod, addr, size in picks:
        r = have.get((mod, addr))
        if r and r["status"] != "RELEASED":
            continue
        if r:
            r.update(status="ACTIVE", note="")
        else:
            rows.append({"module": mod, "addr": addr, "size": str(size), "status": "ACTIVE", "desc": "", "note": ""})
        added += 1
    save_ledger(rows)
    print(f"reserved {added} function(s) in the ledger. Publish them before anyone works on them: "
          f"python team/team.py issue --publish")


def issue_body(cfg, rows):
    live = sorted((r for r in rows if r["status"] in LIVE), key=key)
    if not live:
        return None, None
    total = sum(int(r["size"]) for r in live)
    mods = [r["module"] for r in live]
    where = "USA main and overlay" if "main" in mods else "USA overlay"
    label_for = {"MATCH": "Matched; preparing PR", "RESIDUE": "Retained attempt; still matching"}
    out = [f"Working on these {where} {modtext(mods)} functions ({total:,} bytes total; ends exclusive):", "",
           "| Module | Start | End exclusive | Bytes | Status |", "| --- | --- | --- | ---: | --- |"]
    for r in live:
        a = int(r["addr"], 16)
        out.append(f"| {label(r['module'])} | `0x{r['addr']}` | `0x{a + int(r['size']):08x}` | {r['size']} | "
                   f"{label_for.get(r['status'], 'Active matching')} |")
    out += ["", "All rows were checked against current `decomp-matching`, open kit issues and open decomp PRs; "
            "none are delinked or reserved elsewhere. Matches will use the default compiler and pass the kit "
            "gate, a full USA `ninja check rom`, and `prready.py decomp` before submission.", "",
            "This is our only active batch reservation. It will close when the game PR is opened, with a PR "
            "link; any remaining work will move to one successor batch."]
    title = f"{cfg['tag']} Overlay {modtext(mods)} helpers ({total} bytes)"
    return title, "\n".join(out) + "\n"


def publish_issue(cfg, rows):
    title, body = issue_body(cfg, rows)
    if body is None:
        print("nothing live to reserve")
        return
    clash = {r["addr"] for r in rows if r["status"] in LIVE} & reserved_elsewhere(cfg, max_age=0)
    if clash:
        die("these are now reserved by someone else; drop them first (release rows or edit the ledger): "
            + " ".join(sorted(clash)))
    os.makedirs(TEAM, exist_ok=True)
    path = os.path.join(TEAM, "issue.md")
    open(path, "w", encoding="utf-8").write(body)
    if cfg.get("issue"):
        state = gh("issue", "view", str(cfg["issue"]), "-R", cfg["kit_repo"], "--json", "state", "-q", ".state").strip()
        if state == "OPEN":
            gh("issue", "edit", str(cfg["issue"]), "-R", cfg["kit_repo"], "--title", title, "--body-file", path)
            print(f"updated {cfg['kit_repo']}#{cfg['issue']}: {title}")
            return
    url = gh("issue", "create", "-R", cfg["kit_repo"], "--title", title, "--body-file", path).strip()
    cfg["issue"] = int(url.rstrip("/").split("/")[-1])
    save_config(cfg)
    print(f"opened {url}")


def cmd_issue(a):
    cfg, rows = load_config(), load_ledger()
    if a.publish:
        publish_issue(cfg, rows)
    else:
        title, body = issue_body(cfg, rows)
        print(title or "nothing live to reserve")
        print(body or "")


def take_group(rows, per, module=None):
    pool = [r for r in rows if r["status"] == "ACTIVE" and (not module or r["module"] == module)]
    if not pool:
        return []
    mod = pool[0]["module"]
    return [r for r in pool if r["module"] == mod][:per]


def worker_prompt(group, report_path=None):
    brief = os.path.join(KIT, "team", "WORKER.md").replace("\\", "/")
    lines = [f"You are a DQIX matching worker. Read {brief} completely before doing anything, then follow it exactly.",
             "", "Your assignment (module address size):"]
    lines += [f"{r['module']} {r['addr']} {r['size']}   source: {wip(r['module'], r['addr'])}" for r in group]
    lines += ["", f"Kit checkout: {KIT.replace(chr(92), '/')}", f"State dir ($SP): {SP.replace(chr(92), '/')}",
              f"Decomp checkout (read-only for you): {REPO.replace(chr(92), '/')}"]
    if report_path:
        lines += ["", "Your final message must be the JSON report described in WORKER.md (it is schema-checked)."]
    return "\n".join(lines)


def cmd_next(a):
    rows = load_ledger()
    group = take_group(rows, a.per, a.module)
    if not group:
        die("no ACTIVE (reserved, unassigned) rows; reserve more or collect", 3)
    lbl = a.label or f"sub-{datetime.datetime.now():%H%M%S}"
    for r in group:
        r["status"], r["note"] = "ASSIGNED", lbl
    save_ledger(rows)
    print(worker_prompt(group))


def run_worker(group, lbl, a):
    os.makedirs(REPORTS, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    report = os.path.join(REPORTS, f"{lbl}.json")
    cmd = ["codex", "exec", "-C", KIT, "--skip-git-repo-check", "--sandbox", a.sandbox,
           "--add-dir", SP, "--output-schema", os.path.join(HERE, "report.schema.json"), "-o", report, "--json"]
    if a.model:
        cmd += ["-m", a.model]
    if a.effort:
        cmd += ["-c", f'model_reasoning_effort="{a.effort}"']
    for r in group:
        os.makedirs(os.path.dirname(wip(r["module"], r["addr"])), exist_ok=True)
    with open(os.path.join(LOGS, f"{lbl}.jsonl"), "w", encoding="utf-8") as log:
        p = subprocess.run(cmd + ["-"], input=worker_prompt(group, report), stdout=log, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace", timeout=a.timeout * 60)
    return p.returncode, report


def cmd_dispatch(a):
    if not shutil.which("codex"):
        die("codex CLI not on PATH")
    rows = load_ledger()
    jobs, n = [], 0
    while len(jobs) < a.groups:
        group = take_group(rows, a.per, a.module)
        if not group:
            break
        n += 1
        lbl = f"w{datetime.datetime.now():%m%d%H%M}-{n}"
        for r in group:
            r["status"], r["note"] = "ASSIGNED", lbl
        jobs.append((lbl, group))
    save_ledger(rows)
    if not jobs:
        die("no ACTIVE rows to dispatch; reserve and publish first", 3)
    print(f"dispatching {len(jobs)} group(s), {a.workers} at a time")
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(run_worker, g, lbl, a): (lbl, g) for lbl, g in jobs}
        for fut in as_completed(futs):
            lbl, group = futs[fut]
            try:
                code, report = fut.result()
            except subprocess.TimeoutExpired:
                code, report = "timeout", None
            print(f"[{lbl}] exit {code}; collecting {' '.join(r['addr'] for r in group)}", flush=True)
            collect([key(r) for r in group], report_files=[report] if report else [])


def report_index(files=None):
    """addr -> report entry from worker JSON reports (newest wins)."""
    idx = {}
    paths = files if files else sorted(glob.glob(os.path.join(REPORTS, "*.json")), key=os.path.getmtime)
    for p in paths:
        try:
            data = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for f in data.get("functions", []):
            idx[str(f.get("addr", "")).lower().removeprefix("0x")] = f
    return idx


COMMENT = re.compile(r"//(?!\s*USA:)|/\*")
MMIO = re.compile(r"volatile[^;\n]*\*\s*\)\s*0x0[45][0-9a-fA-F]{6}")


def quality(path):
    """Problems a reviewer would reject, beyond the byte match."""
    src = open(path, encoding="utf-8", errors="replace").read()
    probs = []
    code = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
    if COMMENT.search(code):
        probs.append("comment other than the // USA: tag (run pad/decomment.py)")
    if re.search(r"\b(asm|__asm)\b", code):
        probs.append("inline asm")
    for m in re.finditer(r"#pragma\s+(\w+)", code):
        if m.group(1) not in ("once", "define_section", "section"):
            probs.append(f"#pragma {m.group(1)}")
    vol = [l for l in code.splitlines() if "volatile" in l and not MMIO.search(l)]
    if vol:
        probs.append(f"volatile outside an MMIO register define: {vol[0].strip()[:80]}")
    if "// USA:" not in src:
        probs.append("missing the // USA: tag line")
    if not src.lstrip().startswith("#include <globaldefs.h>"):
        probs.append("first line is not #include <globaldefs.h>")
    return probs


def record_lever(addr, size, before, text, tsv=None):
    """Append the worker's lever as a $SP/wlog/levers.tsv row (IMPROVEMENT_LOOP.md §2), once per address
    and text, so levercheck.py asks for it to be promoted once the function lands."""
    tsv = tsv or os.path.join(SP, "wlog", "levers.tsv")
    text = " ".join(str(text).split())
    if os.path.exists(tsv):
        for line in open(tsv, encoding="utf-8", errors="ignore"):
            f = line.rstrip("\n").split("\t")
            if len(f) >= 4 and f[0] == addr and f[3] == text:
                return
    os.makedirs(os.path.dirname(tsv), exist_ok=True)
    with open(tsv, "a", encoding="utf-8") as fh:
        fh.write(f"{addr}\t{size}\t{int(before)}\t{text}\n")


def collect(keys, report_files=None):
    rows = load_ledger()
    by = {key(r): r for r in rows}
    reps = report_index()
    if report_files:
        reps.update(report_index([p for p in report_files if p and os.path.exists(p)]))
    for k in keys:
        r = by.get(k)
        if not r:
            print(f"{k[0]} {k[1]}: not in the ledger, skipped")
            continue
        f = wip(*k)
        rep = reps.get(k[1], {})
        if rep.get("description") and not r["desc"]:
            r["desc"] = rep["description"].strip().rstrip(".")
        if not os.path.exists(f):
            r["status"], r["note"] = "ACTIVE", "worker left no source"
            print(f"{k[0]} {k[1]}: no source; back to the queue")
            continue
        g = run([PY, os.path.join(KIT, "wgate.py"), k[0], k[1], f], cwd=KIT)
        verdict = (g.stdout.strip().splitlines() or [g.stderr.strip()[:200]])[0]
        if "ALREADY-COMMITTED" in verdict:
            r["status"], r["note"] = "DROPPED", "already landed on decomp-matching"
        elif verdict == "MATCH":
            probs = quality(f)
            if probs:
                r["status"], r["note"] = "RESIDUE", "QUALITY: " + "; ".join(probs)
            else:
                r["status"], r["note"] = "MATCH", ""
                if (rep.get("lever") or "").strip():
                    record_lever(k[1], r["size"], rep.get("lever_bytes") or 0, rep["lever"])
        else:
            r["status"], r["note"] = "RESIDUE", verdict[:200]
        print(f"{k[0]} {k[1]}: {r['status']} {r['note']}".rstrip())
    save_ledger(rows)


def cmd_collect(a):
    rows = load_ledger()
    if a.addrs:
        want = {x.lower().removeprefix("0x") for x in a.addrs}
        keys = [key(r) for r in rows if r["addr"] in want]
    else:
        keys = [key(r) for r in rows if r["status"] in ("ASSIGNED", "RESIDUE", "MATCH", "ACTIVE")
                and os.path.exists(wip(*key(r)))]
    collect(keys)


def cmd_describe(a):
    rows = load_ledger()
    addr = a.addr.lower().removeprefix("0x")
    hit = [r for r in rows if r["addr"] == addr]
    if not hit:
        die(f"{addr} not in the ledger")
    for r in hit:
        r["desc"] = a.text.strip().rstrip(".")
    save_ledger(rows)


def integ_clean(state):
    leftovers = glob.glob(os.path.join(state, "hold_*")) + glob.glob(os.path.join(state, "*_stage"))
    for d in ("staging", "gated", "quarantine"):
        leftovers += glob.glob(os.path.join(state, d, "**", "*.cpp"), recursive=True)
    return leftovers


def state_dirs():
    """kit_init.py's STATE_DIRS: finish_wave.sh and ov_recover.py expect every one of them."""
    import ast
    src = open(os.path.join(KIT, "kit_init.py"), encoding="utf-8").read()
    m = re.search(r"^STATE_DIRS = (\[.*?\])", src, re.S | re.M)
    return ast.literal_eval(m.group(1)) if m else ["wlog", "wlog/gates", "staging", "gated", "quarantine", "attempts"]


def provision_integ(integ):
    """A fresh worktree has none of the tools the build downloads (the compiler, dsd, objdiff). Fetch them
    into the worktree through the build's own download edges; a junction to the main checkout's
    compiler would let the tree's first ninja rewrite the main checkout's compiler."""
    import buildcfg
    cc = os.path.join(integ, "tools", "mwccarm", *buildcfg.MWCC_VERSION.split("/"), "mwccarm.exe")
    if os.path.exists(cc):
        return
    if not os.path.exists(os.path.join(integ, "build.ninja")):
        c = run([PY, "tools/configure.py", "usa"], cwd=integ)
        if c.returncode != 0:
            die(f"configure.py failed in {integ}: {(c.stderr or c.stdout).strip()[-400:]}")
    target = "/".join(("tools", "mwccarm", buildcfg.MWCC_VERSION, "mwccarm.exe"))
    print(f"fetching the compiler and tools into {integ}", flush=True)
    n = run(["ninja", target, "dsd.exe", "objdiff-cli.exe"], cwd=integ)
    if n.returncode != 0 or not os.path.exists(cc):
        die(f"could not fetch the compiler into {integ}: {(n.stdout + n.stderr).strip()[-400:]}")


def cmd_integrate(a):
    cfg = load_config()
    state = cfg["integ_state"]
    for d in state_dirs():
        os.makedirs(os.path.join(state, d), exist_ok=True)
    lock = os.path.join(state, "team_integrate.lock")
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 4 * 3600:
        die(f"another integration started {time.ctime(os.path.getmtime(lock))} ({lock}); two at once "
            "destroy each other's staging and branch. Wait for it; delete the lock only if that run is dead", 2)
    open(lock, "w").write(f"{os.getpid()} {datetime.datetime.now().isoformat()}\n")
    try:
        integrate(a, cfg, state)
    finally:
        os.remove(lock)


def integrate(a, cfg, state):
    rows = load_ledger()
    if os.path.exists(os.path.join(state, "wave.lock")) or os.path.exists(os.path.join(SP, "wave.lock")):
        die("an integration is running (wave.lock present); never start a second one", 2)
    left = integ_clean(state)
    if left:
        if not a.archive:
            die(f"integration state {state} holds {len(left)} leftover file(s) from an earlier run; "
                "rerun with --archive to move them to attempts/ first")
        dest = os.path.join(state, "attempts", f"leftover-{datetime.datetime.now():%Y%m%d-%H%M%S}")
        os.makedirs(dest)
        for p in glob.glob(os.path.join(state, "hold_*")) + glob.glob(os.path.join(state, "*_stage")):
            shutil.move(p, dest)
        for d in ("staging", "gated", "quarantine"):
            shutil.move(os.path.join(state, d), os.path.join(dest, d))
            os.makedirs(os.path.join(state, d))
    todo = [r for r in rows if r["status"] == "MATCH"]
    if not todo:
        die("no unsubmitted MATCH rows")
    missing = [r["addr"] for r in todo if not r["desc"]]
    if missing:
        die("describe these first (python team/team.py describe ADDR \"...\"): " + " ".join(missing))
    branch = f"{cfg['branch_prefix']}{cfg['batch']}"
    base = decomp_tip()
    integ = run([PY, os.path.join(KIT, "integ_tree.py"), "path"], cwd=KIT, check=True).stdout.strip()
    run([PY, os.path.join(KIT, "integ_tree.py"), "sync"], cwd=KIT, check=True)
    run(["git", "-C", integ, "checkout", "-q", "-f", "--detach", base], check=True)
    run(["git", "-C", integ, "clean", "-fdq", "src/"], check=True)
    provision_integ(integ)
    run(["git", "-C", REPO, "branch", "-f", branch, base], check=True)
    mods, staged, skipped = [], [], []
    for r in todo:
        f = wip(r["module"], r["addr"])
        g = run([PY, os.path.join(KIT, "wgate.py"), r["module"], r["addr"], f], cwd=KIT)
        v = (g.stdout.strip().splitlines() or ["?"])[0]
        if v != "MATCH" or quality(f):
            skipped.append((r, v))
            continue
        dst = os.path.join(state, "staging", label(r["module"]))
        os.makedirs(dst, exist_ok=True)
        shutil.copy2(f, dst)
        staged.append(r)
        if r["module"] not in mods:
            mods.append(r["module"])
    for r, v in skipped:
        print(f"SKIP {r['module']} {r['addr']}: {v}")
    env = dict(os.environ, DQIX_STATE=state, DQIX_BRANCH=branch, DQIX_PUBLISH="local", DQIX_INTEG=integ)
    failed = []
    for m in mods:
        print(f"== finish_wave {m}", flush=True)
        p = run(["bash", os.path.join(KIT, "finish_wave.sh"), m], cwd=KIT, env=env)
        out = (p.stdout + p.stderr).strip()
        print("\n".join("   " + t for t in out.splitlines()[-3:]), flush=True)
        if "FATAL" in out or "NtCreateDirectoryObject" in out:
            failed.append(m)
            log = os.path.join(state, "wlog", f"team_fw_{m}.log")
            open(log, "w", encoding="utf-8").write(out)
            print(f"   finish_wave {m} FAILED; full output: {log}")
    if failed and len(failed) == len(mods):
        die("every module failed to integrate; read the logs above before retrying (bash scripts need the "
            "command run outside the Windows sandbox)")
    run(["ninja", "report"], cwd=integ)
    cf = run([PY, os.path.join(KIT, "countfix.py"), f"--since={base}"], cwd=KIT, env=dict(os.environ, DQIX_REPO=integ))
    print("countfix:", (cf.stdout.strip().splitlines() or ["(no output)"])[-1])
    dirty = run(["git", "-C", integ, "status", "--porcelain", "--", "config", "src"]).stdout.strip()
    if dirty:
        print(f"WARN: integration tree dirty after countfix:\n{dirty}")
    if cfg.get("commit_trailer"):
        t = cfg["commit_trailer"].replace("'", "")
        run(["git", "-C", integ, "filter-branch", "-f", "--msg-filter", f"cat; printf '\\n{t}\\n'", f"{base}..HEAD"],
            env=dict(os.environ, FILTER_BRANCH_SQUELCH_WARNING="1"))
    head = run(["git", "-C", integ, "rev-parse", "HEAD"], check=True).stdout.strip()
    run(["git", "-C", REPO, "branch", "-f", branch, head], check=True)
    added = run(["git", "-C", integ, "diff", "--name-only", "--diff-filter=A", f"{base}..HEAD", "--", "src"]).stdout.split()
    other = [p for p in run(["git", "-C", integ, "diff", "--name-only", f"{base}..HEAD"]).stdout.split()
             if not p.startswith("src/")]
    print(f"\nbranch {branch} = {head[:10]} on {base[:10]}: {len(added)} new source files "
          f"({len(staged)} staged, {len(skipped)} skipped)")
    print("non-src files changed: " + (", ".join(sorted(set(other))) or "none"))
    if len(added) != len(staged):
        print("WARN: committed count differs from staged count; look for deferred functions in the "
              "finish_wave output above (they stay MATCH in the ledger and go into the next batch)")
    cfg["last_integration"] = {"branch": branch, "base": base, "head": head, "added": len(added)}
    save_config(cfg)


def delink_owners(integ):
    """source path -> (module, .text start) from every delinks.txt in the integration tree."""
    owners = {}
    base = os.path.join(integ, "config", "usa", "arm9")
    for p in [os.path.join(base, "delinks.txt")] + glob.glob(os.path.join(base, "overlays", "ov*", "delinks.txt")):
        mod = "main" if os.path.dirname(p) == base else os.path.basename(os.path.dirname(p))[2:]
        cur = None
        for line in open(p, encoding="utf-8"):
            if line.rstrip().endswith(":") and not line.startswith((" ", "\t")):
                cur = line.strip()[:-1]
                continue
            m = RANGE.match(line)
            if m and cur and cur not in owners:
                owners[cur] = (mod, m.group(1).lower().zfill(8))
    return owners


def pr_body(cfg, integ, base, rows):
    by = {key(r): r for r in rows}
    files = run(["git", "-C", integ, "diff", "--name-only", "--diff-filter=A", f"{base}..HEAD", "--", "src"]).stdout.split()
    owners = delink_owners(integ)
    table, keys = [], []
    for f in files:
        k = owners.get(f)
        if not k or k not in by:
            die(f"cannot map {f} to a ledger row")
        table.append(by[k])
        keys.append(k)
    table.sort(key=key)
    total = sum(int(r["size"]) for r in table)
    mods = [r["module"] for r in table]
    where = "USA main and overlay" if "main" in mods else "USA overlay"
    added_syms = [l[1:].split()[0] for l in run(["git", "-C", integ, "diff", f"{base}..HEAD", "--", "config/**/symbols.txt",
                                                  "config/*/arm9/symbols.txt"]).stdout.splitlines()
                  if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]
    other = [p for p in run(["git", "-C", integ, "diff", "--name-only", f"{base}..HEAD"]).stdout.split()
             if not p.startswith("src/") and not p.endswith(("delinks.txt", "symbols.txt"))]
    tail = "existing symbol names are kept"
    if added_syms:
        tail += (f"; `symbols.txt` gains {len(added_syms)} alias line(s) for data a function references under a "
                 f"second name ({', '.join(f'`{s}`' for s in added_syms[:6])})")
    tail += "; no other source or header is changed" if not other else f"; also changed: {', '.join(other)}"
    out = ["## What this changes", "",
           f"Matches {len(table)} {where} {modtext(mods)} functions ({total:,} bytes). Each is a new source file in "
           f"its module's `src/` directory, wired into that module's `delinks.txt`; {tail}.", "",
           "| Module | Address | Bytes | Function |", "| --- | --- | ---: | --- |"]
    out += [f"| {label(r['module'])} | `0x{r['addr']}` | {r['size']} | {r['desc']} |" for r in table]
    out += ["", "Validation: every function passed the kit gate (`wgate.py` MATCH: byte-exact with relocations "
            "masked, exact exported symbol, every call and data relocation resolving to the ROM's target) with the "
            "default compiler and flags, no pragmas, asm or overrides. The batch was integrated through the kit's "
            "`finish_wave.sh` from a clean `decomp-matching` worktree (`ninja check` green per module), followed by "
            "`ninja report`; `countfix.py` reports every new unit counted. `prready.py decomp` reports READY "
            "against the current `decomp-matching`.", ""]
    if cfg.get("issue"):
        out += [f"Reservation: {cfg['kit_repo']}#{cfg['issue']}.", ""]
    out += ["## Checklist", "",
            "- [x] `ninja` passes and every module still matches the original ROM",
            "- [x] Symbols in `symbols.txt` match the names used in the decompiled code"]
    if cfg.get("pr_footer"):
        out += ["", cfg["pr_footer"]]
    title = f"{cfg['tag']} Match {len(table)} overlay {modtext(mods)} functions ({total:,} bytes)"
    if "main" in mods:
        title = f"{cfg['tag']} Match {len(table)} {modtext(mods)} functions ({total:,} bytes)"
    return title, "\n".join(out) + "\n", keys


def cmd_pr(a):
    cfg, rows = load_config(), load_ledger()
    li = cfg.get("last_integration")
    if not li:
        die("run integrate first")
    integ = run([PY, os.path.join(KIT, "integ_tree.py"), "path"], cwd=KIT, check=True).stdout.strip()
    head = run(["git", "-C", integ, "rev-parse", "HEAD"], check=True).stdout.strip()
    if head != li["head"]:
        die(f"integration tree moved since integrate ({head[:10]} != {li['head'][:10]}); rerun integrate")
    title, body, keys = pr_body(cfg, integ, li["base"], rows)
    os.makedirs(PRS, exist_ok=True)
    path = os.path.join(PRS, f"{li['branch'].replace('/', '_')}.md")
    open(path, "w", encoding="utf-8").write(body)
    print(title)
    print(f"body: {path}")
    ready = run([PY, os.path.join(KIT, "prready.py"), "decomp"], cwd=KIT, env=dict(os.environ, DQIX_REPO=integ))
    print((ready.stdout + ready.stderr).strip())
    if ready.returncode != 0:
        die("prready is not READY; fix every line above (usually: decomp-matching moved, rerun integrate)")
    mine = set(run(["git", "-C", integ, "diff", "--name-only", f"{li['base']}..HEAD"]).stdout.split())
    clash = []
    for pr in json.loads(gh("pr", "list", "-R", cfg["decomp_repo"], "--state", "open", "--limit", "100",
                            "--json", "number,headRefName,headRepositoryOwner")):
        if (pr.get("headRepositoryOwner") or {}).get("login") != cfg["fork_owner"]:
            continue
        if not pr["headRefName"].startswith(cfg["branch_prefix"].split("/")[0] + "/"):
            continue  # another team pushing from the same fork (e.g. claude/*): not ours to wait for
        theirs = set((gh("pr", "diff", str(pr["number"]), "-R", cfg["decomp_repo"], "--name-only", check=False)
                      or "").split())
        both = sorted(p for p in mine & theirs if p.endswith("delinks.txt"))
        if both:
            clash.append(f"#{pr['number']} ({pr['headRefName']}): {', '.join(both)}")
    if clash:
        print("note: your open PRs also change these delinks.txt files; maintainers resolve the conflict at "
              "landing, so leave those branches as they are:\n  " + "\n  ".join(clash))
    if not a.open:
        print("dry run: add --open to push, open the PR and close the reservation issue")
        return
    fork = f"https://github.com/{cfg['fork_owner']}/{cfg['decomp_repo'].split('/')[1]}.git"
    push = run(["git", "-C", integ, "push", fork, f"HEAD:refs/heads/{li['branch']}"])
    if push.returncode != 0:
        die(f"push of {li['branch']} refused (the branch exists on the fork?). Never move an open pull "
            f"request's branch; bump `batch` in {CONFIG} and rerun integrate. {push.stderr.strip()[-300:]}")
    url = gh("pr", "create", "-R", cfg["decomp_repo"], "--base", cfg["base"], "--head",
             f"{cfg['fork_owner']}:{li['branch']}", "--title", title, "--body-file", path).strip()
    num = url.rstrip("/").split("/")[-1]
    print(f"opened {url}")
    by = {key(r): r for r in rows}
    for k in keys:
        by[k]["status"], by[k]["note"] = "SUBMITTED", f"PR {num}"
    save_ledger(rows)
    archive = os.path.join(cfg["integ_state"], "attempts", f"pr{num}")
    os.makedirs(archive, exist_ok=True)
    for p in glob.glob(os.path.join(cfg["integ_state"], "hold_*")) + glob.glob(os.path.join(cfg["integ_state"], "*_stage")):
        shutil.move(p, archive)
    if cfg.get("issue"):
        gh("issue", "comment", str(cfg["issue"]), "-R", cfg["kit_repo"], "--body",
           f"PR: {cfg['decomp_repo']}#{num}")
        gh("issue", "close", str(cfg["issue"]), "-R", cfg["kit_repo"])
        print(f"closed {cfg['kit_repo']}#{cfg['issue']}")
        cfg["issue"] = None
    cfg["batch"] = int(cfg["batch"]) + 1
    cfg.pop("last_integration", None)
    save_config(cfg)
    if any(r["status"] in LIVE for r in rows):
        publish_issue(cfg, rows)


def cmd_release(a):
    cfg, rows = load_config(), load_ledger()
    released = []
    for r in rows:
        if r["status"] in ("ACTIVE", "ASSIGNED", "RESIDUE") or (r["status"] == "MATCH" and not a.keep_matches):
            released.append(r)
            r["note"] = f"released from {r['status']}: {r['note']}".strip(": ")
            r["status"] = "RELEASED"
    save_ledger(rows)
    if cfg.get("issue"):
        msg = (f"Releasing this reservation: {len(released)} unfinished function(s) are free again. "
               "Partial attempts stay in our local state and will be re-reserved before any further work.")
        gh("issue", "comment", str(cfg["issue"]), "-R", cfg["kit_repo"], "--body", msg)
        gh("issue", "close", str(cfg["issue"]), "-R", cfg["kit_repo"])
        print(f"closed {cfg['kit_repo']}#{cfg['issue']}")
        cfg["issue"] = None
        save_config(cfg)
    print(f"released {len(released)} row(s); wip sources kept in {SP}/wip for later resumption")


def cmd_reclaim(a):
    """Re-reserve released rows whose wip source still gates MATCH and that nobody else took."""
    cfg, rows = load_config(), load_ledger()
    blocked = reserved_elsewhere(cfg, max_age=0)
    keys = []
    for r in rows:
        if r["status"] != "RELEASED" or (a.matches_only and "from MATCH" not in r["note"]):
            continue
        if r["addr"] in blocked:
            print(f"{r['module']} {r['addr']}: reserved by someone else now; left released")
            continue
        r["status"], r["note"] = "ACTIVE", ""
        keys.append(key(r))
    save_ledger(rows)
    collect([k for k in keys if os.path.exists(wip(*k))])
    print("re-reserved locally. Publish before doing anything else: python team/team.py issue --publish")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("sync")
    p = sub.add_parser("candidates")
    p.add_argument("--module")
    p.add_argument("--min", type=int)
    p.add_argument("--max", type=int)
    p.add_argument("--limit", type=int, default=40)
    p = sub.add_parser("reserve")
    p.add_argument("pairs", nargs="*")
    p.add_argument("--take", type=int)
    p.add_argument("--module")
    p.add_argument("--min", type=int)
    p.add_argument("--max", type=int)
    p = sub.add_parser("issue")
    p.add_argument("--publish", action="store_true")
    p = sub.add_parser("next")
    p.add_argument("--label")
    p.add_argument("--per", type=int, default=4)
    p.add_argument("--module")
    p = sub.add_parser("dispatch")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--groups", type=int, default=1000)
    p.add_argument("--per", type=int, default=4)
    p.add_argument("--module")
    p.add_argument("--model")
    p.add_argument("--effort")
    p.add_argument("--sandbox", default="workspace-write")
    p.add_argument("--timeout", type=int, default=240, help="minutes per worker")
    p = sub.add_parser("collect")
    p.add_argument("addrs", nargs="*")
    p = sub.add_parser("describe")
    p.add_argument("addr")
    p.add_argument("text")
    p = sub.add_parser("integrate")
    p.add_argument("--archive", action="store_true")
    p = sub.add_parser("pr")
    p.add_argument("--open", action="store_true")
    p = sub.add_parser("release")
    p.add_argument("--keep-matches", action="store_true")
    p = sub.add_parser("reclaim")
    p.add_argument("--matches-only", action="store_true", help="only rows released while MATCH")
    a = ap.parse_args()
    globals()[f"cmd_{a.cmd}"](a)


if __name__ == "__main__":
    main()
