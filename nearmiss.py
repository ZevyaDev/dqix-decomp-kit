#!/usr/bin/env python
"""Functions a worker left a few bytes from byte-exact, ranked, and queued for the dispatcher.

    python nearmiss.py [max_bytes=16] [--write-priority]
    python nearmiss.py [max_bytes=16] --all       every verified near miss, reservations and
                                                  already-worked-by-a-paid-session included;
                                                  refuses --write-priority

A SKIP reading "4 bytes short, everything else byte-exact" is the most expensive thing in the
pipeline to re-serve cold: the decode is already done and the diff is already localised, so what it
needs is one insight, not another five variations. Those are the claims worth giving the expensive
model.

This used to mine the prose of worker SKIP lines out of the logs and emit to `wave_<mod>/N0.txt`.
Both ends were wrong. `wlog/blockers.tsv` is the MEASURED ledger -- module, size, class and residue
in columns, written by the gate rather than parsed out of a sentence -- and it found 20 functions
under 16 bytes where the prose scan found 1. And `wave_<mod>/` belongs to the retired batch driver;
pull dispatch serves `wlog/priority_<mod>.txt`, so everything the old emit wrote was unreachable.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import glob
import json
import subprocess
import os
import re
import sys

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
TSV = f"{SP}/wlog/blockers.tsv"
NEVER = {"NO-ARTIFACT", "UNKNOWN", "MATCH", "ALREADY-COMMITTED"}


def _last_paid(addr):
    t = 0.0
    for p in glob.glob(f"{SP}/wlog/pull_*_{addr}.json"):
        try:
            if os.path.getsize(p) > 0:
                t = max(t, os.path.getmtime(p))
        except OSError:
            pass
    return t


def _declined_classes():
    out = set()
    try:
        for line in open(f"{SP}/wlog/blockers_declined.txt", encoding="utf-8", errors="ignore"):
            w = line.split()
            if w and re.fullmatch(r"[A-Z][A-Z0-9-]+", w[0]):
                out.add(w[0])
    except OSError:
        pass
    return out

# VERIFIED asm-only (28 C forms, 11 compiler configs, all 7 matched instances use asm). It produces
# textbook near-misses -- 8 bytes, everything else exact -- so without this filter it sits at the top
# of the queue forever and every re-serve is a guaranteed loss.
ASMONLY = re.compile(r"pool[- ]?load|pool-literal|ldr r\d+,?=0x|keeps? pool-loaded|small ARM-encodable",
                     re.I)


def matched_ranges():
    out = []
    for dl in [f"{REPO}/{buildcfg.config_root()}/delinks.txt"] + \
            glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/ov*/delinks.txt"):
        if os.path.exists(dl):
            out += [(int(a, 16), int(b, 16)) for a, b in re.findall(
                r"(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$",
                open(dl, encoding="utf-8", errors="ignore").read())]
    return out


def skiplisted():
    out = set()
    for p in glob.glob(f"{SP}/skiplist*.txt") + glob.glob(f"{SP}/wlog/skiplist*.txt"):
        try:
            for line in open(p, encoding="utf-8", errors="ignore"):
                m = re.match(r"\s*([0-9a-fA-F]{8})\b", line)
                if m:
                    out.add(m.group(1).lower())
        except OSError:
            pass
    return out


def reserved():
    """Addresses a free sweep is working, so the paid queue does not buy what CPU is about to win.

    The queue has two consumers and one of them costs money. Without this the regenerating watcher
    kept re-offering the four register permutations colorsweep was already sweeping.
    """
    out = set()
    try:
        for line in open(f"{SP}/wlog/nearmiss_reserved.txt", encoding="utf-8", errors="ignore"):
            m = re.match(r"\s*([0-9a-fA-F]{8})\b", line)
            if m:
                out.add(m.group(1).lower())
    except OSError:
        pass
    return out


def staged():
    """Addresses already proven and waiting on integration.

    A match is not delinked until it commits, so between staging and the next integration pass the
    ledger still calls it unmatched and the queue would sell it to the expensive model a second
    time. `0202b900` was hand-matched, staged, and still listed.
    """
    out = set()
    for p in glob.glob(f"{SP}/staging/*/*.cpp"):
        m = re.search(r"//\s*(?:SCRATCH-)?USA:\s*func_(?:ov\d+_)?([0-9a-fA-F]{8})",
                      open(p, encoding="utf-8", errors="ignore").read())
        if m:
            out.add(m.group(1).lower())
        m2 = re.search(r"([0-9a-fA-F]{8})", os.path.basename(p))
        if m2:
            out.add(m2.group(1).lower())
    return out


def _cache():
    try:
        return json.load(open(f"{SP}/wlog/nearmiss_verify.json", encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def verified_gap(mod, addr, path, cache):
    """The residue the FILE actually gates at, not the number the ledger remembers.

    A row records what a session measured; the file it names can since have been replaced by a worse
    session writing the same basename. ov024:021f9874 was advertised at 4 bytes for hours while the
    only artifact behind it gated at 87, and the queue sold that to the expensive model. Keyed on
    (path, size, mtime), so a re-run costs nothing until an artifact actually changes.
    """
    if not path or not os.path.exists(path):
        return None
    st = os.stat(path)
    key = f"{path}|{st.st_size}|{int(st.st_mtime)}"
    if key in cache:
        return cache[key]
    r = subprocess.run([sys.executable, f"{KIT}/wgate.py", mod, addr, path],
                       capture_output=True, text=True, cwd=REPO)
    txt = r.stdout + r.stderr
    gap = 0 if re.search(r"(?m)^MATCH\b", txt) else None
    if gap is None:
        m = re.search(r"(?m)^RESIDUE\s+\S+\s+(\d+)", txt)
        gap = int(m.group(1)) if m else -1
    cache[key] = gap
    return gap


def rows(maxb, verify=True, include_worked=False):
    rng = matched_ranges()
    never = NEVER | _declined_classes()
    skip = skiplisted() | staged()
    if not include_worked:
        skip |= reserved()
    best, newest, paid = {}, {}, {}
    try:
        for line in open(TSV, encoding="utf-8", errors="ignore"):
            f = line.rstrip("\n").split("\t")
            if len(f) < 6 or not f[0].isdigit():
                continue
            addr = f[2].strip().lower()
            if not re.fullmatch(r"[0-9a-fA-F]{8}", addr):
                continue
            if not f[5].strip().isdigit():
                continue
            gap = int(f[5].strip())
            if addr not in paid:
                paid[addr] = _last_paid(addr)
            if paid[addr] and int(f[0]) <= paid[addr]:
                newest[addr] = min(newest.get(addr, gap), gap)
            # BEST per address, not LATEST. A session that ends worse than an earlier one does not
            # undo the earlier one -- taking the latest row silently dropped 021f9874 out of the
            # queue the moment a worker regressed it.
            if addr not in best or gap < best[addr][0]:
                best[addr] = (gap, f[1], addr, int(f[3]) if f[3].isdigit() else 0,
                              f[4].strip(), f[6] if len(f) > 6 else "",
                              f[7].strip() if len(f) > 7 else "")
    except OSError:
        return []

    cache = _cache() if verify else {}
    out, dirty = [], False
    for gap, mod, addr, size, cls, detail, evidence in sorted(best.values()):
        if cls in never or addr in skip or ASMONLY.search(detail):
            continue
        if any(s <= int(addr, 16) < e for s, e in rng):
            continue
        if not 0 < gap <= maxb:
            continue
        if verify:
            cand = f"{SP}/clsbest/{addr}.cpp"
            paths = [p for p in (evidence, cand) if p and os.path.exists(p)]
            paths += sorted(glob.glob(f"{SP}/attempts/*{addr}*.cpp"))
            seen, real = set(), None
            for p in paths:
                p = p.replace("\\", "/")
                if p in seen:
                    continue
                seen.add(p)
                g = verified_gap(mod, addr, p, cache)
                dirty = True
                if g is not None and g >= 0 and (real is None or g < real):
                    real = g
                if real is not None and real <= maxb:
                    break
            if real is None or real > maxb:
                continue
            if not include_worked and addr in newest and real >= newest[addr]:
                continue
            gap = real
        out.append((gap, -size, mod, addr, size, cls, detail))
    if dirty:
        try:
            os.makedirs(f"{SP}/wlog", exist_ok=True)
            json.dump(cache, open(f"{SP}/wlog/nearmiss_verify.json", "w", encoding="utf-8"))
        except OSError:
            pass
    out.sort()
    return out


def write_priority(items):
    per = {}
    for gap, _ns, mod, addr, size, cls, _d in items:
        per.setdefault(mod, []).append((addr, gap, size, cls))
    for mod, got in per.items():
        p = f"{SP}/wlog/priority_{'main' if mod == 'main' else 'ov' + mod}.txt"
        keep = []
        if os.path.exists(p):
            # Drop the reserved ones too. Filtering only what this run EMITS leaves an address that
            # has since been reserved sitting in the file from a previous run, which is the whole
            # collision the reservation exists to stop.
            have = {a for a, _g, _s, _c in got} | reserved()
            gone = _declined_classes()
            keep = [l for l in open(p, encoding="utf-8", errors="ignore")
                    if not any(l.lstrip().lower().startswith(a) for a in have)
                    and l.rsplit(",", 1)[-1].strip() not in gone
                    and "nearmiss" not in l]
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            for addr, gap, size, cls in got:
                fh.write(f"{addr}  # nearmiss {gap}B of {size}B, {cls}\n")
            fh.writelines(keep)
        print(f"  {len(got)} near-miss entries -> {os.path.basename(p)}")
    purge_declined()


def purge_declined():
    gone = _declined_classes()
    if not gone:
        return
    for p in glob.glob(f"{SP}/wlog/priority_*.txt"):
        lines = open(p, encoding="utf-8", errors="ignore").readlines()
        keep = [l for l in lines if l.rsplit(",", 1)[-1].strip() not in gone]
        if len(keep) != len(lines):
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.writelines(keep)
            print(f"  purged {len(lines) - len(keep)} declined-class row(s) "
                  f"from {os.path.basename(p)}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # `--residue <addr>` prints the measured residue, or nothing. The dispatcher caps a near-miss
    # session by this rather than by the function's size, and it cannot ask the QUEUE: claim.py
    # strikes an address out of the priority file the moment it serves it, so by the time the cap is
    # computed the address is already gone from the file it would have been looked up in.
    if "--residue" in sys.argv:
        want = sys.argv[sys.argv.index("--residue") + 1].lower()
        for gap, _ns, _mod, addr, _size, _cls, _d in rows(1 << 30, verify=False):
            if addr == want:
                print(gap)
                return 0
        return 1
    maxb = int(args[0]) if args else 16
    everything = "--all" in sys.argv
    got = rows(maxb, include_worked=everything)
    scope = "EVERY verified near miss" if everything else "unmatched"
    print(f"NEAR-MISS QUEUE -- {scope}, <= {maxb} bytes from byte-exact ({len(got)} functions)")
    print(f"{'gap':>4} {'size':>6} {'%':>6}  {'mod':<5} {'addr':<10} {'class':<11} detail")
    print("-" * 108)
    for gap, _ns, mod, addr, size, cls, detail in got:
        pct = 100.0 * gap / size if size else 0
        print(f"{gap:4d} {size:6d} {pct:5.1f}%  {mod:<5} {addr:<10} {cls:<11} {detail[:52]}")
    if "--write-priority" in sys.argv:
        if everything:
            print("REFUSED: --all is the free-consumer view; it must not feed the paid queue")
            return 2
        write_priority(got)
    return 0


if __name__ == "__main__":
    sys.exit(main())
