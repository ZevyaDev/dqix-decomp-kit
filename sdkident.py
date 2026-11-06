#!/usr/bin/env python3
"""IDENTIFY unmatched functions against reference DS decompilations. Research first, never asm-first.

    python sdkident.py index              build the reference index from everything under refs/
    python sdkident.py match <mod> <addr> what in the references implements this function
    python sdkident.py sweep [mod]        every unmatched function, ranked by identifiability
    python sdkident.py show <proj/file> <name>   print a reference implementation

WHY. Library code -- the BIOS syscall stubs, the Metrowerks C runtime, NitroSDK -- is the same
source in every DS game, and several projects have already matched it. Porting a human
implementation beats decompiling it ourselves on every axis: no worker tokens, real names and
types, and code a person wrote. Our `_fadd` is instruction-for-instruction pokediamond's `_fadd`.

IDENTIFICATION IS BY INSTRUCTION SHAPE, NOT BY NAME. Names are a weak signal: ours are descriptive
(`VectorizedMemset`) where the SDK's are official (`MI_CpuFill8`), and 973 of our 1101 unmatched
functions have no name at all. The mnemonic sequence is the actual fingerprint, so a match is a
measured claim -- "these 135 instructions agree" -- rather than a guess from a similar spelling.

THERE IS NO ASM FALLBACK, DELIBERATELY. A sweep that transcribes our own bytes into an `asm` block
whenever C is hard produces assembly where none was needed: the last one matched a game function
and `WaitForVCountZero`, which was four bytes from a clean C match. Assembly here is a CONCLUSION
drawn from a reference decomp that independently implements the same routine as assembly -- and
even then C is preferred if the reference has C. Anything unidentified is reported as
NEEDS-RESEARCH and goes back to normal decompilation. This tool never writes an `asm` block.

ADDRESS BANDS ARE A HINT, NOT A FILTER. Library code clusters at the bottom and top of arm9, so
`sweep` reports that grouping -- but a hardcoded band is a guess about a boundary nobody verified,
so nothing is excluded on that basis and the whole module is always searched.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import json
import os
import re
import sys

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
REFS = f"{SP}/refs"
INDEX = f"{SP}/wlog/sdk_index.json"

# Condition suffixes, longest first so `ne` never eats the `n` of something else.
CONDS = ["eq", "ne", "cs", "hs", "cc", "lo", "mi", "pl", "vs", "vc",
         "hi", "ls", "ge", "lt", "gt", "le", "al"]
# `lo` and `cc` are the same encoding, as are `hs` and `cs`; capstone prints one spelling and the
# reference assembly the other, so both collapse to one before anything is compared.
COND_ALIAS = {"lo": "cc", "hs": "cs", "al": ""}
SHIFTS = ("lsl", "lsr", "asr", "ror", "rrx")


def canon(mn):
    """One spelling per encoding, so our disassembly and reference assembly are comparable.

    Two rewrites matter. capstone prints a shift as a standalone UAL instruction (`lsr r3, r0, #23`)
    where the reference writes the canonical ARM form (`mov r3, r0, lsr #23`) -- same encoding, so
    the shift becomes `mov`. And `lo`/`cc` and `hs`/`cs` are the same four bits, so `sublo` and
    `subcc` must not read as different instructions.
    """
    mn = mn.lower()
    mn = {"svc": "swi", "ldm": "ldmia", "stm": "stmia"}.get(mn, mn)
    if mn in SHIFTS:
        return "mov"
    if mn.endswith("s") and mn[:-1] in SHIFTS:
        return "movs"

    # The S bit and the condition may be written in either order -- reference assembly says
    # `andeqs`, capstone says `andseq` -- so peel both, whichever comes last, and re-emit in one
    # fixed order. Getting this wrong reads two spellings of one encoding as two instructions.
    body, setflags, cond = mn, "", ""
    for _ in range(2):
        if body.endswith("s") and len(body) > 2 and body[:-1] not in ("b", "bl"):
            body, setflags = body[:-1], "s"
            continue
        for c in CONDS:
            if body.endswith(c) and len(body) > len(c):
                body, cond = body[:-len(c)], COND_ALIAS.get(c, c)
                break
        else:
            break
    # A conditional shift (`lsrle`) is still a shift, so the base is folded to MOV only after the
    # condition has been peeled off -- checking the raw mnemonic misses every predicated one.
    if body in SHIFTS:
        body = "mov"
    return body + setflags + cond


def seq_of_asm_text(txt):
    """Mnemonic sequence of a block of ARM assembly source, labels and directives dropped."""
    out = []
    for line in txt.splitlines():
        line = line.split(";")[0].split("//")[0].strip()
        if not line or line.endswith(":"):
            continue
        if line.startswith((".", "#", "@")):
            # Literal pools are part of the shape. Our side records them because capstone cannot
            # decode them; the reference side must record them too or the sequences never line up.
            if line.split()[0] in (".word", ".long", ".int", ".4byte"):
                out.append(".word")
            continue
        mn = line.split()[0]
        if mn.endswith(":"):
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            mn = parts[1].split()[0]
        out.append(canon(mn))
    return out


FUNC_START = re.compile(r"(?m)^\s*(?:arm|thumb)_func_start\s+(\w+)\s*$")
FUNC_END = re.compile(r"(?m)^\s*(?:arm|thumb)_func_end\s+\w+\s*$")
LABEL_START = re.compile(r"(?m)^([A-Za-z_]\w*):\s*$")
ASM_FUNC = re.compile(r"(?m)^\s*asm\s+[\w \*]*?\b(\w+)\s*\([^;{]*?\)\s*\{")
C_FUNC = re.compile(r"(?m)^(?!.*\basm\b)[\w][\w \*]*?\b(\w+)\s*\([^;{]*?\)\s*\{")


def _block(txt, start):
    """Text from `start` to the matching close brace, for a `{`-delimited definition."""
    i = txt.find("{", start)
    depth, j = 0, i
    while j < len(txt):
        if txt[j] == "{":
            depth += 1
        elif txt[j] == "}":
            depth -= 1
            if depth == 0:
                return txt[i + 1:j]
        j += 1
    return txt[i + 1:]


def verified_refs():
    """Directory names a human has confirmed are DS decompilations (refs/VERIFIED.txt)."""
    try:
        lines = open(f"{REFS}/VERIFIED.txt", encoding="utf-8").read().splitlines()
    except OSError:
        return set()
    return {l.split()[0] for l in lines if l.strip() and not l.startswith("#")}


def is_nds_decomp(root):
    """Is this checkout a real Nintendo DS decompilation?

    Only a DS decomp is evidence about DS code. A repository that merely mentions the platform --
    a tool, a header dump, a wiki, a decomp of a different console -- would contribute functions
    that cannot correspond to ours, and a false identification is worse than none because it ends
    the search. The test is structural, not by name: DS games link NitroSDK and are laid out by a
    Nintendo linker script, so both must be present.
    """
    # NEVER OUR OWN GAME. Dragon Quest IX has no independent decompilation -- there is one project
    # and five forks of it, ours among them -- so anything that looks like DQIX under refs/ is our
    # own work coming back around. "Matching" against ourselves would confirm every function we
    # already have and prove nothing about the ones we do not.
    if re.search(r"dqix|dq9|dragon.?quest", os.path.basename(root), re.I):
        return False
    if os.path.basename(root) in verified_refs():
        return True
    # Test the ARCHITECTURE, not the SDK vendoring. Requiring a NitroSDK directory rejected four
    # genuine DS decompilations -- zeldaret/ph, zeldaret/st, sm64ds-decomp and pokeblack -- because
    # they keep the SDK under `libs/` or link it from `arm9.ld`. What every DS ROM has instead is
    # the two-processor split: an ARM9 binary, and an ARM7 binary or overlay table beside it.
    # Search at ANY depth and by substring. A depth-limited, prefix-matched version of this test
    # rejected pokeheartgold, pokeplatinum, pmd-sky and the NitroSDK decomp itself, because each
    # buries its ARM9 tree at a different level under a different parent name. Every DS project
    # names these things somewhere; none of them agree on where.
    arm9 = other = False
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for n in dirs + files:
            low = n.lower()
            arm9 |= "arm9" in low
            other |= "arm7" in low or "overlay" in low or low.endswith((".nds", ".lsf", ".lcf"))
        if arm9 and other:
            return True
    return False


def build_index():
    out = {}

    def add(name, proj, rel, kind, seq, text):
        out.setdefault(name, []).append({"proj": proj, "file": rel, "kind": kind,
                                         "asm": kind != "C",
                                         "seq": seq, "n": len(seq), "text": text[:8000]})

    for proj in sorted(os.listdir(REFS)) if os.path.isdir(REFS) else []:
        root = os.path.join(REFS, proj)
        if not os.path.isdir(root):
            continue
        if not is_nds_decomp(root):
            print(f"skipping {proj}: not a Nintendo DS decompilation")
            continue
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d != ".git"]
            for fn in files:
                if not fn.endswith((".c", ".cpp", ".s")):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    txt = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                rel = os.path.relpath(p, REFS).replace("\\", "/")
                if fn.endswith(".s"):
                    # PROVENANCE GRADE, and it decides whether the entry may justify assembly.
                    # A file whose routines are wrapped in `arm_func_start`/`arm_func_end` came out
                    # of a SPLITTER: it is that project's un-decompiled leftover, not source anyone
                    # wrote. Treating it as proof that a routine "is assembly" would let another
                    # project's unfinished work decide ours -- which is transcribing our own bytes
                    # with extra steps. Hand-written assembly (the syscall stubs) declares plain
                    # labels and carries human comments.
                    marks = list(FUNC_START.finditer(txt))
                    if marks:
                        # A SPLITTER DUMP IS NOT A DECOMPILATION, so it is not a reference.
                        # `arm_func_start`/`arm_func_end` wrappers mean a tool emitted this file
                        # from the ROM: it is that project's un-decompiled leftover, the same bytes
                        # we already have. Porting it would be transcribing our own bytes with a
                        # detour through someone else's repository, and it would let another
                        # project's unfinished work decide that our function "is assembly".
                        # Only human-written source counts: `asm void` in a .c, or a .s with plain
                        # labels and comments (the NitroSDK syscall stubs).
                        continue
                    kind = "HAND"
                    marks = list(LABEL_START.finditer(txt))
                    for k, m in enumerate(marks):
                        stop = marks[k + 1].start() if k + 1 < len(marks) else len(txt)
                        e = FUNC_END.search(txt, m.end(), stop)
                        body = txt[m.end():e.start() if e else stop]
                        add(m.group(1), proj, rel, kind, seq_of_asm_text(body), body)
                else:
                    for m in ASM_FUNC.finditer(txt):
                        body = _block(txt, m.end() - 1)
                        add(m.group(1), proj, rel, "HAND", seq_of_asm_text(body), body)
                    for m in C_FUNC.finditer(txt):
                        if any(m.group(1) == a.group(1) for a in ASM_FUNC.finditer(txt)):
                            continue
                        add(m.group(1), proj, rel, "C", [], _block(txt, m.end() - 1))
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    json.dump(out, open(INDEX, "w", encoding="utf-8"))
    ents = [e for v in out.values() for e in v]
    projs = sorted({e["proj"] for e in ents})
    print(f"indexed {len(out)} names / {len(ents)} definitions from {projs}")
    print(f"  {sum(1 for e in ents if e['asm'])} asm, {sum(1 for e in ents if not e['asm'])} C")


def load_index():
    if not os.path.exists(INDEX):
        sys.exit("no index -- clone a reference decomp into refs/ then run `sdkident.py index`")
    return json.load(open(INDEX, encoding="utf-8"))


def our_functions(mod="main"):
    cfg = f"{REPO}/config/usa/arm9" if mod == "main" else \
          f"{REPO}/config/usa/arm9/overlays/ov{mod}"
    sym = open(f"{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()
    dl = open(f"{cfg}/delinks.txt", encoding="utf-8", errors="ignore").read()
    done = [(int(a, 16), int(b, 16)) for a, b in re.findall(
        r"(?m)^\s*\.(?:text|init) start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)\s*$", dl)]
    out = []
    for m in re.finditer(r"(?m)^(\S+)\s+kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\)"
                         r"\s+addr:0x([0-9a-fA-F]+)", sym):
        name, isa, size, a = m.group(1), m.group(2), int(m.group(3), 16), int(m.group(4), 16)
        if size and not any(s <= a < e for s, e in done):
            out.append((a, size, name, isa))
    return sorted(out)


def our_seq(mod, addr, size, isa):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
    if mod == "main":
        rom = open(f"{REPO}/extract/usa/arm9/arm9.bin", "rb").read()
        base = 0x02000000
    else:
        cfg = f"{REPO}/config/usa/arm9/overlays/ov{mod}"
        rom = open(f"{REPO}/extract/usa/arm9_overlays/ov{mod}.bin", "rb").read()
        base = min(int(x, 16) for x in
                   re.findall(r"start:0x([0-9a-fA-F]+)", open(f"{cfg}/delinks.txt").read()))
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if isa == "thumb" else CS_MODE_ARM)
    code, out, off, step = rom[addr - base:addr - base + size], [], 0, 2 if isa == "thumb" else 4
    # A literal pool sits inside the function body, and capstone stops dead at the first word of
    # it. Stopping there silently truncates the fingerprint -- `_fdiv` came out as 46 instructions
    # for 952 bytes and scored 25% against its own twin -- so record the pool as a token and
    # resume after it.
    while off < len(code):
        got = list(md.disasm(code[off:], addr + off))
        for i in got:
            out.append(canon(i.mnemonic))
        adv = sum(i.size for i in got)
        if adv < len(code) - off:
            out.append(".word")
            adv += step
        off += max(adv, step)
    return out


def contains(hay, needle):
    """Does the reference block contain our whole function, uninterrupted?

    A reference `.s` split often runs a little past the routine we care about -- their file holds a
    tail helper, or an `arm_func_end` is missing -- so requiring equal lengths would reject genuine
    identifications. Containment is the honest test: every one of our instructions, in order, with
    nothing of ours missing.
    """
    n = len(needle)
    return n > 0 and any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def similarity(a, b):
    """Fraction of the longer sequence covered by the longest common subsequence of mnemonics."""
    if not a or not b:
        return 0.0
    if contains(b, a):
        return 1.0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(cur[j], prev[j + 1]))
        prev = cur
    return prev[-1] / max(len(a), len(b))


def name_candidates(name, idx):
    if name.startswith("func_"):
        return []
    bare = name.lstrip("_")
    hits = []
    for ref, entries in idx.items():
        rb = ref.lstrip("_")
        if ref == name or (len(rb) > 4 and (rb in bare or bare in rb)):
            hits.extend(dict(e, ref=ref) for e in entries)
    return hits


def shape_candidates(seq, idx, floor=0.90):
    """Every reference function whose instruction sequence is close to ours, name ignored.

    This is what finds the 973 unmatched functions that carry no name. Length is filtered first
    because a sequence that differs by more than a tenth in length cannot clear the floor, and the
    subsequence comparison is far too slow to run against every reference definition.
    """
    hits = []
    # Below a dozen instructions a "90% similar" sequence means almost nothing -- half the stubs in
    # any decomp are `push/bl/pop/bx` -- so short functions must match exactly or not at all.
    exact_only = len(seq) < 12
    for e in by_length(idx, len(seq)):
        s = 1.0 if contains(e["seq"], seq) else 0.0 if exact_only else similarity(seq, e["seq"])
        if s >= floor:
            hits.append(dict(e, sim=s))
    return sorted(hits, key=lambda h: -h["sim"])


_BUCKETS = {}


def by_length(idx, n):
    """Reference definitions whose length could possibly clear the floor.

    142k definitions times 1101 of ours is 156 million comparisons if every candidate is visited,
    so length is bucketed once and only the plausible band is walked. A sequence differing by more
    than a seventh in length cannot reach 90% similarity, and containment allows the reference to
    be longer, so the band is asymmetric.
    """
    if not _BUCKETS:
        seen = set()
        for ref, entries in idx.items():
            for e in entries:
                # Identical stubs repeat by the thousand across four decomps; keeping one copy of
                # each distinct sequence is what makes the short-function band tractable.
                key = (ref, tuple(e["seq"]))
                if e["n"] and key not in seen:
                    seen.add(key)
                    _BUCKETS.setdefault(e["n"], []).append(dict(e, ref=ref))
    lo, hi = int(n * 0.85) - 4, int(n / 0.85) + 4
    return [e for k in range(lo, hi + 1) for e in _BUCKETS.get(k, ())]


def verdict(sim):
    return "EXACT" if sim >= 0.999 else "CLOSE" if sim >= 0.95 else "PARTIAL"


def report(mod, a, size, name, isa, idx, quiet=False):
    seq = our_seq(mod, a, size, isa)
    hits = shape_candidates(seq, idx)
    seen = {(h["proj"], h["file"], h["ref"]) for h in hits}
    for c in name_candidates(name, idx):
        if (c["proj"], c["file"], c["ref"]) not in seen and c["seq"]:
            c["sim"] = similarity(seq, c["seq"])
            hits.append(c)
    # Instruction shape cannot tell one BIOS stub from another -- every one of them is `swi N; bx
    # lr`, so all seventeen tie at 100% and whichever the index happened to store first wins. Break
    # the tie on the name, which is the only thing that distinguishes them.
    bare = name.lstrip("_").lower()
    hits.sort(key=lambda h: (-h["sim"], not (bare and bare in h["ref"].lower())))
    if not quiet:
        print(f"0x{a:08x} {name} ({size}B, {isa}, {len(seq)} instructions)")
        for h in hits[:6]:
            print(f"   {verdict(h['sim']):<7} {h['sim']*100:5.1f}%  "
                  f"{h.get('kind', 'C'):<4} {h['ref']:<26} {h['proj']}/{h['file']}")
        if not hits:
            print("   NEEDS-RESEARCH -- no reference implements this. Decompile it as C.")
    return hits


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sweep"
    if cmd == "index":
        return build_index()
    idx = load_index()
    if cmd == "show":
        ref, name = sys.argv[2], sys.argv[3]
        for e in idx.get(name, []):
            if e["file"].endswith(ref) or ref in e["file"]:
                print(e["text"])
                return 0
        print("not indexed")
        return 1
    if cmd == "match":
        mod, addr = sys.argv[2], sys.argv[3]
        a = int(addr, 16)
        hit = next((f for f in our_functions(mod) if f[0] == a), None)
        if not hit:
            sys.exit("not an unmatched function in this module")
        report(mod, hit[0], hit[1], hit[2], hit[3], idx)
        return 0
    mod = sys.argv[2] if len(sys.argv) > 2 else "main"
    fns = our_functions(mod)
    if len(sys.argv) > 3:
        # Restrict to an address list, so the library bands can be searched first without
        # pretending they are the only place a reference match can live.
        want = {int(w, 16) for w in re.findall(r"[0-9a-fA-F]{8}", open(sys.argv[3]).read())}
        fns = [f for f in fns if f[0] in want]
    # ONE SWEEP PER MODULE. Two sweeps of the same module interleave their lines into one report,
    # and if they were started against different indexes the result is a file that looks like
    # evidence and is not: a run left over from before splitter dumps were excluded put 39 phantom
    # NNS "matches" into ident_main.txt, all of which are NEEDS-RESEARCH against the real index.
    lock = f"{SP}/wlog/.sweep_{mod}.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        sys.exit(f"REFUSING: a sweep of {mod} is already running (remove {lock} if it is stale)")
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    import atexit
    atexit.register(lambda: os.path.exists(lock) and os.remove(lock))

    print(f"{len(fns)} unmatched in {mod}; identifying by instruction shape", flush=True)
    found = 0
    for a, size, name, isa in fns:
        try:
            hits = report(mod, a, size, name, isa, idx, quiet=True)
        except Exception as exc:
            print(f"ERROR   0x{a:08x} {exc}", flush=True)
            continue
        if not hits:
            continue
        found += 1
        h = hits[0]
        print(f"{verdict(h['sim']):<7} {h['sim']*100:5.1f}%  0x{a:08x} {name[:34]:<34} {size:5d}B  "
              f"{'ASM' if h['asm'] else 'C'}  {h['ref']} <- {h['proj']}/{h['file']}", flush=True)
    print(f"\n{found} identified, {len(fns) - found} NEEDS-RESEARCH", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
