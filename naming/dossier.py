"""Everything the naming pass knows about one symbol, as compact text for a naming agent.

    python naming/dossier.py <name|addr> [--callers N] [--lines N]

Prints the definition, the callees and loaded symbols with their current names and strings, call sites
from up to N callers spread over modules, dynamic observations from $SP/names/dyn, and ledger rows.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kitpaths
from graph import Graph
import names as ledger_mod

CALL_PREFIX = re.compile(r"[=(;,!&|?]|\breturn\b|->|\.\s*$")


def read(repo, rel):
    try:
        with open(f"{repo}/{rel}", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def close(text, i, opener, closer):
    depth = 0
    while i < len(text):
        c = text[i]
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def definition(text, name):
    for m in re.finditer(rf"\b{re.escape(name)}\s*\(", text):
        start = text.rfind("\n", 0, m.start()) + 1
        if CALL_PREFIX.search(text[start:m.start()]):
            continue
        end = close(text, m.end() - 1, "(", ")")
        if end < 0:
            continue
        tail = re.match(r"[\s\w]*\{", text[end + 1:])
        if not tail:
            continue
        body_end = close(text, end + 1 + tail.end() - 1, "{", "}")
        if body_end > 0:
            return text[start:body_end + 1]
    return None


def call_site(text, name):
    use = re.compile(rf"\b{re.escape(name)}\b")
    prototype = re.compile(rf'^\s*(?:extern\s+"C"\s+)?(?!return\b)(?:[\w:<>]+[\s*&]+)+{re.escape(name)}\s*\([^;{{]*;')
    for line in text.splitlines():
        if use.search(line) and not prototype.match(line) and not line.lstrip().startswith("extern ") \
                and not definition(line + "{}", name):
            return line.strip()[:160]
    return None


def label(g, key, moved):
    sym = g.by_key[key]
    return moved.get(sym.name, sym.name)


def dynamic(sym):
    out = []
    for path in sorted(glob.glob(os.path.join(kitpaths.SP, "names", "dyn", "*.json"))):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        hit = data.get("functions", {}).get(f"{sym.module}:{sym.addr:08x}")
        if hit:
            args = "; ".join(" ".join(f"{a:x}" for a in row) for row in hit.get("args", [])[:4])
            out.append(f"{data.get('scenario', os.path.basename(path))}: {hit.get('calls', '?')} call(s)"
                       + (f", r0-r3 {args}" if args else ""))
    return out


def dossier(g, sym, n_callers=12, n_lines=160):
    rows = ledger_mod.rows()
    moved = {r["key"]: r["final"] for r in rows.values() if r["status"] == "landed" and "::" not in r["key"]}
    repo = g.repo
    out = []
    file = g.source_file(sym)
    callers = sorted(g.callers[sym.key] | g.refs[sym.key])
    mods = sorted({m for m, _ in callers})
    out.append(f"{sym.kind.upper()} {sym.name}  {sym.module} 0x{sym.addr:08x} size 0x{sym.size:x}  file {file}  "
               f"reach: {len(g.callers[sym.key])} callers, {len(g.refs[sym.key])} refs, {len(mods)} modules")
    text = read(repo, file) if file else ""
    if sym.kind == "func":
        body = definition(text, sym.name) or text
        lines = body.splitlines()
        out.append("SOURCE" + (f" (first {n_lines} of {len(lines)} lines)" if len(lines) > n_lines else ""))
        out += lines[:n_lines]
        callees = [label(g, k, moved) for k in sorted(g.callees[sym.key])]
        if callees:
            out.append("CALLS " + " ".join(callees))
    else:
        s = g.string_at(sym)
        if s:
            out.append(f'STRING "{s}"')
        decl = [l.strip() for l in text.splitlines() if re.search(rf"\b{re.escape(sym.name)}\b", l)][:4]
        out += [f"DECL {l}" for l in decl]
    loads = []
    for k in sorted(g.loads[sym.key]):
        t = g.by_key[k]
        s = g.string_at(t) if t.kind == "data" else None
        loads.append(f'{label(g, k, moved)}="{s}"' if s else label(g, k, moved))
    if loads:
        out.append("LOADS " + " ".join(loads))
    picked, seen = [], set()
    for key in sorted(callers, key=lambda k: (k[0] in seen, k)):
        if len(picked) >= n_callers:
            break
        if key[0] in seen and len(seen) < len(mods):
            continue
        seen.add(key[0])
        picked.append(key)
    if picked:
        out.append(f"CALLERS ({len(picked)} of {len(callers)})")
    for key in picked:
        c = g.by_key[key]
        cfile = g.source_file(c)
        site = call_site(read(repo, cfile), sym.name) if cfile else None
        out.append(f"  {label(g, key, moved)} [{c.module}] {cfile}: {site or '(asm or not found)'}")
    dyn = dynamic(sym)
    if dyn:
        out.append("DYNAMIC")
        out += [f"  {d}" for d in dyn]
    mine = [r for k, r in rows.items() if k == sym.name or k.startswith(sym.name + "::")]
    if mine:
        out.append("LEDGER")
        out += [f"  {r['status']} {r['key']} -> {r['final']}" for r in mine]
    return "\n".join(out)


def main():
    args = sys.argv[1:]
    n_callers = int(args[args.index("--callers") + 1]) if "--callers" in args else 12
    n_lines = int(args[args.index("--lines") + 1]) if "--lines" in args else 160
    names = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--"))]
    if not names:
        sys.exit(__doc__)
    g = Graph()
    for name in names:
        sym = g.lookup(name)
        if not sym:
            print(f"NOT FOUND {name}")
            continue
        print(dossier(g, sym, n_callers, n_lines))
        print()


if __name__ == "__main__":
    main()
