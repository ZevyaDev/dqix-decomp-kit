"""Rank plain-named symbols by reach: how many distinct functions call or reference them.

    python naming/rank.py [--region usa] [--top N]     writes $SP/names/rank.tsv, prints the top N

Columns: key, kind (func|data), module, addr, size, callers (distinct functions that call it),
modules (distinct modules those callers live in), refs (distinct functions that load its address),
score = callers + refs + 4 * (modules - 1). Named and upstream symbols are left out.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kitpaths
import namerules
from graph import Graph


def rank(g):
    rows = []
    for key, sym in g.by_key.items():
        if not namerules.DEFAULT.fullmatch(sym.name):
            continue
        users = g.callers[key] | g.refs[key]
        if not users:
            continue
        mods = {m for m, _ in users}
        c, r = len(g.callers[key]), len(g.refs[key])
        rows.append((c + r + 4 * (len(mods) - 1), sym, c, len(mods), r))
    rows.sort(key=lambda x: (-x[0], x[1].name))
    return rows


def main():
    args = sys.argv[1:]
    region = args[args.index("--region") + 1] if "--region" in args else "usa"
    top = int(args[args.index("--top") + 1]) if "--top" in args else 30
    rows = rank(Graph(region))
    out = os.path.join(kitpaths.SP, "names", "rank.tsv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("key\tkind\tmodule\taddr\tsize\tcallers\tmodules\trefs\tscore\n")
        for score, s, c, mm, r in rows:
            fh.write(f"{s.name}\t{s.kind}\t{s.module}\t{s.addr:08x}\t{s.size}\t{c}\t{mm}\t{r}\t{score}\n")
    for score, s, c, mm, r in rows[:top]:
        print(f"{score:5} {s.name:28} {s.kind:4} {s.module:5} size={s.size:<5} callers={c:<4} modules={mm:<3} refs={r}")
    print(f"{len(rows)} ranked -> {out}")


if __name__ == "__main__":
    main()
