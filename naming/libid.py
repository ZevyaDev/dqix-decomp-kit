"""Library names by instruction shape: plain functions that a reference decomp's library code implements.

    python naming/libid.py [module...] [--out FILE]     default every module; FILE default $SP/names/libid.jsonl

For each plain function of 12 or more instructions, sdkident's exact-shape hits from library paths
(NitroSDK, NitroSystem, MSL, runtime) are collected; when they all carry one real name, a ledger row is
written with the hits as evidence. Import the file with `names.py import` after reading it.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import kitpaths
import namerules
import sdkident

LIBRARY = re.compile(r"/(?:lib|libs|NitroSDK|NitroSystem|nitro|sdk|msl|MSL|runtime|Runtime)/")
PLACEHOLDER = re.compile(r"^(?:sub|FUN|func|unk|Unk|thunk|ov\d+|Ov\d+|LAB)_|_[0-9A-Fa-f]{7,8}$|^\W|^$")
def stem_for(ref):
    try:
        return ref if namerules.final("func_00000000", ref) else None
    except ValueError:
        return None


def modules(args):
    if args:
        return args
    mods = ["main"]
    base = f"{kitpaths.REPO}/config/usa/arm9/overlays"
    mods += sorted(d[2:] for d in os.listdir(base) if d.startswith("ov"))
    return mods


def sweep(mods, out):
    idx = sdkident.load_index()
    rows = 0
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        for mod in mods:
            for a, size, name, isa in sdkident.our_functions(mod, matched=True):
                if not namerules.DEFAULT.fullmatch(name):
                    continue
                seq = sdkident.our_seq(mod, a, size, isa)
                if len(seq) < 12:
                    continue
                hits = [h for h in sdkident.shape_candidates(seq, idx, floor=0.999)
                        if LIBRARY.search("/" + h["file"]) and not PLACEHOLDER.search(h["ref"])]
                refs = {h["ref"] for h in hits}
                if len(refs) != 1:
                    continue
                ref = refs.pop()
                stem = stem_for(ref)
                if not stem:
                    continue
                evidence = [f"ref: {h['proj']}/{h['file']} {h['ref']} exact, {len(seq)} instructions"
                            for h in hits[:3]]
                fh.write(json.dumps({"key": name, "stem": stem, "evidence": evidence, "by": "libid",
                                     "ref": ref}) + "\n")
                fh.flush()
                rows += 1
                print(f"{name} -> {stem} ({ref}, {len(hits)} hit(s))")
    print(f"{rows} row(s) -> {out}")


def main():
    args = sys.argv[1:]
    out = os.path.join(kitpaths.SP, "names", "libid.jsonl")
    if "--out" in args:
        i = args.index("--out")
        out, args = args[i + 1], args[:i] + args[i + 2:]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sweep(modules(args), out)


if __name__ == "__main__":
    main()
