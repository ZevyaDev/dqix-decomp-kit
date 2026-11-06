"""The naming pass's ledger: what each plain name becomes, the evidence for it, and whether it landed.

    python naming/names.py add KEY STEM EVIDENCE... [--by WHO]
    python naming/names.py import FILE             JSON lines {key, stem, evidence: [...], by}
    python naming/names.py accept KEY...           proposed -> accepted (the audit passed)
    python naming/names.py reject KEY WHY
    python naming/names.py check [DIR]             every accepted row not landed, against DIR
    python naming/names.py apply DIR               rename them in decomp tree DIR
    python naming/names.py show [KEY...]
    bash naming/namesland.sh [--dry]               apply in the integration tree, gate every region, publish

A key is the plain name in the tree (namerules.py): `func_ov012_021e4bc8`, `data_02101234`,
`Struct_020a1234`, `Struct_020a1234::unknown_34_`, `func_02012345::arg0`. The final name is the stem plus
the key's address or member offset. Parameter and local names need their function named in the same
batch or before. The ledger is $SP/names/ledger.jsonl; the last row for a key wins.
"""
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kitpaths
import namerules

LEDGER = os.environ.get("DQIX_NAMES_LEDGER") or os.path.join(kitpaths.SP, "names", "ledger.jsonl")
SOURCE_EXT = (".c", ".cpp", ".h", ".hpp", ".inc", ".s")
TOKEN = re.compile(rb"[A-Za-z_][A-Za-z0-9_]*")
PATH_EXT = re.compile(rb"\.(?:cpp|c|h|hpp|inc|s)\b")
SYMBOL_ADDR = re.compile(r"\baddr:0x([0-9a-fA-F]+)")
ALIAS = re.compile(rb"(?m)^[ \t]*#[ \t]*define[ \t]+((?:func|data)_\w+)[ \t]+((?:func|data)_\w+)[ \t]*\r?$")
OTHER_REGIONS = ("eur", "jpn")
REGION_TAG = re.compile(r"(?:^|_)(?:jpn|eur)_")
EMPTY_REGION = re.compile(rb"(?m)^[ \t]*#[ \t]*if(?:def[ \t]+(?:jpn|eur)|[ \t]+defined\((?:jpn|eur)\))"
                          rb"[ \t]*\r?\n[ \t]*#[ \t]*endif[^\n]*\n")


def rows():
    out = {}
    if os.path.isfile(LEDGER):
        with open(LEDGER, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    out[row["key"]] = row
    return out


def write(new_rows):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8", newline="\n") as fh:
        for row in new_rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def proposal(key, stem, evidence, by):
    kind, final = namerules.final(key, stem)
    evidence = [e for e in evidence if e.strip()]
    if not evidence:
        raise ValueError(f"{key}: no evidence")
    return {"key": key, "stem": stem, "final": final, "kind": kind, "evidence": evidence, "by": by,
            "status": "proposed", "t": time.strftime("%Y-%m-%dT%H:%M:%S")}


def restate(key, status, **extra):
    row = dict(rows()[key], status=status, t=time.strftime("%Y-%m-%dT%H:%M:%S"), **extra)
    write([row])
    return row


def tree_files(tree):
    for top in ("src", "include"):
        for folder, _, names in os.walk(os.path.join(tree, top)):
            for name in names:
                if name.endswith(SOURCE_EXT):
                    yield os.path.join(folder, name)
    for folder, _, names in os.walk(os.path.join(tree, "config")):
        for name in names:
            if name == "symbols.txt":
                yield os.path.join(folder, name)


def tree_tokens(tree):
    found = set()
    for path in tree_files(tree):
        with open(path, "rb") as fh:
            data = fh.read()
        found.update(TOKEN.findall(data))
    return found


def landed_globals(ledger):
    return {r["key"]: r["final"] for r in ledger.values() if r["status"] == "landed" and "::" not in r["key"]}


def current(key, moved):
    outer, sep, inner = key.partition("::")
    return f"{moved.get(outer, outer)}{sep}{inner}"


def batch(ledger):
    return [r for r in ledger.values() if r["status"] == "accepted"]


def problems(tree, ledger, todo):
    moved = landed_globals(ledger)
    tokens = tree_tokens(tree)
    out, finals = [], {}
    named_now = {r["key"] for r in todo if r["kind"] == "func"}
    for r in todo:
        key = current(r["key"], moved)
        outer = key.partition("::")[0]
        if outer.encode() not in tokens:
            out.append(f"NOT IN TREE {r['key']}")
        if "::" not in key:
            if r["final"].encode() in tokens:
                out.append(f"TAKEN {r['key']}: {r['final']} already exists")
            if r["final"] in finals:
                out.append(f"DUPLICATE {r['key']} and {finals[r['final']]}: both {r['final']}")
            finals[r["final"]] = r["key"]
        elif r["kind"] == "local":
            fn = r["key"].partition("::")[0]
            if namerules.DEFAULT.fullmatch(fn) and fn not in named_now and fn not in moved:
                out.append(f"UNNAMED FUNCTION {r['key']}: name {fn} in the same batch")
    return out


def mangled_pattern(mapping):
    alts = b"|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True))
    return re.compile(rb"([0-9]+)(" + alts + rb")")


def renamer(mapping):
    mapping = {k.encode(): v.encode() for k, v in mapping.items()}
    mangled = mangled_pattern(mapping) if mapping else None

    def in_mangled(m):
        digits, ident = m.group(1), m.group(2)
        length = str(len(ident)).encode()
        if not digits.endswith(length):
            return m.group(0)
        new = mapping[ident]
        return digits[:-len(length)] + str(len(new)).encode() + new

    def rename(data):
        def token(m):
            tok = m.group(0)
            if tok.startswith(b"_Z"):
                return mangled.sub(in_mangled, tok)
            new = mapping.get(tok)
            if new is None or PATH_EXT.match(data, m.end()):
                return tok
            return new
        return TOKEN.sub(token, data) if mapping else data
    return rename


def rename_globals(tree, mapping):
    if not mapping:
        return []
    rename = renamer(mapping)
    changed = []
    for path in tree_files(tree):
        with open(path, "rb") as fh:
            data = fh.read()
        new_data = rename(data)
        if new_data != data:
            with open(path, "wb") as fh:
                fh.write(new_data)
            changed.append(os.path.relpath(path, tree).replace("\\", "/"))
    return changed


def region_symbols(tree, region):
    out = {}
    for path in glob.glob(f"{tree}/config/{region}/arm9/**/symbols.txt", recursive=True):
        m = re.search(r"overlays[\\/](ov\d{3})", path)
        module = m.group(1) if m else "main"
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                a = SYMBOL_ADDR.search(line)
                if a and line.strip():
                    out.setdefault(namerules.own_ident(line.split()[0]), (module, int(a.group(1), 16)))
    return out


def define_aliases(tree):
    out = {}
    for path in tree_files(tree):
        if path.endswith("symbols.txt"):
            continue
        with open(path, "rb") as fh:
            for m in ALIAS.finditer(fh.read()):
                out.setdefault(m.group(1).decode(), set()).add(m.group(2).decode())
    return out


def localized(tree, todo):
    usa = region_symbols(tree, "usa")
    others = {region: region_symbols(tree, region) for region in OTHER_REGIONS}
    out = []
    for r in todo:
        m = namerules.DEFAULT.fullmatch(r["key"])
        if m and m.group(1) in ("func", "data") and r["key"] not in usa and not REGION_TAG.search(m.group(2)):
            only = [region for region in OTHER_REGIONS if r["key"] in others[region]]
            if len(only) == 1:
                ov = re.match(r"ov\d{3}_", m.group(2))
                head = ov.group(0) if ov else ""
                r = dict(r, final=f"{r['stem']}_{head}{only[0]}_{m.group(2)[len(head):]}{m.group(3)}")
        out.append(r)
    return out


def drop_aliases(tree, pairs):
    if not pairs:
        return []
    lines = [re.compile(rb"(?m)^[ \t]*#[ \t]*define[ \t]+" + re.escape(key.encode()) + rb"[ \t]+"
                        + re.escape(alias.encode()) + rb"[ \t]*\r?\n") for key, alias in pairs]
    changed = []
    for path in tree_files(tree):
        if path.endswith("symbols.txt"):
            continue
        with open(path, "rb") as fh:
            data = fh.read()
        new = data
        for line in lines:
            new = line.sub(b"", new)
        if new != data:
            new = EMPTY_REGION.sub(b"", new)
            with open(path, "wb") as fh:
                fh.write(new)
            changed.append(os.path.relpath(path, tree).replace("\\", "/"))
    return changed


def apply(tree, ledger, todo):
    import plainnames
    moved = landed_globals(ledger)
    scoped = {current(r["key"], moved): r["final"] for r in todo if "::" in r["key"]}
    mapping = {current(r["key"], moved): r["final"] for r in todo if "::" not in r["key"]}
    usa = region_symbols(tree, "usa")
    aliases = define_aliases(tree)
    collapse, misses = {}, []
    targets = {}
    for name, names in aliases.items():
        for alias in names:
            targets.setdefault(alias, set()).add(name)
    for key, final in mapping.items():
        for other in sorted(targets.get(key, set()) - {key}):
            misses.append(f"ALIAS TARGET {key}: it is {other}'s region alias, so that region's {other} "
                          f"would take this name")
        for alias in sorted(aliases.get(key, ())):
            if alias in usa:
                misses.append(f"ALIAS COLLIDES {key}: its region alias {alias} is also a USA name")
            else:
                collapse[(key, alias)] = final
    if misses:
        return [], misses
    changed = []
    if scoped:
        changed, misses = plainnames.rename_scoped(tree, scoped)
    changed = set(changed) | set(drop_aliases(tree, collapse))
    changed |= set(rename_globals(tree, {**mapping, **{alias: final for (_, alias), final in collapse.items()}}))
    return sorted(changed), misses


def land(dry=False):
    import landpr
    ledger = rows()
    todo = batch(ledger)
    if not todo:
        print("nothing accepted")
        return
    kit = kitpaths.KIT
    code, out = landpr.run(kit, sys.executable, f"{kit}/integ_tree.py", "sync")
    if code:
        landpr.refuse(f"integ_tree.py sync: {out.strip()[-200:]}")
    tree = out.strip().splitlines()[-1]
    os.chdir(tree)
    tip = landpr.fetch(tree, landpr.BRANCH)
    landpr.git(tree, "checkout", "-q", "-f", "--detach", tip)
    landpr.UNDO.append((tree, tip))
    todo = localized(tree, todo)
    found = problems(tree, ledger, todo)
    if found:
        landpr.refuse("\n".join(found))
    changed, misses = apply(tree, ledger, todo)
    if misses:
        landpr.refuse("\n".join(f"UNRESOLVED {m}" for m in misses))
    landpr.git(tree, "add", "--", "src", "include", "config")
    landpr.git(tree, "commit", "-q", "-m", f"Name {len(todo)} symbols")
    moved = landed_globals(ledger)
    renames = os.path.join(os.path.dirname(LEDGER), "renames.json")
    with open(renames, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({current(r["key"], moved): r["final"] for r in todo if "::" not in r["key"]}, fh)
    code, out = landpr.run(kit, sys.executable, f"{kit}/prready.py", "decomp",
                           env=dict(os.environ, DQIX_REPO=tree, PRREADY_RENAMES=renames))
    if code:
        landpr.refuse(f"prready.py decomp:\n{out.strip()}")
    landpr.build_every_region(tree)
    if dry:
        landpr.git(tree, "checkout", "-q", "-f", "--detach", tip)
        print(f"GREEN {len(todo)} name(s) in {len(changed)} file(s); --dry: nothing published")
        return
    code, out = landpr.run(kit, sys.executable, f"{kit}/integ_tree.py", "publish")
    if code not in (0, 2):
        landpr.refuse(f"integ_tree.py publish: {out.strip()[-300:]}")
    head = landpr.git(tree, "rev-parse", "--short", "HEAD")[1].strip()
    pooled = landpr.run(kit, sys.executable, f"{kit}/pad/repool.py", "--apply", "--rev", tip)[1].strip()
    print("pools: " + (pooled.splitlines() or [""])[-1])
    for r in todo:
        restate(r["key"], "landed", commit=head, final=r["final"])
    print(f"LANDED {len(todo)} name(s) in {len(changed)} file(s) at {head}")


def main():
    args = sys.argv[1:]
    by = "?"
    if "--by" in args:
        i = args.index("--by")
        by, args = args[i + 1], args[:i] + args[i + 2:]
    if not args:
        sys.exit(__doc__)
    cmd, args = args[0], args[1:]
    if cmd == "add" and len(args) >= 3:
        write([proposal(args[0], args[1], args[2:], by)])
    elif cmd == "import" and len(args) == 1:
        new, bad = [], []
        with open(args[0], encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    try:
                        new.append(proposal(r["key"], r["stem"], r.get("evidence", []), r.get("by", by)))
                    except (ValueError, KeyError) as e:
                        bad.append(f"BAD {e}")
        write(new)
        print("\n".join(bad + [f"{len(new)} proposed"]))
        sys.exit(1 if bad else 0)
    elif cmd == "accept" and args:
        ledger = rows()
        for key in args:
            if ledger.get(key, {}).get("status") != "proposed":
                sys.exit(f"{key}: not proposed")
            restate(key, "accepted")
    elif cmd == "reject" and len(args) == 2:
        restate(args[0], "rejected", why=args[1])
    elif cmd in ("check", "apply"):
        tree = args[0] if args else kitpaths.REPO
        ledger = rows()
        todo = localized(tree, batch(ledger))
        found = problems(tree, ledger, todo)
        if cmd == "apply" and not found:
            changed, misses = apply(tree, ledger, todo)
            found = [f"UNRESOLVED {m}" for m in misses]
            print(f"{len(todo)} name(s), {len(changed)} file(s) changed")
        print("\n".join(found) if found else f"OK {len(todo)} accepted")
        sys.exit(1 if found else 0)
    elif cmd == "land" and args in ([], ["--dry"]):
        land(dry=bool(args))
    elif cmd == "show":
        ledger = rows()
        for r in ledger.values():
            if not args or r["key"] in args:
                print(f"{r['status']:9} {r['key']} -> {r['final']}  [{'; '.join(r['evidence'])}]")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
