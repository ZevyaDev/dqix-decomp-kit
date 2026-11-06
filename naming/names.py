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


def rename_globals(tree, mapping):
    mapping = {k.encode(): v.encode() for k, v in mapping.items()}
    if not mapping:
        return []
    mangled = mangled_pattern(mapping)

    def in_mangled(m):
        digits, ident = m.group(1), m.group(2)
        length = str(len(ident)).encode()
        if not digits.endswith(length):
            return m.group(0)
        new = mapping[ident]
        return digits[:-len(length)] + str(len(new)).encode() + new

    changed = []
    for path in tree_files(tree):
        with open(path, "rb") as fh:
            data = fh.read()

        def token(m):
            tok = m.group(0)
            if tok.startswith(b"_Z"):
                return mangled.sub(in_mangled, tok)
            new = mapping.get(tok)
            if new is None or PATH_EXT.match(data, m.end()):
                return tok
            return new

        new_data = TOKEN.sub(token, data)
        if new_data != data:
            with open(path, "wb") as fh:
                fh.write(new_data)
            changed.append(os.path.relpath(path, tree).replace("\\", "/"))
    return changed


def apply(tree, ledger, todo):
    import plainnames
    moved = landed_globals(ledger)
    scoped = {current(r["key"], moved): r["final"] for r in todo if "::" in r["key"]}
    glob = {current(r["key"], moved): r["final"] for r in todo if "::" not in r["key"]}
    changed, misses = [], []
    if scoped:
        changed, misses = plainnames.rename_scoped(tree, scoped)
    changed = sorted(set(changed) | set(rename_globals(tree, glob)))
    return changed, misses


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
    found = problems(tree, ledger, todo)
    if found:
        landpr.refuse("\n".join(found))
    changed, misses = apply(tree, ledger, todo)
    if misses:
        landpr.refuse("\n".join(f"UNRESOLVED {m}" for m in misses))
    landpr.git(tree, "add", "--", "src", "include", "config")
    landpr.git(tree, "commit", "-q", "-m", f"Name {len(todo)} symbols")
    code, out = landpr.run(kit, sys.executable, f"{kit}/prready.py", "decomp", env=dict(os.environ, DQIX_REPO=tree))
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
    for r in todo:
        restate(r["key"], "landed", commit=head)
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
        todo = batch(ledger)
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
