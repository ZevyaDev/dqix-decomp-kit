#!/usr/bin/env python
"""Every still-unmatched address that already has a saved attempt to resume from.

    python resumable.py                 -> "<mod> <addr> <bytes|-> <prior>" one per line, best first
    python resumable.py <addr>          -> just the prior file for that address (empty if none)
    python resumable.py --count         -> how many are resumable

The reservoir is the point: re-deriving a function costs ~$4.55 and usually misses, while resuming
its own near-miss cost $1.08 and matched (measured on func_0203af48). A saved attempt is a paid-for
decode with one transformation left, so the parked pools -- not the cold pool -- are the cheapest
work in the project.

WHICH DIRECTORIES COUNT. Only the pools that hold a session's OWN OUTPUT: hold_*, *_stage,
staging/*, *_reclaim, quarantine, attempts. Emphatically NOT scaffold/ (a scaffold is the cold
starting point, so resuming from one is the cold path wearing a resume label), not refs/ (other
projects' decomps), not repair_work/ (repairsweep's scratch copies), and not the SP root, which
holds ~31k loose .cpp files of every kind.

RANKING. Near-misses first, closest byte-diff first, because that is where one transformation is
most likely to close it; then everything else, newest attempt first.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import glob, os, re, sys, collections

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO

POOLS = ["hold_*/*.cpp", "*_stage/*.cpp", "staging/*/*.cpp", "*_reclaim/*.cpp",
         "quarantine/*.cpp", "attempts/*.cpp", "gated/*/*.cpp", "priors/*/*.cpp"]
# A session's final answer beats an intermediate save: attempts/ is swept from staging mid-session,
# so a file still sitting in a stage/hold pool is the later, better artifact. gated/ outranks
# everything: wgate copies a source there ONLY on a MATCH, so those bytes are proven against the
# target -- 801 archived, 112 of them still uncommitted, and no dispatcher had ever read the
# directory. A proven source is the best possible thing to resume from.
RANK_DIR = {"attempts": 1}


def rank_of(f):
    p = f.replace("\\", "/")
    # A `Trans_<addr>.cpp` sitting OUTSIDE gated/ is a literal transliteration: every instruction is
    # translated and the control flow is right, but it colours registers its own way, so it can never
    # gate MATCH. It is reference material, not a candidate -- resuming FROM it would hand a worker a
    # file it must throw away. Rank it below every real prior; resume_one attaches it separately as a
    # reference. (Inside gated/ the same name means translate.py proved it, so that stays best.)
    if "/gated/" in p:
        return -1
    if os.path.basename(p).startswith("Trans_"):
        return 9
    return RANK_DIR.get(os.path.basename(os.path.dirname(p)), 0)

_rng = []          # (start, end, module) over .text, from the delink config
for dl in [f"{REPO}/{buildcfg.config_root()}/delinks.txt"] + sorted(
        glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/ov*/delinks.txt")):
    if not os.path.exists(dl):
        continue
    mod = "main" if dl.endswith("arm9/delinks.txt") else re.search(r'ov(\d+)', dl).group(1)
    for a, b in re.findall(r'(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$', open(dl).read()):
        _rng.append((int(a, 16), int(b, 16), mod))


def matched(addr):
    """True once the address falls inside a delinked .text range -- i.e. it is already committed."""
    x = int(addr, 16)
    return any(s <= x < e for s, e, _m in _rng)


# Module by ADDRESS RANGE, never by symbol name: a matched function is renamed and its func_ symbol
# stops existing. main is checked first and is never ambiguous; overlays can share a load region, so
# an address inside two overlays is reported as ambiguous and skipped rather than gated wrongly.
_main_end = None


def _main_text_end():
    global _main_end
    if _main_end is not None:
        return _main_end
    path = f"{REPO}/{buildcfg.config_root()}/delinks.txt"
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError as e:
        raise SystemExit("cannot read main .text end from %s: %s" % (path, e))
    m = re.search(r"\.text\s+start:0x[0-9a-fA-F]+\s+end:0x([0-9a-fA-F]+)\s+kind:", text)
    if not m:
        raise SystemExit("no .text section end in %s" % path)
    _main_end = int(m.group(1), 16)
    return _main_end


def module_of(addr):
    x = int(addr, 16)
    if x < _main_text_end():
        return "main"
    hits = {m for s, e, m in _rng if s <= x < e and m != "main"}
    return hits.pop() if len(hits) == 1 else ""


# A prior SKIP that names one of these is a dead end that has already been paid for. Re-serving it
# buys the same verdict again: measured 08-20, the four closest-by-bytes candidates were all of this
# kind, and the first one cost $2.27 to be told a second time that the idiom is documented UNSOLVED.
HARD = re.compile(r'no C form|no-C-form|needs (?:hand |raw )?asm|hand-asm|unmatchable|UNSOLVED'
                  r'|colorsweep (?:inert|converged)|colorsweep\+|proven|documented'
                  r'|lever(?:s)? exhausted|exhausted|spent lever|no new lever', re.I)
# How much grinding the residue has already absorbed. Every try recorded here is a lever a resume
# worker would spend its session re-pulling. Workers write the count half a dozen ways.
EFFORT = re.compile(r'(\d+)\s*\+?\s*(?:tries|runs|prior variants|variants|variations'
                    r'|source shapes|shapes|compiles|attempts|probes)', re.I)


def skips():
    """addr -> (best byte distance or None, every reason text ever recorded for it).

    ALL of an address's SKIP lines matter, not the newest one. A worker that gives up on try 9 often
    writes a terser verdict than the one that documented the dead end on try 2, so keeping only the
    last line hides exactly the evidence that should hold the address back.
    """
    seen = collections.defaultdict(list)
    for p in ([f"{SP}/wlog/skips_archive.txt"] + glob.glob(f"{SP}/wlog/*.log")
              + [f"{SP}/wlog/verdicts_live.txt"]):
        try:
            t = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for m in re.finditer(r'^SKIP\s+([0-9a-fA-F]{8})\s+(.+)$', t, re.M):
            seen[m.group(1).lower()].append(m.group(2))
    out = {}
    for a, lines in seen.items():
        uniq = list(dict.fromkeys(lines))
        bs = [b for ln in uniq for b in distances(ln)]
        out[a] = (min(bs) if bs else None, " | ".join(uniq))
    return out


# A SIZE delta and a "vs slot" delta are not diff distances; counting them as one reported an
# address that is 140 bytes out as 4 bytes from matching, which would tell the next worker to skip
# a function it had barely started.
NOISE = re.compile(r'SIZE\s*[+-]\s*\d+|[+-]\d+\s*(?:vs|from)\s*slot|mine\s*[+-]\s*\d+', re.I)
# Only the shapes workers actually use to report a DIFF distance. The (?<![\w.]) guard keeps the
# tail of a hex literal from reading as a decimal count -- without it "9/0xb4 bytes diff" scores as
# 4 bytes, the most dangerous possible misread since it makes a barely-started function look solved.
_N = r'(?<![\w.])'
DIST = re.compile(rf'{_N}(\d+)\s*/\s*(?:0x)?[0-9a-f]+\s*(?:bytes?|b)\b'
                  rf'|\bbest\s*(?:of\s*)?{_N}(\d+)\s*(?:bytes?|b)\b'
                  rf'|{_N}(\d+)\s*(?:bytes?|b)\s*(?:best|diff|off|out)\b'
                  rf'|\b(?:diff|stuck|got to)\s*{_N}(\d+)\s*(?:bytes?|b)\b'
                  rf'|{_N}(\d+)\s*diff\s*bytes?\b'
                  rf'|{_N}(\d+)\s*bytes?\s*at\s*0x'
                  rf'|{_N}(\d+)\s*b\s*/', re.I)


def distances(line):
    """Every DIFF distance a SKIP line reports, noise stripped."""
    return [int(g) for m in DIST.finditer(NOISE.sub(" ", line)) for g in m.groups() if g]


def measured():
    """addr -> byte distance from the last repairsweep GATE, which beats parsing stale SKIP text."""
    out = {}
    try:
        t = open(f"{SP}/repair_verdicts.txt", encoding="utf-8", errors="ignore").read()
    except OSError:
        return out
    for line in t.splitlines():
        p = line.split(None, 2)
        if len(p) == 3:
            b = re.search(r'(\d+)\s*(?:bytes?|B)\b', p[2])
            if b:
                out[p[1].lower()] = int(b.group(1))
    return out


# A file sitting in staging/ is NOT evidence of pending value and must not be held back from the
# queue. Measured 08-20: 17 addresses whose sources had gated MATCH the day before were re-gated by
# finish_wave and came back BYTEDIFF/SIZE -- a gate verdict decays as the repo moves under it. Holding
# them out would have stranded 34 addresses on the strength of a stale MATCH.


def priors():
    """addr -> [prior files], best first."""
    by = collections.defaultdict(list)
    for pat in POOLS:
        for f in glob.glob(f"{KIT if pat.startswith('priors/') else SP}/{pat}"):
            m = re.search(r'(0[0-9a-f]{7})', os.path.basename(f))
            if m:
                by[m.group(1).lower()].append(f.replace("\\", "/"))
    for a, fs in by.items():
        fs.sort(key=lambda f: (rank_of(f), -os.path.getmtime(f)))
    return by


def module_from_path(f):
    """hold_023, ov031_stage, staging/ov031, main_stage -> the module that produced the file.

    The pool directory is better evidence than an address range: several overlays share a load
    region, so range lookup calls those addresses ambiguous and drops them -- which silently threw
    away every overlay candidate (152 of 251) the first time this ran.
    """
    d = os.path.dirname(f).replace("\\", "/")
    tail = "/".join(d.rsplit("/", 2)[-2:])
    m = re.search(r'(?:hold_|staging/|)(?:ov)?(\d{3})(?:_stage)?$', tail)
    if m:
        return m.group(1)
    return "main" if re.search(r'(?:hold_main|main_stage|staging/main|priors/main)$', tail) else ""


def rows(keep_hard=False):
    """Resumable work, most tractable first, plus the rows held back and why.

    Ranking is by PRIOR EFFORT before byte distance. Byte distance measures how hard a function has
    already been ground, not how close it is to falling: a residue only reaches 4 bytes because a
    previous session burned its levers getting there, so ascending-bytes ranks descending-tractability
    inside this pool. Measured 08-20: ranking by bytes put four exhausted residues at the head of the
    queue and both that ran came back MISS for $4.80, the second one landing 2 bytes from the prior
    attempt's own recorded best.
    """
    sk, ms = skips(), measured()
    out, held = [], []
    for a, fs in priors().items():
        if matched(a):
            continue
        mod = module_from_path(fs[0]) or module_of(a)
        if not mod:
            continue
        bytes_, reason = sk.get(a, (None, ""))
        bytes_ = ms.get(a, bytes_)
        eff = max((int(x) for x in EFFORT.findall(reason)), default=0)
        # A prior session naming a spent lever DEPRIORITISES an address; it never removes it. These
        # are compiler outputs of human-written C, so a C form exists for every one of them and
        # "earlier sessions gave up here" is evidence about those sessions, not about the function.
        # An exclusion list is how 30 matchable functions got skiplisted before.
        hard = 1 if HARD.search(reason) else 0
        row = (hard, eff, bytes_ if bytes_ is not None else 10 ** 6, mod, a, fs[0])
        if hard:
            held.append(("deprioritised", mod, a, reason))
        out.append(row)
    out.sort(key=lambda r: (r[0], r[1], r[2], r[3], r[4]))
    return out, held


if __name__ == "__main__":
    # Worker verdict text carries arrows and box glyphs; this console is cp1252, so printing a
    # reason raw kills the whole listing with a UnicodeEncodeError.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = sys.argv[1:]
    keep_hard = "--all" in args
    arg = next((x for x in args if not x.startswith("--")), "")
    if re.fullmatch(r'0[0-9a-fA-F]{7}', arg):
        fs = priors().get(arg.lower(), [])
        print(fs[0] if fs else "", end="")
        sys.exit(0)
    out, held = rows(keep_hard)
    if "--count" in args:
        print(len(out))
    elif "--held" in args:
        # Never drop work silently: a held row is a decision, and it has to be readable.
        for why, mod, a, reason in sorted(held):
            print(f"{why} {mod} {a} {reason[:110]}")
    else:
        for hard, eff, b, mod, a, f in out:
            print(f"{mod} {a} {b if b < 10**6 else '-'} {f}")
