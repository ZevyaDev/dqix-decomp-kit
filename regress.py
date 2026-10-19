#!/usr/bin/env python3
"""REGRESSION tests for the helper scripts, pinning behaviour that was fixed by hand.

    python regress.py

pipetest.py tests the GATE against the ROM. This tests the scripts AROUND it -- the ranking, the
prompt, the verdict parsing, the placement filter, the colour sweep -- because those were edited
repeatedly on 08-20 with nothing but selfcheck's static invariants as a guard, and selfcheck cannot
see behaviour. Every case below encodes a fault that actually happened and cost something, so a
failure here means a real regression, not a style drift.

Each test states the fault it detects. If you change a script and a test fails, the question is
which of the two is wrong -- do not delete the test to make the suite green.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import importlib.util
import json
import os
import re
import sys
import tempfile
import time

SP = _kp.SP
KIT = _kp.KIT
sys.path.insert(0, KIT)

FAILED = []
PASSED = [0]
CHECKS = []
TIMES = f"{SP}/wlog/regress_times.json"


def check(name, fault):
    def deco(fn):
        CHECKS.append((name, fault, fn))
        return fn
    return deco


def run_check(name, fault, fn):
    start = time.perf_counter()
    try:
        bad = fn()
    except Exception as e:                       # a test that explodes is a failure
        bad = "raised %s: %s" % (type(e).__name__, e)
    if bad:
        FAILED.append((name, fault, bad))
        print("FAIL  %s: %s" % (name, bad))
        print("      the fault it detects: %s" % fault)
    else:
        PASSED[0] += 1
        print("ok    %s" % name)
    sys.stdout.flush()
    return time.perf_counter() - start


def run_shard(indices):
    times = {CHECKS[i][0]: run_check(*CHECKS[i]) for i in indices}
    print("RESULT " + json.dumps({"passed": PASSED[0], "failed": FAILED, "times": times}))


def plan(shards):
    try:
        with open(TIMES, encoding="utf-8") as fh:
            known = json.load(fh)
    except (OSError, ValueError):
        known = {}
    loads = [[0.0, []] for _ in range(shards)]
    for i in sorted(range(len(CHECKS)), key=lambda i: -known.get(CHECKS[i][0], 1.0)):
        slot = min(loads, key=lambda s: s[0])
        slot[0] += known.get(CHECKS[i][0], 1.0)
        slot[1].append(i)
    return [sorted(s[1]) for s in loads if s[1]], known


def run_checks(shards=None):
    import subprocess
    groups, known = plan(shards or max(4, min(16, (os.cpu_count() or 8) - 2)))
    procs = [subprocess.Popen([sys.executable, os.path.abspath(__file__), "--shard", ",".join(map(str, g))],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              errors="replace") for g in groups]
    for k, p in enumerate(procs):
        out = p.communicate()[0]
        result = None
        for line in out.splitlines():
            if line.startswith("RESULT "):
                result = json.loads(line[7:])
            else:
                print(line)
        if result is None:
            FAILED.append(("shard %d/%d" % (k, len(procs)), "a regress shard must report its result",
                           "exit %s without a RESULT line: %s" % (p.returncode, out.strip()[-300:])))
            continue
        PASSED[0] += result["passed"]
        FAILED.extend(tuple(f) for f in result["failed"])
        known.update(result.get("times", {}))
    try:
        with open(TIMES, "w", encoding="utf-8") as fh:
            json.dump(known, fh)
    except OSError:
        pass
    return FAILED


def record(nbad=0):
    line = "%d passed, %d failed" % (PASSED[0], len(FAILED) + nbad)
    _kp.record("regress", ["FAIL  %s: %s" % (name, bad) for name, _fault, bad in FAILED] + [line])
    return line


def load(mod):
    spec = importlib.util.spec_from_file_location("_r_" + mod, f"{KIT}/{mod}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@check("decomment keeps the KEEP-NAME marker and the region tags",
       "a staged file stripped by pad/decomment.py lost `// KEEP-NAME`, so integrate no longer "
       "delinked it under its mangled symbol; landpr's strip took `// JPN:` off #151's JPN-only files")
def _decomment_keeps_markers():
    src = ("// KEEP-NAME: the ROM symbol here is the mangled C++ name, not a func_ tag.\n"
           "// USA: 0x02000000\n// JPN: func_02043014\n// note\nint f() { return 0; } /* x */\n")
    out = load("pad/decomment").strip(src)
    if ("// KEEP-NAME" not in out or "// USA:" not in out or "// JPN:" not in out or "note" in out
            or "/*" in out):
        return "stripped to %r" % out
    return None


@check("regionsync restores only the modules a delink or link error names, not the whole port",
       "an ov029 header error and an ov027 .data range error named no `Check` line, so landpr's EUR port of "
       "33 files was restored whole and EUR got none of #254-#267's matches")
def _regionsync_names_error_modules():
    R = load("regionsync")
    log = ("[WARN ] No module for relocation from 0x02216c94 in overlay 31 to 0x02249b54\n"
           "Error: config\\eur\\arm9\\overlays/ov029/delinks.txt:7: section .text does not exist in this file's header:\n"
           "Error: Last symbol '@wstringBase0' in section '.data' of file 'src/NitroSDK/Overlay_27/f.cpp' has the range\n"
           "[ERROR] Imported symbol @73 at 0x022460dc in overlay 30 is local, it cannot be used in relocation\n"
           "Error: Failed to delink 'main_26', see errors above\n")
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        os.makedirs(os.path.join(d, "config/eur/arm9/overlays/ov027"))
        with open(os.path.join(d, "config/eur/arm9/overlays/ov027/delinks.txt"), "w", encoding="utf-8") as fh:
            fh.write("src/NitroSDK/Overlay_27/f.cpp:\n    complete\n    .text start:0x021dc680 end:0x021dc864\n")
        os.chdir(d)
        try:
            got = R.failed_folders(log, "eur")
        finally:
            os.chdir(cwd)
    want = {"config/eur/arm9/overlays/ov029", "config/eur/arm9/overlays/ov027", "config/eur/arm9/overlays/ov030",
            "config/eur/arm9"}
    if got != want:
        return "named %r, want %r" % (sorted(got), sorted(want))
    return None


@check("landpr strips contribution comments from assembly sources too",
       "#259 and #265 carried 146 comment lines in .s files that landpr's .c/.cpp-only strip let through")
def _landpr_strips_asm():
    import subprocess
    L = load("landpr")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        def git(*args):
            subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
                            *args], capture_output=True, text=True, check=True)
        git("init", "-q", "-b", "main")
        git("config", "user.name", "t")
        git("config", "user.email", "t@t")
        os.makedirs(os.path.join(d, "src"))
        path = os.path.join(d, "src", "a.s")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\t.arm\n")
        git("add", "-A")
        git("commit", "-qm", "x")
        tip = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("// why this is asm\n\t.arm\n// USA: func_02000000\nf:\n\tbx lr\n")
        git("commit", "-qam", "y")
        L.strip_comments(d, tip)
        with open(path, encoding="utf-8") as fh:
            out = fh.read()
    if "why" in out or "// USA: func_02000000" not in out:
        return "landpr left %r" % out
    return None


def _evo_score(sites_list):
    argv, sys.argv = sys.argv, ["evo_score.py", "main", "02011b68"]
    try:
        es = load("pad/evo_score")

        def fake_diff(ov, addr, src, sec=None, out=None, diagnose=True, ctx=None, maxruns=None):
            kept = sites_list[:maxruns or 12]
            lost = len(sites_list) - len(kept)
            text = ("BYTEDIFF %d bytes in %d run(s), slot=0x44c isa=thumb\n"
                    % (len(sites_list), len(sites_list)) + "".join(kept)
                    + (" ... %d more run(s) suppressed (raise WDIFF_MAXRUNS)\n" % lost if lost else ""))
            out.extend(text.rstrip("\n").split("\n"))
            return 0

        es._wdiff = lambda: type("_wdiff", (), {"diff": staticmethod(fake_diff)})
        return es
    finally:
        sys.argv = argv


def _site(off, target, ours):
    return " *0x%04x  %-34s| %s\n" % (off, target, ours)


_HEAD = [_site(o, "ldr r%d,[r3]" % i, "ldr r%d,[r4]" % i)
         for i, o in enumerate((0x0048, 0x0090, 0x0118, 0x012c, 0x0150, 0x0164, 0x0190,
                                0x01b0, 0x01d0, 0x01f0, 0x0210, 0x0230, 0x0250, 0x0270))]


@check("evo_score's sig separates candidates that are wrong in the same places",
       "sig was built from the OFFSETS of the differing runs and never from what differs there, so "
       "c_frameorder.cpp and c_splitframe.cpp scored the same fitness 126 and the same sig "
       "LOOP-SHAPE@48,90-c4,118,12c-130,150,164-170+3 while emitting different code (the frame "
       "slots permute: recBase 0->8, fresh 8->0). dqix-evolve.js select() keeps one file per "
       "signature, so the second residue was discarded unmeasured")
def _evo_sig_separates_same_offsets():
    a = _HEAD[:2]
    b = [_HEAD[0], _site(0x0090, "ldr r0,[r3]", "ldr r0,[r5]")]
    sa = _evo_score(a).sites("x.cpp")[0]
    sb = _evo_score(b).sites("x.cpp")[0]
    if sa == sb:
        return "same offsets, different instructions, same sig: %s" % sa
    return None


@check("evo_score's sig separates candidates that differ only past the sixth site",
       "sig named the first 6 differing runs and folded the rest into `+N` -- a count with no "
       "position and no content -- and wdiff prints only WDIFF_MAXRUNS (12) runs, so two "
       "candidates wrong in the same first six places but differently after that were one "
       "signature")
def _evo_sig_covers_every_site():
    a = _evo_score(_HEAD).sites("x.cpp")[0]
    b = _evo_score(_HEAD[:-1] + [_site(0x0270, "ldr r13,[r3]", "ldr r13,[r5]")]).sites("x.cpp")[0]
    if a == b:
        return "differing site 14 of 14, sig does not: %s" % a
    return None


@check("evo_score's sig keeps the readable offset prefix boards already carry",
       "sig is a required field of dqix-evolve.js's scored-file schema and workers' board.tsv "
       "files hold sigs in the old form; a replacement format would leave every one of them "
       "unreadable")
def _evo_sig_keeps_prefix():
    sig, nbytes = _evo_score(_HEAD).sites("x.cpp")
    old = "48,90,118,12c,150,164+8"          # the offset list in the format boards already carry
    if not sig.startswith(old + "~"):
        return "readable prefix %r lost or reworded: %s" % (old, sig)
    if not re.fullmatch(r"[0-9a-f]{8}", sig[len(old) + 1:]):
        return "disambiguator is not a short hex tail: %s" % sig
    if nbytes != 14:
        return "BYTEDIFF not parsed: %r" % nbytes
    return None


# ---------------------------------------------------------------- resumable.py

@check("distances() ignores hex tails and size deltas",
       "reading '9/0xb4 bytes diff' as 4 bytes told a worker a barely-started function was nearly "
       "done; reading 'SIZE+4' or '-4 vs slot' as a diff distance did the same")
def _distances():
    R = load("resumable")
    cases = [
        ("regalloc cascade, 142/340 bytes best", [142]),
        ("extremely close (9/0xb4 bytes diff, mov#0xc), stuck after 7 tries", [9]),
        # A bare hex size with no numerator is the case that actually exercises the lookbehind:
        # in the line above, the `N/0xM bytes` alternative consumes the span before the tail of
        # the hex literal can be misread, so that case passes even with the guard removed.
        ("residual 0xb4 bytes diff", []),
        ("best 0x2c bytes", []),
        ("1 byte at 0x68 (asr vs lsr)", [1]),
        ("accum not cached; 140b/8runs, mine -4 vs slot", [140]),
        ("SIZE 0xc8 vs 0xd0 (8 bytes short), missing r3/r5", []),
        ("SIZE+4/332, if-conversion, 220 diff bytes", [220]),
    ]
    for text, want in cases:
        got = R.distances(text)
        if got != want:
            return "distances(%r) = %r, want %r" % (text, got, want)
    return None


@check("a spent-lever verdict deprioritises but never removes an address",
       "excluding 'no C form' / 'colorsweep inert' addresses wrote off matchable work; 30 functions "
       "were skiplisted that way before, and the standing rule is that only genuine needs-asm defers")
def _no_exclusion():
    R = load("resumable")
    out, held = R.rows()
    addrs = {r[4] for r in out}
    for _why, _mod, a, _reason in held:
        if a not in addrs:
            return "address %s is held but absent from the queue" % a
    if held and not any(r[0] == 1 for r in out):
        return "held addresses are not carrying the deprioritisation flag"
    return None


@check("gated/ is a dispatch pool",
       "wgate writes a source to gated/ ONLY on a MATCH; 801 proven sources accumulated there and "
       "112 stayed uncommitted because no dispatcher read the directory")
def _gated_pool():
    R = load("resumable")
    if not any(p.startswith("gated/") for p in R.POOLS):
        return "POOLS does not include gated/"
    if R.rank_of("/x/gated/main/0209ed0c.cpp") >= R.rank_of("/x/hold_main/0209ed0c.cpp"):
        return "a proven gated/ source does not outrank an ordinary hold_ prior"
    return None


# ---------------------------------------------------------------- mkresume.py

@check("the resume prompt hands over prior verdicts without authorising a skip",
       "the block used to end with 'SKIP immediately ... a cheap early SKIP is worth more than a "
       "full-cap grind', and three of four workers quoted it back instead of trying anything")
def _ruled_out():
    M = load("mkresume")
    if KIT not in sys.path:
        sys.path.insert(0, KIT)
    import resumable
    real = resumable.skips
    resumable.skips = lambda: {"021e6448": (None, "SKIP REGPERM 142 | declaration order inert")}
    try:
        block = M.ruled_out(SP, "021e6448")
    finally:
        resumable.skips = real
    if not block.strip():
        return "no ruled-out block produced for an address with recorded verdicts"
    low = block.lower()
    for banned in ("skip immediately", "cheap early skip", "not progress -- it is the prior"):
        if banned in low:
            return "block still contains skip-authorising text: %r" % banned
    if "matchable" not in low:
        return "block no longer asserts the function is matchable"
    return None


# ---------------------------------------------------------------- fix_verdicts.py

@check("a PASS sign-off counts as a match, a SKIP quoting MATCH does not",
       "resume_sweep classified on MATCH|matched only, so a worker finishing with 'PASS <addr>' was "
       "filed as a miss -- and DONE is what stops an address being served again")
def _verdicts():
    F = load("fix_verdicts")
    d = tempfile.mkdtemp()
    cases = [("PASS 0203af48", "MATCH"), ("MATCH", "MATCH"),
             ("SKIP 021f7b98 no MATCH found, 19 bytes", "miss"),
             ("BYTEDIFF 8 bytes", "miss")]
    for i, (result, want) in enumerate(cases):
        p = f"{SP}/wlog/resume_zz{i}_0000000{i}.json"
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"result": result}, fh)
        try:
            got = F.verdict_of("zz%d" % i, "0000000%d" % i)
            if got != want:
                return "result %r classified %s, want %s" % (result, got, want)
        finally:
            os.remove(p)
    return None


# ---------------------------------------------------------------- colorsweep.py

@check("colorsweep ranks a mnemonic mismatch worse than a byte",
       "byte-count scoring rejected the only move that led to a match: on 0209ed0c the CORRECT "
       "'i < total' scored 16 against the wrong 'total > i' at 15, so the sweep converged on the "
       "wrong side of the valley and reported 'inert'")
def _score_ranking():
    C = load("colorsweep")
    src = open(f"{KIT}/colorsweep.py", encoding="utf-8").read()
    if "mnem * mnem_w" not in src or "mnem_w = slot + 1" not in src or "over_w = mnem_w * (slot // 4 + 2)" not in src:
        return "score() no longer weights size above mnemonics above bytes"
    if not re.search(r"\\s\*\\\*\\s\*0x|\*\\s\*0x", src):
        return "score() no longer anchors the diff-row parse (wdiff's legend line has '*' and '|')"
    slot = 10204
    mnem_w = slot + 1
    over_w = mnem_w * (slot // 4 + 2)
    worst_right = (slot // 4) * mnem_w + slot       # every instruction a wrong mnemonic, every byte wrong
    best_over = 0 * mnem_w + 0 + over_w             # oversize but otherwise identical
    if not worst_right < best_over:
        return "an oversize candidate can still outrank a right-sized one (0217e6b0: --apply wrote a 265-byte oversize over a 12-byte base)"
    if not worst_right + over_w < 10 ** 9:
        return "the worst real score reaches FAILSCORE"
    if not (0 * mnem_w + slot) < (1 * mnem_w + 0):
        return "one wrong mnemonic can still score better than a large byte diff"
    C._W["mnem"], C._W["over"] = mnem_w, over_w
    if C._fmt_score(2 * mnem_w + 37 + over_w) != "37 bytes / 2 wrong mnemonic(s) +oversize":
        return "_fmt_score no longer decodes the composite it is given: %r" % C._fmt_score(
            2 * mnem_w + 37 + over_w)
    return None


@check("r11 hoists a block-scoped declaration to function scope, at every position",
       "mwcc ranks callee-saved candidates by function-scope declaration order and an inner-block "
       "declaration ranks after all of them; r8 only lifts to the head of its OWN block, so the "
       "form that closed 0209ed0c was unreachable. Hoisting BELOW the other declaration is inert, "
       "so position must be enumerated")
def _r11():
    C = load("colorsweep")
    text = ('extern "C" ARM void f(char* p)\n{\n    int i;\n\n'
            '    if (p) {\n        unsigned char total = *(unsigned char*)(p + 0x8e07);\n'
            '        i = total;\n    }\n}\n')
    got = C.r11_decl_to_function_scope(text)
    if not got:
        return "no candidate produced (a cast initialiser must not be rejected -- r8's guard was)"
    if len(got) < 2:
        return "only %d position(s) generated; both above and below `int i;` are needed" % len(got)
    above = [c for _l, c in got if c.index("unsigned char total;") < c.index("int i;")]
    if not above:
        return "never places the hoisted declaration ABOVE the existing one, the case that matched"
    for _l, cand in got:
        if "total = *(unsigned char*)(p + 0x8e07);" not in cand:
            return "the assignment was moved; r11 must move only the declaration"
    return None


@check("neighbours() interleaves the rules instead of concatenating them",
       "a file with many early-rule sites spent the whole budget before a later rule was scored "
       "once: 150 compiles on ov023:021fa2f4 never reached the rule that cracked it. Every rule "
       "must get a turn before any rule gets a second")
def _interleaved():
    C = load("colorsweep")
    text = ('extern int data_ov023_021fea0c[];\n'
            'void f(int a, int b, int c, int d) {\n'
            '    int w = a + b;\n    int x = b + c;\n    int y = c + d;\n    int z = d + a;\n'
            '    int* p = &data_ov023_021fea0c[w];\n    int q = x + y + z;\n}\n')
    labels = [l for l, _ in C.neighbours(text)]
    if not any(l.startswith("inline1:") for l in labels):
        return "r22 produced nothing on a text that clearly holds its shape"
    first = next(i for i, l in enumerate(labels) if l.startswith("inline1:"))
    producing = sum(1 for rule in C.RULES[:-1] if rule(text))
    if first >= producing:
        return ("the first r22 candidate is at position %d of %d; with one candidate per rule per "
                "round it must appear within the first round (%d)" % (first, len(labels), producing))
    return None


@check("r23 turns an early-return guard into a single-exit result variable",
       "the ROM materialises a return constant BEFORE the compare (`mov r0,#0` then `pophs`) while "
       "an early `return 0;` lets mwcc predicate it (`movhs r0,#0`). main:020a1bb4 and its twin "
       "020a1ccc each carried that one instruction as part of a 33/62-byte residue")
def _r23():
    import colorsweep
    body = ("// USA: func_1\nARM int f(unsigned int id) {\n"
            "    if (id >= 0x23) {\n        return 0;\n    }\n"
            "    g();\n    return 1;\n}")
    got = dict(colorsweep.r23_single_exit_result(body))
    if not got:
        return "r23 no longer fires on the early-return guard shape"
    only = list(got.values())[0]
    for want in ("int _r23 = 0;", "if (!(id >= 0x23)) {", "_r23 = 1;", "return _r23;"):
        if want not in only:
            return "r23 output is missing %r" % want
    ptr = ("// USA: func_1\nARM char* f(int i) {\n"
           "    if (i) {\n        return 0;\n    }\n    g();\n    return buf;\n}")
    if colorsweep.r23_single_exit_result(ptr):
        return "r23 fires when the final return is not an integer literal, but it types _r23 as int"
    if colorsweep.r23_single_exit_result(only):
        return "r23 fires on its own output, so a sweep can nest the rewrite"
    if colorsweep.r23_single_exit_result not in colorsweep.RULES:
        return "r23 is defined but not in RULES, so no sweep will ever try it"
    return None


@check("r22 folds an adjacent single-use local and refuses every unsafe shape",
       "r22 is the only rule that changes the expression TREE rather than statement order, which is "
       "why it can reach the scratch-register family nothing else can -- but folding a local whose "
       "value is read twice, or across an intervening statement, silently changes what the code "
       "computes, and a wrong 'improvement' that still compiles is the worst outcome the sweep has")
def _r22():
    import colorsweep
    body = ("extern \"C\" ARM int f(int* p) {\n"
            "    int a = p[0] + 3;\n"
            "    int b = a * 2;\n"
            "    return b;\n}")
    got = dict(colorsweep.r22_inline_single_use(body))
    if "inline1:a" not in got or "int b = (p[0] + 3) * 2;" not in got["inline1:a"]:
        return "r22 no longer folds an adjacent single-use local"
    twice = ("extern \"C\" ARM int f(int* p) {\n"
             "    int a = p[0] + 3;\n"
             "    int b = a * a;\n"
             "    return b;\n}")
    if any(l == "inline1:a" for l, _ in colorsweep.r22_inline_single_use(twice)):
        return "r22 folds a local that is read twice, which duplicates the computation"
    apart = ("extern \"C\" ARM int f(int* p) {\n"
             "    int a = p[0] + 3;\n"
             "    p[1] = 0;\n"
             "    return a;\n}")
    if any(l == "inline1:a" for l, _ in colorsweep.r22_inline_single_use(apart)):
        return "r22 folds across an intervening statement, so a side effect can be reordered"
    if colorsweep.RULES[-1] is not colorsweep.r17_decl_permute:
        return "r17_decl_permute is no longer last, so the widest rule now starves the others"
    if colorsweep.r22_inline_single_use not in colorsweep.RULES:
        return "r22 is defined but not in RULES, so no sweep will ever try it"
    return None


@check("the scheduler serves every unmatched function, not only the ones inside SIZE_BOUNDS",
       "claim.stratify() filtered to SIZE_BOUNDS, which starts at 257, and it was applied to the "
       "MEDIUM band (65-256) as well -- so every medium function fell outside every bound and the "
       "band came back EMPTY. `PULL_BAND=med` reported `pool drained` with 331 medium functions "
       "waiting in main, and mixed round-robin never served a medium function at all: 765 of them, "
       "749 never once attempted, unreachable. A scheduler that drops work reports success")
def _stratify_total():
    C = load("claim")
    src = open(os.path.join(KIT, "claim.py"), encoding="utf-8").read()
    if "not any(lo <= r[1] <= hi for lo, hi in SIZE_BOUNDS)" not in src:
        return "stratify() no longer keeps items that fall outside every SIZE_BOUNDS range"
    with tempfile.TemporaryDirectory() as d:
        sp, C.SP = C.SP, d
        try:
            pool = C.unmatched("main")
        finally:
            C.SP = sp
    if not pool:
        return "claim.unmatched('main') is empty -- the band filter is dropping work again"
    return None


@check("colorsweep's compile-failure sentinel cannot collide with a real score",
       "score() returns mnemonic_mismatches*10000 + bytes + oversize, and the sentinel was 10**6 -- "
       "so any base with 100+ differing mnemonics scored ABOVE it and the sweep refused to start, "
       "printing `base does not compile cleanly against the slot` about a source that compiles. "
       "100 wrong mnemonics is ordinary on a 250-instruction function's first pass, so this "
       "silently disabled colorsweep on the whole large band; three verdicts in one night quote "
       "that false message. main:02035178 scored 1581602 and was called a compile failure")
def _failscore():
    C = load("colorsweep")
    worst = 2600 * 10000 + 999 + 1000          # every instruction wrong, oversize, on the biggest
    if C.FAILSCORE <= worst:                   # function in the ROM
        return "FAILSCORE %d is reachable by a real score (worst plausible %d)" % (C.FAILSCORE, worst)
    src = open(os.path.join(KIT, "colorsweep.py"), encoding="utf-8").read()
    if "10 ** 6" in src:
        return "a bare 10**6 sentinel is still in colorsweep.py"
    if src.count("FAILSCORE") < 5:
        return "FAILSCORE is not used at every failure return and guard"
    return None


def _serial_sweep(C, base, module, addr, depth, budget):
    import hashlib
    out, spent = [], 0
    best_bytes, head = C.score(base, module, addr, "base")
    spent += 1
    out.append("base: %s" % head)
    if best_bytes == 0 or best_bytes >= C.FAILSCORE:
        return out, base
    beam = [(best_bytes, base, "")]
    best = (best_bytes, base, "")
    tried = {hashlib.md5(base.encode()).hexdigest()}
    for level in range(depth):
        scored = []
        for _, text, trail in beam:
            for label, cand in C.neighbours(text):
                h = hashlib.md5(cand.encode()).hexdigest()
                if h in tried:
                    continue
                tried.add(h)
                if spent >= budget:
                    break
                nbytes, _hd = C.score(cand, module, addr, "s%d" % spent)
                spent += 1
                if nbytes >= C.FAILSCORE:
                    continue
                path = (trail + " > " + label).strip(" >")
                scored.append((nbytes, cand, path))
                if nbytes < best[0]:
                    best = (nbytes, cand, path)
                    out.append("  %s  <- %s" % (C._fmt_score(nbytes), path))
                if nbytes == 0:
                    break
            if best[0] == 0 or spent >= budget:
                break
        if best[0] == 0 or spent >= budget or not scored:
            break
        scored.sort(key=lambda t: t[0])
        beam = scored[:3]
    out.append("RESULT %s after %d compiles: %s"
               % ("MATCH" if best[0] == 0 else C._fmt_score(best[0]), spent, best[2] or "(no change)"))
    return out, (best[1] if best[0] < best_bytes else base)


@check("colorsweep's parallel scoring explores and ranks exactly what the serial loop did",
       "every candidate was one `python wdiff.py` process run one at a time, 0.77 s against a 0.11 s "
       "compile, so a 400-compile sweep took 5 minutes. Scoring several at once is only safe if the "
       "candidate order, the budget cut, the match stop and the winner stay those of the serial loop: "
       "a sweep that explores a different set loses matches silently")
def _colorsweep_parallel_is_serial():
    import concurrent.futures
    import contextlib
    import hashlib
    import io
    import shutil
    C = load("colorsweep")
    if not hasattr(C, "sweep") or not hasattr(C, "level_scores"):
        return "colorsweep has no sweep()/level_scores(); candidates are still scored one process at a time"
    if "sys.executable" in open(f"{KIT}/colorsweep.py", encoding="utf-8").read():
        return "colorsweep still launches a Python process per candidate"

    def neighbours(text):
        out = [("n%d" % j, "%s.%d" % (text, j)) for j in range(6)]
        return out + [("shared", "shared-%d" % (len(text) % 3))]

    def fake_score(goal):
        def score(text, module, addr, tag):
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            time.sleep((h % 4) / 1000.0)
            if text == "base":
                return 40, "BYTEDIFF base"
            if text.endswith(goal):
                return 0, "MATCH"
            if h % 9 == 0:
                return C.FAILSCORE, "COMPILE-FAIL"
            return 5 + h % 60, "BYTEDIFF"
        return score

    d = tempfile.mkdtemp(prefix="cs_par_")
    try:
        C.neighbours = neighbours
        for goal, depth, budget in ((".none", 3, 500), (".none", 3, 23), (".5.2", 3, 500),
                                    (".1.4.0", 4, 900), (".none", 2, 7)):
            C.score = fake_score(goal)
            want, want_text = _serial_sweep(C, "base", "main", "02000000", depth, budget)
            src = os.path.join(d, "c.cpp")
            open(src, "w", encoding="utf-8", newline="\n").write("base")
            buf = io.StringIO()
            with concurrent.futures.ThreadPoolExecutor(4) as pool, contextlib.redirect_stdout(buf):
                C.sweep(pool, 8, "main", "02000000", src, depth, budget, True)
            got = [l for l in buf.getvalue().splitlines() if not l.startswith("applied to ")]
            if got != want:
                return "goal %s depth %d budget %d: parallel printed %r, serial %r" % (
                    goal, depth, budget, got[-2:], want[-2:])
            if open(src, encoding="utf-8").read() != want_text:
                return "goal %s budget %d: parallel applied a different winner" % (goal, budget)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return None


@check("colorsweep scores in-process and leaves no candidate or object file behind",
       "score() wrote $SP/_cs_<pid>_<tag>.cpp per candidate and never deleted it: the state root "
       "held ~960k of them and every glob of $SP cost ~1 s")
def _colorsweep_no_leak():
    import shutil
    C = load("colorsweep")
    d = tempfile.mkdtemp(prefix="cs_leak_")
    W = C._wdiff()
    scr = W.SCR
    try:
        C.RUNROOT = os.path.join(d, "tmp")
        W.SCR = os.path.join(d, "compile")
        os.makedirs(W.SCR)
        text = open(f"{KIT}/regress_fixtures/GatherEnabledRecords_0209ed0c.cpp", encoding="utf-8").read()
        n, head = C.score(text, "main", "0209ed0c", "t")
        if not 0 < n < C.FAILSCORE:
            return "the 0209ed0c prior did not score as a near miss: %d %s" % (n, head)
        run = C._rundir()
        same = lambda p: os.path.normcase(os.path.abspath(p))
        if same(os.path.dirname(run)) != same(C.RUNROOT) or os.listdir(run):
            return "score() left %r in its run directory" % os.listdir(run)
        if os.listdir(W.SCR):
            return "wdiff left %r in its compile scratch" % os.listdir(W.SCR)
        C._drop_rundir()
        if os.listdir(C.RUNROOT):
            return "the run directory survived the sweep: %r" % os.listdir(C.RUNROOT)
    finally:
        W.SCR = scr
        C._drop_rundir()
        shutil.rmtree(d, ignore_errors=True)
    return None


@check("r24 puts the bigger arm first, and only when that is what it is asked to do",
       "six verdicts report `the ROM branches over the arm, mwcc predicates it`, and on "
       "ov031:0221474c writing the 3-instruction arm as the `if` instead of the `else` produced the "
       "missing `beq` -- 4 bytes SHORT became size-exact and colorsweep closed the rest. The rewrite "
       "is pure negation, so the danger is not correctness but firing on `else if` (which would drop "
       "a branch of the chain) or looping on its own output")
def _r24():
    C = load("colorsweep")
    src = ("void f(void){\n    if (n == 0) {\n        ok = 0;\n    } else {\n"
           "        p->a = n;\n        p->b = i;\n        ok = 1;\n    }\n}\n")
    got = C.r24_arm_invert(src)
    if not got:
        return "r24 does not fire on the 0221474c shape it was written for"
    cand = got[0][1]
    if "if (!(n == 0)) {" not in cand:
        return "r24 fired but did not negate the condition"
    if cand.index("p->a = n;") > cand.index("ok = 0;"):
        return "r24 fired but left the small arm first, which is the shape that predicates"
    if C.r24_arm_invert(cand):
        return "r24 fires on its own output, so a sweep can loop between the two orders"
    for bad, why in (
            ("void f(void){\n    if (a) {\n        x = 1;\n    }\n}\n", "an if with no else"),
            ("void f(void){\n    if (a) {\n        x = 1;\n        y = 2;\n    } else {\n"
             "        z = 3;\n    }\n}\n", "an else that is already the smaller arm"),
            ("void f(void){\n    if (a) {\n        x = 1;\n    } else if (b) {\n        z = 3;\n"
             "        w = 4;\n    }\n}\n", "an else-if chain")):
        if C.r24_arm_invert(bad):
            return "r24 fires on %s" % why
    if C.r24_arm_invert not in C.RULES:
        return "r24 is defined but not in RULES, so no sweep will ever try it"
    return None


@check("r16 never moves a statement across a brace or a control header",
       "on main:0201647c r16 lifted `node = node->next;` out of its while body, scored 599 against "
       "604 and offered an INFINITE LOOP as the sweep's best candidate -- a worker had to revert it "
       "by hand twice. A rewrite rule that changes meaning is worse than an inert one: it burns the "
       "budget and can hand a broken source to whoever trusts the score")
def _r16_blocks():
    C = load("colorsweep")
    loop = ("void f(void){\n    int a = 1;\n    int b = 2;\n    Node *node = head;\n"
            "    while (node) {\n        a = node->v;\n        b = a;\n"
            "        node = node->next;\n    }\n    int c = 3;\n}\n")
    for label, cand in C.r16_stmt_move(loop):
        body = cand.split("while (node) {", 1)
        if len(body) != 2:
            return "r16 %s destroyed the loop header" % label
        if "node = node->next;" not in body[1].split("}", 1)[0]:
            return "r16 %s moved the loop advance out of the while body" % label
    unbraced = ("void f(void){\n    int a = 1;\n    if (a)\n        a = 2;\n"
                "    int b = 3;\n    int c = 4;\n}\n")
    for label, cand in C.r16_stmt_move(unbraced):
        if cand.split("if (a)", 1)[1].lstrip().split("\n", 1)[0].strip() != "a = 2;":
            return "r16 %s changed the body of a brace-less if" % label
    flat = "void f(void){\n    int a = 1;\n    int b = 2;\n    int c = 3;\n    int d = 4;\n}\n"
    if not C.r16_stmt_move(flat):
        return "r16 no longer moves anything in straight-line code, so the fix made it inert"
    return None


@check("r18-r21 each fire on the shape they were written for, and only on it",
       "the four rules added from 02061c04 all rewrite ordinary-looking C, so a regex that is one "
       "character too greedy fires on comments or captures an unbalanced fragment and every "
       "candidate it proposes fails to compile -- which reads as `the rewrite made it worse` and "
       "silently spends the whole sweep budget. pad/ruleprobe.cpp carries one instance of each")
def _new_rules():
    C = load("colorsweep")
    probe = os.path.join(KIT, "pad", "ruleprobe.cpp")
    if not os.path.exists(probe):
        return "pad/ruleprobe.cpp is missing -- the rules have no shape to be tested against"
    text = open(probe, encoding="utf-8").read()
    want = {"r18_narrow_bind": "int _nb", "r19_ternary_split": "if (k == 3)",
            "r20_bool_materialise": "int _bm", "r21_cast_width": "Sink(k, 2);"}
    for name, needle in want.items():
        got = getattr(C, name)(text)
        if not got:
            return "%s produced no candidate for its own probe shape" % name
        if not any(needle in cand for _l, cand in got):
            return "%s fired but never emitted %r" % (name, needle)
        for _l, cand in got:
            if cand.count("(") != cand.count(")"):
                return "%s emitted a candidate with unbalanced parentheses" % name
    # and the rules must leave a source with none of their shapes alone
    clean = 'extern "C" ARM int g(int a) { return a; }\n'
    for name in want:
        if getattr(C, name)(clean):
            return "%s fires on a source containing none of its shapes" % name
    return None


@check("r43 casts a bitfield read that feeds an add",
       "`add rd, rn, rm, shift` folds ONE shift and a bitfield read ends in one, so a bare "
       "`fld->flag + i * 2` folds the extract and gives the other operand the register; a (short) "
       "cast blocks the fold and emits nothing (0218a9ec)")
def _r43():
    C = load("colorsweep")
    add = ('ARM void f(Box* fld, int i)\n{\n'
           '    Sink((short)(fld->flag + i * 2 + 0x7530));\n}\n')
    got = [c for _t, c in C.r43_short_cast_in_add(add)]
    if not any("(short)fld->flag" in c for c in got):
        return "r43 never cast the bitfield read that feeds the add"
    store = '    *(unsigned int*)((char*)&rec + 4) &= 0x01ffffff;\n'
    if C.r43_short_cast_in_add(store):
        return "r43 fired on a source containing none of its shape"
    return None


@check("r45 turns a masked OR into an accumulate so the OR lands in the word's register",
       "`W = (W & mask) | v` is a two-operand OR with no accumulator, so mwcc puts the result in "
       "the INSERTED value's register and the store then pushes the next statement's setup past "
       "it. Binding the value and accumulating with `&=` then `|=` reproduces the ROM's "
       "`orr rW, rW, rV, lsr #k` and its argument order (0209a104, 33 -> 27)")
def _r45():
    C = load("colorsweep")
    text = ('ARM void f(Rec* r, int x)\n{\n'
            '    r->raw = (r->raw & ~0xff000u) | ((unsigned int)x << 12);\n}\n')
    got = [c for _t, c in C.r45_accumulate_or(text)]
    if not got:
        return "r45 produced no candidate for a masked OR"
    if not any("r->raw &= ~0xff000u;" in c and "r->raw |= _acc" in c for c in got):
        return "r45 fired but never emitted the &= / |= accumulate pair"
    mirrored = text.replace("(r->raw & ~0xff000u) | ((unsigned int)x << 12)",
                            "((unsigned int)x << 12) | (r->raw & ~0xff000u)")
    if not C.r45_accumulate_or(mirrored):
        return "r45 only matches the mask-first spelling, not value-first"
    if C.r45_accumulate_or('ARM void f(Rec* r) { r->raw = r->other | 3; }\n'):
        return "r45 fires on an OR whose left operand is not the destination masked"
    return None


@check("r46 moves a loop counter's declaration among the pointer locals",
       "Callee-saved pointers came out as a register permutation that no ordering of their own "
       "declarations reached; where the loop COUNTER is declared decides which pointer's register "
       "it coalesces with. 02021578 needed its counter block moved between two pointers, 020227dc "
       "needed its for-scoped counter hoisted to a bare declaration, which emits nothing")
def _r46():
    C = load("colorsweep")
    block = ('extern "C" ARM void f(char* s) {\n'
             '    void* a;\n    char* b;\n    int i0;\n    int i1;\n'
             '    a = g();\n    b = h();\n'
             '    for (i0 = 0; i0 < 4; i0++) { k(a); }\n'
             '    for (i1 = 0; i1 < 4; i1++) { k(b); }\n}\n')
    got = [c for _t, c in C.r46_counter_position(block)]
    if not any(c.index("int i0;") < c.index("char* b;") for c in got):
        return "r46 never moved the counter block above a pointer declaration"
    scoped = ('extern "C" ARM void f(char* s) {\n'
              '    void* a = g();\n    char* b = h();\n'
              '    for (int i = 0; i < 4; i++) { k(a, b); }\n}\n')
    got = [c for _t, c in C.r46_counter_position(scoped)]
    if not any("int i;" in c and "for (i = 0;" in c for c in got):
        return "r46 never hoisted a for-scoped counter to a bare declaration"
    if C.r46_counter_position('extern "C" ARM int g(int a) {\n    int x;\n    x = a;\n'
                              '    return x;\n}\n'):
        return "r46 fires on a function whose int local is not a loop counter"
    return None


@check("r49 moves the assignment before a for loop into the body as its first statement",
       "LICM hoists a loop-invariant load written as the body's first statement to just after the "
       "for-init; written before the for, it lands before the init (021ebb90, with r50: 24 -> 14)")
def _r49():
    C = load("colorsweep")
    text = ('extern "C" ARM void f(struct N* node, int n) {\n'
            '    codes = node->codes;\n'
            '    for (j = 0; j < n; j++) {\n'
            '        g(codes[j]);\n'
            '    }\n}\n')
    got = [c for _t, c in C.r49_sink_into_loop(text)]
    want = '    for (j = 0; j < n; j++) {\n        codes = node->codes;\n        g(codes[j]);'
    if not any(want in c for c in got):
        return "r49 never moved the assignment into the loop body"
    if C.r49_sink_into_loop(text.replace("    codes = node->codes;\n", "    int k = 1;\n")):
        return "r49 moved a declaration into the loop body"
    return None


@check("r50 retypes locals that only ever hold 0 or 1 to unsigned char, each and all together",
       "Byte flags move the spill slots and the reload order around them; the row loop of 021ebb90 "
       "only matched with found and blocked BOTH unsigned char (with r49: 24 -> 14)")
def _r50():
    C = load("colorsweep")
    text = ('extern "C" ARM void f(int n) {\n'
            '    int found = 0;\n'
            '    int blocked = 0;\n'
            '    int count = 0;\n'
            '    if (n) found = 1;\n'
            '    if (n > 2) blocked = 1;\n'
            '    count++;\n'
            '    g(found, blocked, count);\n}\n')
    got = [c for _t, c in C.r50_narrow_flag(text)]
    if not any("unsigned char found = 0;" in c and "unsigned char blocked = 0;" in c for c in got):
        return "r50 never retyped both flags together"
    if any("unsigned char count" in c for c in got):
        return "r50 retyped a counter that is incremented"
    if C.r50_narrow_flag(text.replace("found = 1;", "found = n;").replace("blocked = 1;", "blocked = n;")):
        return "r50 retyped a local assigned a value other than 0 or 1"
    return None


@check("r51 retypes a spilled int local to short, together with the int callees assigned into it",
       "A short spill is reloaded with a full-word ldr that stays below the previous store, where an "
       "int's reload is hoisted above it (021ebb90, 14 -> MATCH). short alone adds a truncation after "
       "each call, so the callee's declaration returns short too")
def _r51():
    C = load("colorsweep")
    text = ('int Clamp(int id, float a);\n'
            'int Other(int id);\n'
            '// USA: func_f\n'
            'extern "C" ARM void f(struct V* d, int id) {\n'
            '    int sf = 0x1000;\n'
            '    int k = Other(id);\n'
            '    if (id) sf = Clamp(id, 1.0f);\n'
            '    d->x = Mul(d->x, sf);\n'
            '    d->y = Mul(d->y, sf);\n'
            '    g(k);\n}\n')
    got = C.r51_short_spill(text)
    if not got:
        return "r51 produced no candidate"
    c = got[0][1]
    if "short sf = 0x1000;" not in c or "short Clamp(int id, float a);" not in c:
        return "r51's first candidate is not the most-used local retyped together with its callee"
    if "short Other(" in c:
        return "r51 retyped a callee that is not assigned into the retyped local"
    if not any("short sf = 0x1000;" in c2 and "int Clamp(" in c2 for _t, c2 in got):
        return "r51 did not also offer the local alone"
    if C.r51_short_spill('extern "C" ARM void f(int* p) {\n    unsigned int u = 0;\n    g(u);\n}\n'):
        return "r51 fired on a local that is not a plain int"
    return None


@check("r52 inlines a once-assigned address local at every use and offers the compound form",
       "A named pointer to base + K changed the order mwcc hoists loop invariants (02065990, 40 -> 5)")
def _r52():
    C = load("colorsweep")
    text = ('// USA: func_f\n'
            'extern "C" ARM void f(unsigned char* self, int n) {\n'
            '    unsigned char* flags;\n'
            '    flags = self + 0x195b;\n'
            '    if (n) *flags = *flags | 1;\n'
            '    g(flags);\n}\n')
    got = C.r52_inline_address_local(text)
    if not got:
        return "r52 produced no candidate"
    if "*(self + 0x195b) |= 1;" not in got[0][1] or "flags" in got[0][1]:
        return "r52's first candidate is not the compound form with the local gone"
    if not any("*(self + 0x195b) = *(self + 0x195b) | 1;" in c for _t, c in got):
        return "r52 did not also offer the plain inlined form"
    if C.r52_inline_address_local(text.replace("g(flags);", "flags += 2;\n    g(flags);")):
        return "r52 inlined a local that is written twice"
    return None


@check("r53 turns a copy-modify-store into an in-place update and folds the copy's only shift",
       "02065990's last 5 bytes: `int old = F >> 4; F += step * 16;` -- the in-place update alone is inert")
def _r53():
    C = load("colorsweep")
    text = ('// USA: func_f\n'
            'extern "C" ARM void f(struct S* s, int step) {\n'
            '    int old = s->pos;\n'
            '    int cur = old + step * 16;\n'
            '    s->pos = cur;\n'
            '    g((cur >> 4) - (old >> 4));\n}\n')
    got = C.r53_update_in_place(text)
    if not got:
        return "r53 produced no candidate"
    c = got[0][1]
    if (not got[0][0].startswith("inplace+fold") or "int old = s->pos >> 4;" not in c
            or "s->pos += step * 16;" not in c or "- old)" not in c or "cur" in c):
        return "r53's first candidate is not the folded in-place update"
    if not any(t.startswith("inplace:") for t, _c in got):
        return "r53 did not also offer the unfolded in-place update"
    if C.r53_update_in_place(text.replace("int old = s->pos;", "int old = Get(s)->pos;")):
        return "r53 fired on a copy whose source calls a function"
    return None


@check("r56 drops the trailing argument from an extern \"C\" prototype and every call to it",
       "A stale pointer left in r1 at a call means the source passed one argument fewer (ov003:02178910)")
def _r56():
    C = load("colorsweep")
    text = ('extern "C" void g(int a, int b);\n'
            '// USA: func_f\n'
            'extern "C" ARM void f(int* p) {\n'
            '    g(p[0], h(p[1], 2));\n'
            '    g(1, 2);\n}\n')
    got = dict(C.r56_drop_last_arg(text))
    new = got.get("droparg:g")
    if not new:
        return "r56 produced no candidate"
    if 'extern "C" void g(int a);' not in new or "g(p[0]);" not in new or "g(1);" not in new:
        return "r56 did not drop the last parameter and argument everywhere"
    if C.r56_drop_last_arg('extern "C" void g(int a);\nvoid f() { g(1); }\n'):
        return "r56 fired on a one-parameter prototype"
    return None


@check("the body-scoped rules read a function whose opening brace is on its own line",
       "_r46_body only accepted `ARM f(...) {` on one line, so r51 never offered `short x` on the "
       "Allman-style ov023:021ddc98 and every body-scoped rule skipped 162 of 710 parked sources")
def _allman_body():
    C = load("colorsweep")
    text = ('// USA: func_f\n'
            'extern "C" ARM int f(short* p)\n'
            '{\n'
            '    int x;\n'
            '    x = p[0];\n'
            '    return x + p[1];\n'
            '}\n')
    got = dict(C.r51_short_spill(text))
    if "    short x;\n" not in got.get("shortspill:x@3", ""):
        return "r51 offered nothing on a brace-below function: %s" % sorted(got)
    return None


@check("r61 writes a zero memset as __clear",
       "The game zero-fills with __clear(buf, n), not memset(buf, 0, n) (main:02021f88)")
def _r61():
    C = load("colorsweep")
    text = ('// USA: func_f\n'
            'extern "C" ARM void f(char* p) {\n'
            '    char buf[16];\n'
            '    memset(buf, 0, sizeof(buf));\n'
            '    memset(p, 1, 4);\n'
            '}\n')
    got = C.r61_memset_to_clear(text)
    if not got:
        return "r61 produced no candidate"
    new = got[0][1]
    if "__clear(buf, sizeof(buf));" not in new or "memset(p, 1, 4);" not in new:
        return "r61 did not rewrite only the zero memset"
    if 'extern "C" void __clear(void* buf, int n);' not in new:
        return "r61 did not declare __clear"
    return None


@check("r60 marks a read-only extern table const",
       "A const byte table lets its ldrb hoist above a volatile store (ov005:0215b520)")
def _r60():
    C = load("colorsweep")
    text = ('extern "C" unsigned char data_tbl[];\n'
            'extern "C" int data_rw[];\n'
            '// USA: func_f\n'
            'extern "C" ARM int f(int i) {\n'
            '    data_rw[i] = 1;\n'
            '    return data_tbl[i];\n}\n')
    got = dict(C.r60_const_extern_table(text))
    if 'extern "C" const unsigned char data_tbl[];' not in got.get("constextern:data_tbl", ""):
        return "r60 did not const the read-only table"
    if "constextern:data_rw" in got:
        return "r60 consted a table that is written"
    ptrs = ('extern Cmd* data_q[9];\n'
            'extern "C" Cmd* data_w[2];\n'
            '// USA: func_f\n'
            'extern "C" ARM Cmd* f(int i) {\n'
            '    data_w[i] = 0;\n'
            '    return data_q[i];\n}\n')
    got = dict(C.r60_const_extern_table(ptrs))
    if "extern Cmd* const data_q[9];" not in got.get("constextern:data_q", ""):
        return "r60 did not const the read-only pointer table (main:020d22f4): %s" % sorted(got)
    if "constextern:data_w" in got:
        return "r60 consted a pointer table that is written"
    return None


@check("r59 stores a late value into an earlier local of the same type",
       "A fresh local swapped two callee-saved registers; reusing the loop's node fixed it (ov002:0216033c)")
def _r59():
    C = load("colorsweep")
    text = ('// USA: func_f\n'
            'extern "C" ARM void f(struct L* l) {\n'
            '    struct Node* node = l->head;\n'
            '    use(node);\n'
            '    struct Node* root = GetRoot(l);\n'
            '    use(root);\n'
            '}\n')
    got = dict(C.r59_reuse_earlier_local(text))
    new = got.get("reuse:root->node@4")
    if not new:
        return "r59 produced no candidate: %s" % sorted(got)
    if "    node = GetRoot(l);\n    use(node);" not in new:
        return "r59 did not rewrite the declaration and its uses"
    return None


@check("r58 gives a later loop its own counter",
       "Two loops sharing one counter share its register; the ROM had two (ov004:02169b4c)")
def _r58():
    C = load("colorsweep")
    text = ('// USA: func_f\n'
            'extern "C" ARM void f(int* a, int n) {\n'
            '    int i;\n'
            '    for (i = 0; i < n; i++) {\n'
            '        a[i] = 0;\n'
            '    }\n'
            '    for (i = 0; i < n; i++) {\n'
            '        a[i] += i;\n'
            '    }\n'
            '    g(i);\n'
            '}\n')
    got = C.r58_split_loop_counter(text)
    if not got:
        return "r58 produced no candidate"
    new = got[0][1]
    if "    int i2;\n" not in new or "for (i2 = 0; i2 < n; i2++) {\n        a[i2] += i2;" not in new:
        return "r58 did not rename the second loop's counter"
    if "for (i = 0; i < n; i++) {\n        a[i] = 0;" not in new or "g(i);" not in new:
        return "r58 touched code outside the second loop"
    return None


@check("r57 moves the call after an if block into its arm",
       "The ROM's blt skipped the clamp AND the call, so the call was inside the arm (ov002:0216acf0)")
def _r57():
    C = load("colorsweep")
    text = ('// USA: func_f\n'
            'extern "C" ARM void f(int* list, int idx, int count) {\n'
            '    if (idx >= count) {\n'
            '        idx = count - 1;\n'
            '    }\n'
            '    g(list, idx);\n'
            '}\n')
    got = C.r57_call_into_preceding_if(text)
    if not got:
        return "r57 produced no candidate"
    if "        idx = count - 1;\n        g(list, idx);\n    }\n" not in got[0][1]:
        return "r57 did not move the call inside the arm"
    if C.r57_call_into_preceding_if(text.replace("    g(list, idx);", "    x = 1;")):
        return "r57 fired on a statement that is not a call"
    return None


@check("r10 marks a never-written scalar local const",
       "`const short id = ...` fixed a function-wide r7/r8 swap on ov024:021eb5d0")
def _r10_scalar():
    C = load("colorsweep")
    text = ('// USA: func_f\n'
            'extern "C" ARM int f(short* p) {\n'
            '    short id = p[2];\n'
            '    int n = 0;\n'
            '    n += id;\n'
            '    return n;\n}\n')
    names = [n for n, _t in C.r10_const_local(text)]
    if not any(n.startswith("constscalar:id") for n in names):
        return "r10 did not offer const on a read-only scalar local"
    if any(n.startswith("constscalar:n") for n in names):
        return "r10 offered const on a local that is written later"
    return None


@check("r55 loads both values into their locals before transforming either",
       "Loading both first keeps the second load live across the first transform, which swaps their "
       "scratch registers (ov023:021e63bc); statement order, raw locals and getters are inert")
def _r55():
    C = load("colorsweep")
    text = ('// USA: func_f\n'
            'extern "C" ARM int f(short* pos) {\n'
            '    int x = (short)(pos[0] << 3) + 0xa;\n'
            '    int ytop = (short)(pos[1] << 3) + 0x10;\n'
            '    return x + ytop;\n}\n')
    got = C.r55_load_then_transform(text)
    if not got:
        return "r55 produced no candidate"
    want = ("    int x = pos[0];\n    int ytop = pos[1];\n    x = (short)(x << 3) + 0xa;\n"
            "    ytop = (short)(ytop << 3) + 0x10;\n")
    if want not in got[0][1]:
        return "r55 did not render load-then-transform"
    if C.r55_load_then_transform(text.replace("(pos[1] << 3)", "(pos[x] << 3)")):
        return "r55 fired when the second expression reads the first local"
    if C.r55_load_then_transform(text.replace("(short)(pos[0] << 3) + 0xa", "g(pos[0])")):
        return "r55 fired on an expression that calls a function"
    return None


@check("levercheck counts a LANDED evolve crack that core.md does not cite, and leverwatch fires on it once",
       "evolve agents never write levers.tsv, so leverwatch could only idle out during evolve work, a "
       "landed evolve crack never reached the promotion gate, and an in-memory announced set re-fired "
       "the same lever on every re-arm")
def _levercheck_boards():
    import subprocess
    import tempfile
    d = tempfile.mkdtemp()
    cfg = os.path.join(d, "cfg")
    os.makedirs(os.path.join(cfg, "overlays", "ov017"))
    open(os.path.join(cfg, "delinks.txt"), "w").write("    .text start:0x02011111 end:0x02011200\n")
    open(os.path.join(cfg, "overlays", "ov017", "delinks.txt"), "w").write(
        "    .text start:0x02133333 end:0x02133400\n")
    boards = os.path.join(d, "boards")
    os.makedirs(boards)
    open(os.path.join(boards, "02011111_board.md"), "w").write("EVO g1_x RULE: a lever\n")
    open(os.path.join(boards, "02133333_board.md"), "w").write("EVO SCORED g2 f.cpp 0 MATCH\n")
    open(os.path.join(boards, "02155555_board.md"), "w").write("EVO g1_y RULE: not landed yet\n")
    doc = os.path.join(d, "core.md")
    open(doc, "w").write("cites 02133333\n")
    env = {**os.environ, "LEVERCHECK_TSV": os.path.join(d, "none.tsv"), "LEVERCHECK_DOCS": doc,
           "LEVERCHECK_DECLINED": os.path.join(d, "none.txt"), "LEVERCHECK_BOARDS": boards,
           "LEVERCHECK_CFG": cfg, "LEVERWATCH_SEEN": os.path.join(d, "seen.txt")}
    r = subprocess.run([sys.executable, f"{KIT}/levercheck.py", "--keys"], capture_output=True, text=True, env=env)
    keys = [ln.split()[0] for ln in r.stdout.splitlines() if ln.strip()]
    if keys != ["02011111"] or r.returncode != 1:
        return "levercheck --keys gave %s (exit %d); expected only the landed uncited 02011111" % (keys, r.returncode)
    bash, env = _kp.bash(env)
    first = subprocess.run([bash, f"{KIT}/leverwatch.sh", "--once", "1"], capture_output=True, text=True,
                           env=env, timeout=60)
    if first.returncode != 0 or first.stdout.count("LEVER NEEDS PROMOTING") != 1 or "02011111" not in first.stdout:
        return "leverwatch --once did not fire exactly once on 02011111: %r" % first.stdout[:200]
    try:
        again = subprocess.run([bash, f"{KIT}/leverwatch.sh", "--once", "1"], capture_output=True, text=True,
                               env=env, timeout=5)
        return "leverwatch --once exited on an already-announced lever: %r" % again.stdout[:200]
    except subprocess.TimeoutExpired as e:
        if e.stdout and b"LEVER" in (e.stdout if isinstance(e.stdout, bytes) else e.stdout.encode()):
            return "leverwatch re-announced a lever it had already announced"
    return None


@check("levercheck's default doc list keeps a checkout path that contains ':'",
       "the two worker_src paths were joined with os.pathsep and split again, so a colon in the "
       "checkout path made every core.md citation invisible and claim.py served nothing")
def _levercheck_colon_path():
    docs = load("levercheck").doc_paths("/tmp/Dragon Quest IX: Sentinels/kit")
    core = os.path.join("/tmp/Dragon Quest IX: Sentinels/kit", "worker_src", "core.md")
    dead = os.path.join("/tmp/Dragon Quest IX: Sentinels/kit", "worker_src", "deadends.md")
    if docs != [core, dead]:
        return "doc_paths split the checkout path: %r" % (docs,)
    return None


@check("r28 rewrites a field read to the literal its equality arm compared against",
       "020db3f4 sits 6 bytes and one wrong mnemonic out because `field + 15` re-loads the field "
       "instead of reusing the register the compare already materialised the literal in. The "
       "rewrite is only valid on `==` arms and only on READS")
def _r28():
    C = load("colorsweep")
    text = ('ARM void f(Obj* o, char* p)\n{\n    if (o->f6a == -16) {\n'
            '        memset(p, o->f6a + 15, 0x800);\n    }\n}\n')
    got = dict(C.r28_literal_in_equality_arm(text))
    if not got:
        return "no candidate produced for the 020db3f4 shape"
    cand = got.get("litarm@o->f6a@0", "")
    if "(-16) + 15" not in cand:
        return "the literal form is missing; the arm's constant must replace the field read"
    if "if (o->f6a == -16)" not in cand:
        return "the condition itself was rewritten, which folds the test away"
    for bad in ('if (o->f6a != -16) { g(o->f6a); }',
                'if (o->f6a == -16) { o->f6a = 3; }',
                'if (o->f6a == -16) { g(&o->f6a); }'):
        if C.r28_literal_in_equality_arm('ARM void f(Obj* o)\n{\n    %s\n}\n' % bad):
            return "fired where the rewrite is not value-preserving: %s" % bad
    return None


@check("the six 2026-09-05 rules each fire on their own lever shape and on nothing clean",
       "each was promoted into core.md as prose after a worker paid for it; a rule that does not "
       "fire is prose the sweep cannot use, and one that fires on unrelated code spends the budget "
       "a real candidate needed")
def _r29_r34():
    C = load("colorsweep")
    shapes = {
        "r29_field_reread": ('ARM void f(Obj* o)\n{\n    int c = o->cur;\n    g(c);\n}\n',
                             "g(o->cur);"),
        "r30_cse_repeat_expr": ('ARM void f(Slot* arr, int n)\n{\n    g(&arr[n]);\n    h(&arr[n]);\n}\n',
                                "_cse_arrn = &arr[n];"),
        "r31_hoist_loop_bound": ('ARM void f(int w)\n{\n    int i;\n    for (i = 0; i < w - 9; i++) {\n'
                                 '        g(i);\n    }\n}\n', "= w - 9;"),
        "r32_sink_store_into_arms": ('ARM void f(char* o, int c)\n{\n    int v;\n    if (c == 0) {\n'
                                     '        v = 0;\n    } else {\n        v = 1;\n    }\n'
                                     '    o[0x5d] = v;\n}\n', "o[0x5d] = 0;"),
        "r33_field_signedness": ('struct S {\n    int idx;\n};\n// USA: func_1\n'
                                 'ARM void f(struct S* s)\n{\n    g(s->idx);\n}\n',
                                 "unsigned int idx;"),
        "r34_call_move_earlier": ('ARM void f(Obj* o)\n{\n    int a = g(o);\n    if (a != 0) {\n'
                                  '        h(o);\n    }\n    int b = k(o);\n    use(a, b);\n}\n',
                                  None),
    }
    for name, (text, needle) in shapes.items():
        got = getattr(C, name)(text)
        if not got:
            return "%s produced no candidate for the shape its own lever has" % name
        if needle and not any(needle in cand for _l, cand in got):
            return "%s fired but never emitted %r" % (name, needle)
        for _l, cand in got:
            if cand.count("(") != cand.count(")") or cand.count("{") != cand.count("}"):
                return "%s emitted an unbalanced candidate" % name
    clean = 'extern "C" ARM int g(int a)\n{\n    return a;\n}\n'
    for name in shapes:
        if getattr(C, name)(clean):
            return "%s fires on a source containing none of its shapes" % name
    return None


@check("r4 swaps same-type and bare declarations, not just differing initialised ones",
       "`_independent` counted every identifier left of `=` as WRITTEN, which for a declaration "
       "includes the type: `int a = 1;` and `int b = 2;` both wrote `int`, intersected, and were "
       "refused. A bare `int b;` has no `=` at all, so its written set came out empty and it was "
       "refused too. Recipe #9 -- the primary callee-saved lever -- therefore fired only on an "
       "adjacent pair with DIFFERENT type words that were BOTH initialised, which is almost no real "
       "declaration run, and 02218604's hoist had to be found by a paid session")
def _r4_same_type():
    C = load("colorsweep")

    def n(x, y):
        return len(C.r4_decl_reorder("ARM int f(S* s)\n{\n%s\n%s\n    return 0;\n}\n" % (x, y)))

    for name, x, y in (("same type, both initialised", "    int a = 1;", "    int b = 2;"),
                       ("same type, second bare", "    int a = 1;", "    int b;"),
                       ("both bare", "    int a;", "    int b;"),
                       ("bare below an initialised pointer",
                        "    TextBuffer* buf = &s->buf;", "    int len;")):
        if not n(x, y):
            return "no candidate for %s" % name
    for name, x, y in (("second reads the first", "    int a = 1;", "    int b = a;"),
                       ("first reads the second", "    int a = b;", "    int b = 2;"),
                       ("two call initialisers", "    int a = f();", "    int b = g();"),
                       ("an increment in the pair", "    int a = 1;", "    int b = c++;")):
        if n(x, y):
            return "swapped a dependent pair: %s" % name
    return None


@check("r4 preserves struct/class/union layout while reordering local declarations",
       "ov031:0223de7c colorsweep applied declswap@4 to primaryX/primaryY struct members; "
       "a smaller byte difference hid a changed input-object layout")
def _r4_preserves_record_layout():
    C = load("colorsweep")
    for kind in ("struct", "class", "union"):
        record = (kind + " Coordinates\n{\n"
                  "    unsigned short primaryX;\n    unsigned short primaryY;\n};\n")
        for nested in (False, True):
            text = ("void f() {\n" + record if nested else record + "void f() {\n")
            text += ("    // struct Fake {\n"
                     "    const char* brace = \"} union Fake {\";\n"
                     "    int left;\n    int right;\n"
                     "    if (left) {\n        int innerA;\n        int innerB;\n    }\n}\n")
            candidates = C.r4_decl_reorder(text)
            if not candidates:
                return "lost local declaration swaps for %s, nested=%s" % (kind, nested)
            for label, candidate in candidates:
                if record not in candidate:
                    return "%s changed %s member layout, nested=%s" % (label, kind, nested)
            if not any("    int right;\n    int left;" in c for _, c in candidates):
                return "lost function-local pair"
            if not any("        int innerB;\n        int innerA;" in c for _, c in candidates):
                return "lost nested-block local pair"
    method = ("class C {\n    int first;\n    int second;\n"
              "    void f() {\n        int a;\n        int b;\n    }\n};\n")
    candidates = C.r4_decl_reorder(method)
    if not any("        int b;\n        int a;" in c for _, c in candidates):
        return "lost method-local pair"
    if any("    int first;\n    int second;" not in c for _, c in candidates):
        return "changed method owner's member layout"
    return None


# ---------------------------------------------------------------- residue.py

@check("LOOP-SHAPE means the loop moved, not that the function changed length",
       "`branchy` compared the ROM's instruction at an offset against OURS at the same offset, so "
       "one extra instruction made every later branch 'differ' and 15 functions were filed under "
       "advice about hoisting a load out of a loop that was never restructured. It also excluded "
       "every mnemonic starting with `bl`, which silently dropped the blt/ble/bls/blo back-edges "
       "the class exists to catch")
def _loop_shape_class():
    R = load("residue")

    def drive(target_ins, our_ins):
        step = 4
        orig = bytes(range(1, 1 + step * len(target_ins)))
        mine = bytes(range(101, 101 + step * len(our_ins)))
        tmap = {i * step: t for i, t in enumerate(target_ins)}
        mmap = {i * step: m for i, m in enumerate(our_ins)}
        R.decode = lambda buf, isa: tmap if buf is orig else mmap
        return R.classify(orig, mine, "arm", set(), step * len(target_ins),
                          total=step * len(our_ins))[0]

    cases = [
        ("a branch facing a non-branch is a misalignment, not a target change",
         ["ldrsb r0, [r4, #8]", "cmp r0, #0", "bge #0x104", "mov r2, r0"],
         ["mvn r1, #0", "ldrsb r2, [r4, #8]", "cmp r2, r1", "bgt #0x104"], "SHAPE"),
        ("every target moved by the same amount is a length change",
         ["beq #0x10c", "b #0x104", "b #0x104", "beq #0x104"],
         ["beq #0x108", "b #0x100", "b #0x100", "beq #0x100"], "OPERAND"),
        ("blt is B with a condition, not BL",
         ["b #0x40", "cmp r0, #4", "blt #0x10", "mov r0, r1"],
         ["b #0x40", "cmp r0, #4", "blt #0x30", "mov r0, r1"], "LOOP-SHAPE"),
        ("bleq is BL and stays masked",
         ["bleq #0x40", "mov r0, r1"], ["bleq #0x80", "mov r0, r1"], "OPERAND"),
        ("two targets moving by different amounts is a real loop shape",
         ["b #0x40", "cmp r0, #4", "blt #0x10", "mov r0, r1"],
         ["b #0x20", "cmp r0, #4", "blt #0x30", "mov r0, r1"], "LOOP-SHAPE"),
        ("a pure register permutation is untouched",
         ["mov r0, r1", "add r2, r0, r3"], ["mov r5, r1", "add r2, r5, r3"], "REGPERM"),
    ]
    for name, t, m, want in cases:
        got = drive(t, m)
        if got != want:
            return "%s: want %s, got %s" % (name, want, got)
    return None


# ---------------------------------------------------------------- ov_recover.py

@check("placement refuses hand asm and still places plain C",
       "place() had a bare `continue` when sanitize found no ARM/THUMB name, so 7 byte-verified "
       "candidates deferred as wired-0 on every wave forever, silently. Six were hand asm (never to "
       "be landed) and one was real C that no naming rule covered")
def _placement():
    import pragmas
    src = open(f"{KIT}/ov_recover.py", encoding="utf-8").read()
    for tool in ("ov_recover.py", "integrate.py"):
        if "from pragmas import HAND_ASM as ASMPAT, asm_allow" not in open(f"{KIT}/{tool}", encoding="utf-8").read():
            return "%s no longer takes the asm pattern and allowlist from pragmas.py" % tool
    if "ASM_ALLOW" not in src or "asm_allow.txt" not in open(f"{KIT}/pragmas.py", encoding="utf-8").read():
        return "the asm allowlist is gone, so refusal is all-or-nothing again"
    pat = pragmas.HAND_ASM
    asm_src = "// USA: func_1\nARM\nasm void MTX_Identity33_(register void* pDst)\n{\n}\n"
    c_src = "// USA: func_2\nchar* StringReplaceLanguageTag(const char* s, char* d, int l) {\n}\n"
    if not pat.search(asm_src):
        return "hand-asm source is not detected, so it would be landed against policy"
    if pat.search(c_src):
        return "plain C is misdetected as asm, so real work would be refused"
    for token in ("PLACE-SKIP-ASM", "PLACE-FALLBACK", "PLACE-ASM-ALLOW"):
        if token not in src:
            return "place() no longer reports %s" % token
    allow = open(f"{KIT}/asm_allow.txt", encoding="utf-8").read()
    addrs = [l.split('#', 1)[0].split()[0] for l in allow.splitlines() if l.split('#', 1)[0].strip()]
    if not all(re.fullmatch(r"0[0-9a-f]{7}", a) for a in addrs):
        return "asm_allow.txt holds something that is not a bare address, so the gate is not narrow"
    if "print(f\"  PLACE-SKIP" not in src and "PLACE-SKIP" not in src:
        return "place() can still drop a candidate silently"
    return None


# ---------------------------------------------------------------- autorepair.py

@check("autorepair drops extern \"C\" on a callee the ROM mangles, and reverts only the renames",
       "ov017:021ab280 was BYTE-EXACT and parked as UNDEF-SYM because one prototype said "
       "`extern \"C\" int Vec3LengthRounded(int*)` while the ROM symbol is _Z17Vec3LengthRoundedPi; "
       "the all-or-nothing revert then threw that fix away along with a bad callee rename")
def _linkage_repairs():
    import autorepair
    src = open(f"{KIT}/autorepair.py", encoding="utf-8").read()
    if "_no_rename" not in src:
        return "the two-stage retry is gone: one bad rename again discards every other repair"
    if 'dropped extern "C"' not in src:
        return "the mangled-callee linkage repair is gone"
    names = autorepair._all_symbol_names()
    if not any(n.startswith("_Z") for n in names):
        return "no mangled symbols loaded, so the repair can never fire"
    # Any mangled symbol whose BARE name the config does not also declare is a callee a source can
    # only reach through the mangled spelling. Naming one here rots: Vec3LengthRounded was the
    # example until the update-compiler base renamed that address to Vector3fix_Length.
    probe = re.compile(r"^_Z(\d+)(.+)$")
    for n in names:
        m = probe.match(n)
        if not m:
            continue
        bare = m.group(2)[:int(m.group(1))]
        if len(bare) == int(m.group(1)) and bare not in names:
            return None
    return "no mangled callee whose bare name the config leaves undeclared, so the repair cannot fire"


@check("autorepair leaves a C++ callee whose declaration already mangles to the ROM symbol",
       "main 0205b234 declared `int GetWordFromTable02042648(int);`, which mangles to the ROM's "
       "_Z24GetWordFromTable02042648i; autorepair renamed it to that spelling under extern \"C\", "
       "the commit linked the same, and prready refused it as EXTERN-C-MANGLED")
def _autorepair_keeps_cxx_callee():
    import autorepair
    probe = re.compile(r"^_Z(\d+)(\w*[0-9a-f]{8}\w*)v$")
    for addr, name in autorepair._symbols("main").items():
        m = probe.match(name)
        if m and len(m.group(2)) == int(m.group(1)):
            bare = m.group(2)
            break
    else:
        return "main has no mangled no-argument callee with an address in its name to probe"
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "probe.cpp")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"void {bare}();\nvoid Probe() {{ {bare}(); }}\n")
    autorepair.repair(path, "main", "02000000")
    out = open(path, encoding="utf-8").read()
    if f"{bare}();" not in out or "_Z" in out or 'extern "C"' in out:
        return "the C++ callee was rewritten: %r" % out
    return None


@check("autorepair leaves a correct .c definition alone instead of adding extern \"C\"",
       "ov031 02226e08 gated MATCH as a .c, but the wave's autorepair probed the text as C++, saw a "
       "mangled symbol, and wrote `extern \"C\"` onto the definition; mwcc -lang=c then refused the file "
       "(\"')' expected\") and the wave integrated nothing")
def _autorepair_keeps_c_definition():
    import autorepair
    text = open(f"{KIT}/regress_fixtures/MinusDec_02009edc.c", encoding="utf-8").read()
    with tempfile.TemporaryDirectory(dir=f"{SP}/handwork", ignore_cleanup_errors=True) as d:
        path = os.path.join(d, "func_02009edc.c")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        autorepair.repair(path, "main", "02009edc")
        out = open(path, encoding="utf-8").read()
    if 'extern "C"' in out:
        return "autorepair wrote C++ linkage into a .c source: %r" % [l for l in out.splitlines() if 'extern "C"' in l]
    src =open(f"{KIT}/integrate.py", encoding="utf-8").read()
    m = re.search(r'(?m)^\s*has_ec = (.*(?:\n\s+.*)*?)$\n\s*cf = f', src)
    if not m or 'endswith(".c")' not in m.group(1):
        return "integrate.py would force extern \"C\" onto a .c definition (has_ec ignores the .c extension)"
    return None


# ---------------------------------------------------------------- finish_wave.sh

@check("finish_wave refuses a malformed module instead of reporting green",
       "`finish_wave.sh ov031` crashed ov_recover, integrated nothing, and still printed "
       "'OK : +0 delinked, green, no-new-commits' -- a harvest that never ran looked like a "
       "harvest with no hits")
def _module_arg():
    src = open(f"{KIT}/finish_wave.sh", encoding="utf-8").read()
    if "FATAL: module must be" not in src:
        return "no module validation present"
    if not re.search(r"main\|\[0-9\]\[0-9\]\[0-9\]\)", src):
        return "the accepted-module pattern no longer matches `main` or a 3-digit overlay"
    return None


@check("the staging sweep keeps the file it just proved",
       "the sweep compared the staged copy against $f, the path the worker WROTE, so the guard "
       "never fired and every MATCH was moved out of staging into attempts/. Integration picks a "
       "module by counting staging/*/*.cpp, so no worker match could land: six sat in attempts/ "
       "while the log said MATCH")
def _staging_sweep_keeps_match():
    import subprocess
    src = open(f"{KIT}/pull_worker.sh", encoding="utf-8").read()
    start = src.find('  mkdir -p "$SP/attempts"\n  _fb=')
    end = src.find('non-final file(s) out of staging" >> "$LOG"', start)
    if start < 0 or end < 0:
        return "cannot locate the sweep block in pull_worker.sh"
    block = src[start:src.index("\n", end) + 1]
    with tempfile.TemporaryDirectory() as d:
        stage = os.path.join(d, "stage").replace("\\", "/")
        sp = os.path.join(d, "sp").replace("\\", "/")
        os.makedirs(stage)
        os.makedirs(sp)
        open(f"{sp}/STAMP", "w").close()
        # `find -newer` is strictly greater, and the stamp and the files land in the
        # same second on this filesystem, so age the stamp or the sweep sees nothing.
        os.utime(f"{sp}/STAMP", (time.time() - 60, time.time() - 60))
        proven = f"{stage}/0201aaaa.cpp"
        variant = f"{stage}/Named_0201aaaa.cpp"
        for p in (proven, variant):
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("// USA: func_0201aaaa\nARM void f(void) {}\n")
        script = ("set -e\n"
                  f'SP="{sp}"\nSTAGE="{stage}"\nSTAMP="$SP/STAMP"\n'
                  'ADDR=0201aaaa\nTAG=func_\nMOD=main\nv=MATCH\n'
                  f'f="{d}/wip/0201aaaa.cpp"\n_swept=0\nLOG=/dev/null\n' + block)
        # the worker's own copy lives outside staging, which is the whole point of the bug
        os.makedirs(os.path.join(d, "wip"))
        with open(os.path.join(d, "wip", "0201aaaa.cpp"), "w", encoding="utf-8") as fh:
            fh.write("// USA: func_0201aaaa\n")
        bash, benv = _kp.bash()
        r = subprocess.run([bash, "-c", script], capture_output=True, text=True, env=benv)
        if r.returncode != 0:
            return "sweep block failed to run: %s" % (r.stderr or "").strip()[:200]
        left = sorted(n for n in os.listdir(stage) if n.endswith(".cpp"))
        if "0201aaaa.cpp" not in left:
            return "the proven match was swept out of staging (left: %s)" % left
        if "Named_0201aaaa.cpp" in left:
            return "the non-final variant was kept in staging (left: %s)" % left
    return None


@check("a slot claims its next function while the post-session sweep of the last one runs",
       "the slot waited for presweep --force on every miss before claiming again: 177 sessions spent "
       "434 slot-minutes there, p90 914 s, most killed by the 900 s timeout with nothing to show")
def _postsweep_detached():
    import subprocess
    src = open(f"{KIT}/pull_worker.sh", encoding="utf-8").read()
    start = src.find('  if [ "$v" = miss ] && [ -f "$_keep" ]; then\n')
    end = src.find("\n  fi\n", start)
    if start < 0 or end < 0:
        return "pull_worker.sh does not start the post-session sweep after the session's verdict"
    block = src[start:end + 6]
    with tempfile.TemporaryDirectory() as d:
        root = d.replace("\\", "/")
        os.makedirs(f"{root}/kit")
        os.makedirs(f"{root}/stage")
        with open(f"{root}/kit/presweep.py", "w", encoding="utf-8") as fh:
            fh.write("import os, sys, time\nsecond = os.path.exists(sys.argv[3] + '.swept')\ntime.sleep(3)\n"
                     "p = sys.argv[3] + '.swept'\nopen(p, 'w').write('// SCRATCH-USA: func_0201aaaa\\n')\n"
                     "print('MATCH ' + p if second else 'IMPROVED 4 2')\n")
        with open(f"{root}/a.cpp", "w", encoding="utf-8") as fh:
            fh.write("// USA: func_0201aaaa\n")
        script = (f'KIT="{root}/kit"\nMARG=main\nADDR=0201aaaa\nSLOT=1\nLOG="{root}/log"\nSTAGE="{root}/stage"\n'
                  f'v=miss\n_keep="{root}/a.cpp"\n_post_pid=""\necho "t $EPOCHREALTIME"\n{block}echo "t $EPOCHREALTIME"\n'
                  f'{block}echo "t $EPOCHREALTIME"\nwait\n')
        bash, benv = _kp.bash()
        r = subprocess.run([bash, "-c", script], capture_output=True, text=True, env=benv)
        stamps = [float(l.split()[1].replace(",", ".")) for l in r.stdout.splitlines() if l.startswith("t ")]
        log = open(f"{root}/log").read() if os.path.exists(f"{root}/log") else ""
        staged = open(f"{root}/stage/0201aaaa.cpp").read() if os.path.exists(f"{root}/stage/0201aaaa.cpp") else ""
    if len(stamps) != 3:
        return "the harness did not run: %s" % (r.stdout + r.stderr).strip()[-300:]
    if stamps[1] - stamps[0] > 2:
        return "the slot waited %.1fs for the post-session sweep" % (stamps[1] - stamps[0])
    if stamps[2] - stamps[0] < 2.5:
        return "a second sweep started before the slot's first one finished"
    if "s1 postsweep 0201aaaa 4 2" not in log or "s1 postsweep MATCHED 0201aaaa" not in log:
        return "the sweeps' results were not logged: %r" % log
    if "// USA: func_0201aaaa" not in staged:
        return "a sweep MATCH was not staged under its real tag: %r" % staged
    return None


def _compile_elf(text, repo, postcompile=False, rev=None, extra=()):
    import io
    import subprocess
    import tarfile
    import buildcfg
    from elftools.elf.elffile import ELFFile
    with tempfile.TemporaryDirectory() as d:
        src, obj = os.path.join(d, "t.cpp"), os.path.join(d, "t.o")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        flags = list(buildcfg.FLAGS)
        if rev:
            subprocess.run(["git", "-C", repo, "archive", "-o", os.path.join(d, "inc.tar"), rev, "include"], check=True)
            with tarfile.open(os.path.join(d, "inc.tar")) as tar:
                tar.extractall(d)
            flags = [os.path.join(d, "include") if f == "include" and flags[i - 1] == "-i" else f
                     for i, f in enumerate(flags)]
        r = subprocess.run(buildcfg.tool_command(buildcfg.CC) + flags + list(extra) + ["-c", src, "-o", obj],
                           cwd=repo, capture_output=True, text=True)
        if r.returncode:
            return "COMPILE " + (r.stdout + r.stderr)[-200:]
        if postcompile:
            buildcfg.postcompile(obj)
        return ELFFile(io.BytesIO(open(obj, "rb").read()))


@check("the data planner reproduces the ov026:021d8ba0 hand landing and refuses what cannot link",
       "integrate.py wired only .text, so a source that defines its own data -- the function-scope "
       "static that matched 021d8ba0 -- got its .data placed wherever the linker put it and shifted "
       "the overlay; and a static in the function BODY is a local symbol that 021dc440's object "
       "cannot link to, which only showed up as an undefined symbol at link time")
def _dataown_replay():
    import subprocess
    import buildcfg
    import dataown
    repo = buildcfg.REPO
    cfg = "config/usa/arm9/overlays/ov026"
    srcpath = "src/Combat/Overlay_26/func_ov026_021d8ba0.cpp"
    before, after = "aea3f05d", "2424ebd7"

    def show(rev, path):
        r = subprocess.run(["git", "show", "%s:%s" % (rev, path)], cwd=repo, capture_output=True)
        return r.stdout.decode("utf-8").replace("\r\n", "\n")

    pristine = open(repo + "/extract/usa/arm9_overlays/ov026.bin", "rb").read()
    own = os.path.normcase(os.path.abspath(os.path.join(repo, cfg, "relocs.txt")))

    def run(text, rom):
        elf = _compile_elf(text, repo, rev=after)
        if isinstance(elf, str):
            return elf
        relocs = dataown.load_relocs(repo)
        relocs[own] = (show(before, cfg + "/relocs.txt"), "\n")
        index = next(i for i, s in enumerate(elf.iter_sections()) if s.name == ".text")
        return dataown.plan(elf, index, 0x22c0, 0x021d8ba0, rom, 0x021d8a40, "026", cfg, repo, srcpath, {},
                            show(before, cfg + "/delinks.txt"), show(before, cfg + "/symbols.txt"), relocs)

    committed = show(after, srcpath)
    p = run(committed, pristine)
    if not isinstance(p, dict):
        return "the planner refused the landed source: %s" % p
    if p["symtxt"] != show(after, cfg + "/symbols.txt"):
        return "symbols.txt differs from the hand landing"
    if set(p["relocs"]) != {own} or p["relocs"][own][0] != show(after, cfg + "/relocs.txt"):
        return "relocs.txt differs from the hand landing"
    if p["delink_lines"] != "    .data start:0x021de840 end:0x021de87c\n":
        return "delink lines %r" % p["delink_lines"]

    head = "inline RowLabels& GetRowLabels() {"
    tail = "    return s;\n}\n"
    fn = 'extern "C" ARM void func_ov026_021d8ba0(BattleWork* self) {\n'
    if head not in committed or fn not in committed:
        return "cannot find the accessor or the function header to build the body-static variant"
    accessor = committed[committed.index(head):committed.index(tail, committed.index(head)) + len(tail)]
    decl = accessor[accessor.index("    static RowLabels s"):accessor.index("    return s;")]
    decl = decl.replace("static RowLabels s =", "static RowLabels sHolder =").replace("s.names", "sHolder.names")
    body = committed.replace(accessor, "").replace(fn, fn + decl).replace("GetRowLabels().", "sHolder.")
    p = run(body, pristine)
    if not (isinstance(p, str) and p.startswith("DATA-LOCALREF")):
        return "a body static that 021dc440 references was not refused: %s" % str(p)[:160]

    rom = bytearray(pristine)
    rom[0x021de858 - 0x021d8a40] ^= 1
    p = run(committed, bytes(rom))
    if not (isinstance(p, str) and p.startswith("DATA-BYTEDIFF")):
        return "a wrong initial byte was not refused: %s" % str(p)[:160]
    return None


@check("the data planner leaves a runtime object's exception tables to the link, which drops them",
       "the ROM's exception index is empty (020e5920..020e5920), yet the planner required a ROM home for "
       "every data section, so 0200ee38's try/catch, byte-exact with -Cpp_exceptions on, was refused "
       "DATA-UNPLACED .exceptix")
def _dataown_skips_exception_tables():
    import buildcfg
    import dataown
    text = open(f"{KIT}/regress_fixtures/DestroyArray_0200ee38.cpp", encoding="utf-8").read()
    elf = _compile_elf(text, buildcfg.REPO, extra=["-O4,p", "-char", "unsigned", "-Cpp_exceptions", "on"])
    if isinstance(elf, str):
        return elf
    names = {s.name for s in elf.iter_sections()}
    if not {".exception", ".exceptix"} <= names:
        return "the fixture no longer emits exception tables: %s" % sorted(names)
    index = next(i for i, s in enumerate(elf.iter_sections()) if s.name == ".text")
    p = dataown.plan(elf, index, 0x5c, 0x0200ee38, b"", 0x02000000, "main", "config/usa/arm9",
                     buildcfg.REPO, "src/Runtime/Main/func_0200ee38.cpp", {}, "", "", {})
    if p is not None:
        return "the planner on 0200ee38's EH object: %r" % (p if isinstance(p, str) else sorted(p))
    return None


@check("the data planner never writes a compiler-local name into another source",
       "landing main:020c6d7c renamed bss data_021112dc to its function-scope static isInitialized$13 and "
       "rewrote a dead `extern int data_021112dc;` in another source to `extern \"C\" int "
       "isInitialized$13;`, which mwcc rejects")
def _dataown_local_name():
    import subprocess
    import buildcfg
    import dataown
    repo = buildcfg.REPO
    cfg = "config/usa/arm9"
    landed = "c1328b61"
    srcpath = "src/Combat/Main/InitializeGamecardBusOwnership.cpp"

    def show(rev, path):
        r = subprocess.run(["git", "show", "%s:%s" % (rev, path)], cwd=repo, capture_output=True)
        return r.stdout.decode("utf-8").replace("\r\n", "\n")

    elf = _compile_elf(show(landed, srcpath), repo)
    if isinstance(elf, str):
        return elf
    pristine = open(os.path.join(repo, "extract/usa/arm9/arm9.bin"), "rb").read()
    index = next(i for i, s in enumerate(elf.iter_sections()) if s.name == ".text")
    with tempfile.TemporaryDirectory() as tree:
        os.makedirs(os.path.join(tree, "src"))
        with open(os.path.join(tree, "src", "Other.cpp"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("extern int data_021112dc;\nvoid Other() {}\n")
        subprocess.run(["git", "init", "-q"], cwd=tree, capture_output=True)
        subprocess.run(["git", "add", "src"], cwd=tree, capture_output=True)
        own = os.path.normcase(os.path.abspath(os.path.join(tree, cfg, "relocs.txt")))
        relocs = {own: (show(landed + "^", cfg + "/relocs.txt"), "\n")}
        p = dataown.plan(elf, index, 0xcc, 0x020c6d7c, pristine, 0x02000000, "main", cfg, tree, srcpath, {},
                         show(landed + "^", cfg + "/delinks.txt"), show(landed + "^", cfg + "/symbols.txt"),
                         relocs)
    if not isinstance(p, dict):
        return "the planner refused the landed source: %s" % p
    if "isInitialized$13 kind:bss addr:0x021112dc local" not in p["symtxt"]:
        return "symbols.txt does not carry the local static"
    written = [path for path, (text, _nl) in p["src_edits"].items() if "isInitialized$13" in text]
    if written:
        return "a compiler-local name was written into %s" % written
    return None


@check("cf_multi runs on the current colorforce JS and a move reaches the colouring order",
       "cf_multi patched JS anchors colorforce no longer has and died on its own assert, so the "
       "`moves`/`choices` probe core.md documents could not run")
def _cf_multi_moves():
    import shutil
    import subprocess
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "probe.cpp")
    shutil.copy(os.path.join(KIT, "regress_fixtures", "DispatchSumOrCopyHalfwords_0218ee38.cpp"), src)

    def trace(cfg):
        r = subprocess.run([sys.executable, f"{KIT}/pad/cf_multi.py", src, "ov015", "0218ee38", "0xb8", "0xb8",
                            json.dumps(cfg)], capture_output=True, text=True, cwd=KIT)
        if r.returncode:
            return None, (r.stdout + r.stderr).strip()[-300:]
        with open(os.path.join(tmp, "probe.cfm", "trace.json")) as fh:
            return json.load(fh)[-1]["nodes"], None

    try:
        base, err = trace({})
        if err:
            return "cf_multi failed: %s" % err
        order = [n[0] for n in base]
        if len(order) < 2:
            return "the last colouring call has %d node(s)" % len(order)
        moved, err = trace({"moves": [[order[-1], 0]]})
        if err:
            return "cf_multi failed with a move: %s" % err
        if moved[0][0] != order[-1]:
            return "node %d was not moved to the front: %s" % (order[-1], [n[0] for n in moved][:6])
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@check("a pool word's addend is read from r_addend, not from the zero mwcc writes in place",
       "mwcc emits RELA relocations with a zero in-place word; integrate.py, wgate.py and classify.py "
       "took the addend from that word, so a pool reference to symbol+N resolved to the bare symbol and "
       "a correct candidate was rejected as RELOC-WRONG (141 such words in the committed build; "
       "classify.py dropped ov015:0218bb3c from a wave that wgate had passed)")
def _rela_addend():
    import buildcfg
    import dataown
    elf = _compile_elf('extern char data_0201aaaa[];\nextern "C" char* F() { return data_0201aaaa + 5; }\n',
                       buildcfg.REPO)
    if isinstance(elf, str):
        return elf
    text = elf.get_section_by_name(".text").data()
    rel = elf.get_section_by_name(".rela.text")
    found = [dataown.addend(rr, text) for rr in rel.iter_relocations() if rr["r_info_type"] == 2]
    if found != [5]:
        return "addends read %s, want [5]" % found
    if "dataown.addend(rr, mine)" not in open(f"{KIT}/integrate.py", encoding="utf-8").read():
        return "integrate.py no longer reads the addend through dataown.addend"
    if "rr['r_addend'] if rr.is_RELA()" not in open(f"{KIT}/wgate.py", encoding="utf-8").read():
        return "wgate.py no longer reads r_addend for a RELA pool word"
    if "dataown.addend(rr, mine)" not in open(f"{KIT}/classify.py", encoding="utf-8").read():
        return "classify.py no longer reads the addend through dataown.addend"
    return None


@check("an inline function nothing references leaves the gate one non-empty .text section",
       "mwcc emits an empty inline destructor as its own multidef .text section; the original -dead "
       "link stripped it and our -nodead link kept it, so wgate called ov003:0216c00c OVERGEN 4 and "
       "its dead `rot` copy could only be held with a fake volatile")
def _dead_inline_section():
    import buildcfg
    text = ('struct Vec3 { int x, y, z; ~Vec3() {} };\nextern "C" void Use(void*);\n'
            'extern "C" void F(char* p) { Vec3 v = *(Vec3*)(p + 8); Use(p); }\n')
    raw = _compile_elf(text, buildcfg.REPO)
    if isinstance(raw, str):
        return raw
    if len([s for s in raw.iter_sections() if s.name == ".text" and s["sh_size"]]) != 2:
        return "the fixture no longer emits its destructor out of line"
    elf = _compile_elf(text, buildcfg.REPO, postcompile=True)
    kept = buildcfg.sections(elf, ".text")
    if len(kept) != 1 or not buildcfg.relocations(elf, kept[0][0]):
        return "after postcompile: %d non-empty .text sections" % len(kept)
    for tool in ("wgate.py", "wdiff.py", "classify.py", "integrate.py", "tucheck.py"):
        if "buildcfg.postcompile(" not in open(f"{KIT}/{tool}", encoding="utf-8").read():
            return "%s no longer runs the build's postcompile step" % tool
    return None


def _main_function(landed):
    import buildcfg
    import delinked
    cfg = f"{buildcfg.REPO}/{buildcfg.config_dir('main')}"
    texts = [open(f"{cfg}/delinks.txt", encoding="utf-8", errors="ignore").read()]
    allow = load("pragmas").asm_allow()
    for m in re.finditer(r"(?m)^\S+ kind:function\(arm,size=0x[0-9a-f]+\) addr:0x([0-9a-f]{8})",
                         open(f"{cfg}/symbols.txt", encoding="utf-8", errors="ignore").read()):
        if m.group(1) not in allow and delinked.covers(int(m.group(1), 16), texts) == landed:
            return m.group(1)
    return None


def _wgate(addr, text, name="t.cpp"):
    import subprocess
    with tempfile.TemporaryDirectory(dir=f"{SP}/handwork", ignore_cleanup_errors=True) as d:
        src = os.path.join(d, name)
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        env = {k: v for k, v in os.environ.items() if not k.startswith("WGATE_ALLOW")}
        r = subprocess.run([sys.executable, f"{KIT}/wgate.py", "main", addr, src], capture_output=True,
                           text=True, cwd=_kp.REPO, env={**env, "WGATE_SESSION": "regress"})
    return r.returncode, r.stdout + r.stderr


@check("wgate refuses hand asm off asm_allow.txt before spending a compile, and passes allowlisted asm",
       "wgate gated main 020c8aac's pure asm body MATCH; place() then parked it, so the worker session "
       "was paid for a file that could never land and the address was served again (#327)")
def _gate_refuses_hand_asm():
    pragmas = load("pragmas")
    allowed = sorted(pragmas.asm_allow())[0]
    asm = '#include <globaldefs.h>\nextern "C" ARM asm void f(void) {\n    bx lr\n}\n'
    if not pragmas.refused_asm("0200aaaa", "x.cpp", asm) or not pragmas.refused_asm("0200aaaa", "x.s", ""):
        return "refused_asm passes hand asm off the allowlist"
    if pragmas.refused_asm(allowed, "x.cpp", asm) or pragmas.refused_asm(allowed, "x.s", ""):
        return "refused_asm refuses %s, which asm_allow.txt lists" % allowed
    if pragmas.refused_asm("0200aaaa", "x.cpp", 'extern "C" int f(int a) { return a; }\n'):
        return "refused_asm refuses plain C"
    if pragmas.refused_asm("0200aaaa", "x.cpp", '// asm void g(void) is what the ROM has\n/* asm { nop } */\n'
                           'extern "C" int f(int a) { return a; }\n'):
        return "refused_asm refuses asm quoted in a comment"
    if not pragmas.refused_asm("0200aaaa", "x.cpp", 'extern "C" int f(int a) {\n    int b;\n'
                               '    __asm("mov b, a");\n    return b;\n}\n'):
        return "refused_asm passes an inline __asm register hack"
    addr = _main_function(landed=False)
    if not addr:
        return "no unlanded main function to gate"
    rc, out = _wgate(addr, asm.replace("void f(", "void func_%s(" % addr))
    if rc != 1 or "RESIDUE HAND-ASM 1" not in out:
        return "wgate on an asm body for %s: exit %d, %r" % (addr, rc, out.strip()[-160:])
    if not re.search(r'grep -qi "\^\$a " "\$KIT/asm_allow.txt"', open(f"{KIT}/stage_gated.sh", encoding="utf-8").read()):
        return "stage_gated.sh copies hand asm off asm_allow.txt from gated/ back into staging/"
    return None


@check("wgate reports a landed address ALREADY-COMMITTED even when the source does not compile",
       "the delink check ran after the compile, so a stale copy of a landed function wrote NO-COMPILE "
       "to its gate ledger: 8 of 10 NO-COMPILE ledgers in one hour were landed addresses (#277)")
def _committed_before_compile():
    addr = _main_function(landed=True)
    if not addr:
        return "no landed main function to gate"
    rc, out = _wgate(addr, "this is not C\n")
    if rc != 2 or "RESIDUE ALREADY-COMMITTED 0" not in out:
        return "wgate on an uncompilable source for landed %s: exit %d, %r" % (addr, rc, out.strip()[-160:])
    return None


@check("blockercheck counts no landed address as an open or pending blocker",
       "blockers.tsv is append-only and half its rows are addresses landed since, so health raised "
       "`CRACK: SHAPE blocks 6 function(s)` with 4 of the 6 already in decomp-matching (020a9eb8)")
def _blockercheck_skips_landed():
    import contextlib
    import io
    bc = load("blockercheck")
    landed, open_ = _main_function(landed=True), _main_function(landed=False)
    with tempfile.TemporaryDirectory(dir=f"{SP}/handwork", ignore_cleanup_errors=True) as d:
        bc.TSV, bc.DOC, bc.DECLINED = f"{d}/b.tsv", f"{d}/core.md", f"{d}/declined.txt"
        with open(bc.TSV, "w", encoding="utf-8", newline="\n") as fh:
            for a in (landed, landed, open_, open_):
                fh.write("1800000000\tmain\t%s\t600\tZZCLASS\t9\tx\n" % a)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bc.main()
    row = next((l for l in out.getvalue().splitlines() if l.startswith("ZZCLASS")), "")
    if landed in row or open_ not in row or row.split()[1:3] != ["1", "1"]:
        return "blockercheck row for a landed and an open address: %r" % row
    return None


@check("the linker's section symbols are known to the gate with their delinked addresses",
       "0200f29c needed a fake size-0 `func_020e5920_dup` alias for its second pool word at the start of "
       ".init; ARM9_INIT_START names that address, but the gate called it UNDEF-SYM (#335)")
def _section_lcf_symbols():
    import buildcfg
    known = buildcfg.lcf_symbols()
    head = open(f"{buildcfg.REPO}/{buildcfg.config_dir('main')}/delinks.txt", encoding="utf-8").read()
    m = re.search(r"(?m)^\s*\.init\s+start:0x([0-9a-fA-F]+)\s+end:0x([0-9a-fA-F]+)", head)
    if not m:
        return "main delinks.txt has no .init section header"
    if known.get("ARM9_INIT_START") != int(m.group(1), 16) or known.get("ARM9_INIT_END") != int(m.group(2), 16):
        return "lcf_symbols() ARM9_INIT_START/END = %r/%r, delinks .init is %s-%s" % (
            known.get("ARM9_INIT_START"), known.get("ARM9_INIT_END"), m.group(1), m.group(2))
    elf = _compile_elf('extern "C" char ARM9_INIT_START[];\nextern "C" unsigned int F() { return (unsigned int)ARM9_INIT_START; }\n',
                       buildcfg.REPO)
    if isinstance(elf, str):
        return elf
    symtab = elf.get_section_by_name(".symtab")
    undef = {s.name for s in symtab.iter_symbols() if s["st_shndx"] == "SHN_UNDEF" and s.name}
    if undef - set(known):
        return "not linker symbols: %s" % sorted(undef - set(known))
    return None


@check("the NitroSDK stack-size symbols are known linker symbols with the ROM's pool values",
       "main:020c6d48, 020c745c and 020c8548 load SDK_IRQ_STACKSIZE and SDK_SYS_STACKSIZE from their "
       "literal pools; lcf_symbols() did not list them, so wgate called every candidate UNDEF-SYM and "
       "integrate.py skipped it")
def _sdk_lcf_symbols():
    import buildcfg
    elf = _compile_elf('extern "C" void SDK_IRQ_STACKSIZE();\nextern "C" void SDK_SYS_STACKSIZE();\n'
                       'extern "C" long F(int a) { return a ? (long)SDK_IRQ_STACKSIZE : (long)SDK_SYS_STACKSIZE; }\n',
                       buildcfg.REPO)
    if isinstance(elf, str):
        return elf
    symtab = elf.get_section_by_name(".symtab")
    referenced = {symtab.get_symbol(rr["r_info_sym"]) for sec in elf.iter_sections()
                  if hasattr(sec, "iter_relocations") for rr in sec.iter_relocations()}
    referenced = {s.name for s in referenced if s["st_shndx"] == "SHN_UNDEF" and s.name}
    known = buildcfg.lcf_symbols()
    if referenced - set(known):
        return "not linker symbols: %s" % sorted(referenced - set(known))
    pools = {"usa": (0x020c6d78, 0x020c7574), "eur": (0x020c6d88, 0x020c7584), "jpn": (0x020c8844, 0x020c9040)}
    rom = open(f"{buildcfg.REPO}/{buildcfg.pristine('main')}", "rb").read()
    for name, addr in zip(("SDK_IRQ_STACKSIZE", "SDK_SYS_STACKSIZE"), pools[buildcfg.REGION]):
        word = int.from_bytes(rom[addr - 0x02000000:addr - 0x02000000 + 4], "little")
        if known[name] != word:
            return "%s = %#x, the ROM's pool word at %08x is %#x" % (name, known[name], addr, word)
    return None


@check("ov_recover gathers a staged file tagged with its bound name instead of skipping it",
       "gather() located a file only by a `// USA: func_<addr>` tag, so a port tagged with its curated "
       "name (`// USA: _Z22OnDMAOrTimerCompletioni`) passed wgate and was silently left out of every "
       "wave: 4 main ports and ov033:022a296c")
def _retag_bound_name():
    import ast
    src = open(f"{KIT}/ov_recover.py", encoding="utf-8").read()
    fns = {n.name: ast.get_source_segment(src, n) for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    if "retag" not in fns or "bound_addrs" not in fns:
        return "ov_recover.py has no retag()/bound_addrs()"
    if "txt = retag(txt, fp)" not in src:
        return "gather() no longer retags an untagged candidate"
    ns = {"re": re, "os": os, "TAG": "USA", "TAGPRE": "func_ov015_",
          "_BOUND": {"_Z3Foov": "0218bb3c", "Bar": "0218bb40"}}
    exec(fns["bound_addrs"] + "\n" + fns["retag"], ns)
    out = ns["retag"]("// USA: _Z3Foov\nARM void Foo()\n{\n}\n", "x.cpp")
    if not out.startswith("// USA: func_ov015_0218bb3c // KEEP-NAME\nARM void Foo()"):
        return "a C++ definition was retagged as %r" % out.split("\n")[0]
    out = ns["retag"]('// USA: Bar\nextern "C" ARM void Bar()\n', "y.cpp")
    if not out.startswith("// USA: func_ov015_0218bb40\n"):
        return "an extern \"C\" definition was retagged as %r" % out.split("\n")[0]
    if ns["retag"]("// USA: Nope\nARM void Nope()\n", "z.cpp") != "// USA: Nope\nARM void Nope()\n":
        return "an unknown name was rewritten"
    return None


@check("ov_recover commits its region's wiring and leaves the gate's ports to the other regions for regionsync",
       "the gate builds the ports with the landing, and `git add -A` swept the uncommitted config/jpn port into "
       "the match commit, past regionsync's red-module restore")
def _ov_recover_commit_leaves_ports():
    import ast
    import subprocess
    src = open(f"{KIT}/ov_recover.py", encoding="utf-8").read()
    wanted = {"sh", "commit", "consistent", "dirty_tracked", "unstage_foreign", "committed_addrs", "tag_addr"}
    nodes = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    if {n.name for n in nodes} != wanted:
        return "ov_recover.py lacks %s" % sorted(wanted - {n.name for n in nodes})
    with tempfile.TemporaryDirectory() as root:
        def git(*args):
            return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True).stdout
        files = {"config/usa/arm9/delinks.txt": "src/Old.cpp:\n    .text start:0x02000100 end:0x02000110\n",
                 "config/jpn/arm9/delinks.txt": "src/Old.cpp:\n    .text start:0x02000200 end:0x02000210\n",
                 "src/Old.cpp": "// USA: func_02000100\n"}
        for path, text in files.items():
            os.makedirs(os.path.dirname(f"{root}/{path}"), exist_ok=True)
            with open(f"{root}/{path}", "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        for args in (("init", "-q"), ("config", "user.name", "regress"), ("config", "user.email", "regress@localhost"),
                     ("add", "-A"), ("commit", "-q", "-m", "base")):
            git(*args)
        for path, block in (("config/usa/arm9/delinks.txt", "\nsrc/New.cpp:\n    .text start:0x02000000 end:0x02000010\n"),
                            ("config/jpn/arm9/delinks.txt", "\nsrc/New.cpp:\n    .text start:0x02000020 end:0x02000030\n")):
            with open(f"{root}/{path}", "a", encoding="utf-8", newline="\n") as fh:
                fh.write(block)
        with open(f"{root}/src/New.cpp", "w", encoding="utf-8", newline="\n") as fh:
            fh.write("// USA: func_02000000\n")
        ns = {"os": os, "re": re, "sys": sys, "time": time, "subprocess": subprocess, "_TRACKED": None,
              "_INDEX_MUTATORS": frozenset(("add", "reset", "checkout", "commit")), "REPO": root,
              "CFG": "config/usa/arm9", "HEXC": "[0-9a-fA-F]", "TAGRE": r"// USA: func_([0-9a-fA-F]{8})\b",
              "MSG": "Match {n}", "AUTH": [], "NOCOMMIT": False, "_DIRTY_BASE": set(),
              "OTHER_CONFIGS": ["config/jpn"]}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "commit-regression", "exec"), ns)
        cwd = os.getcwd()
        os.chdir(root)
        try:
            st = ns["commit"](1)
        finally:
            os.chdir(cwd)
        landed = git("show", "--name-only", "--format=", "HEAD").split()
        left = git("status", "--porcelain", "--", "config/jpn").strip()
    if st != "ok" or sorted(landed) != ["config/usa/arm9/delinks.txt", "src/New.cpp"]:
        return f"commit returned {st!r} and committed {landed}"
    if not left:
        return "the jpn port did not stay in the working tree for regionsync"
    return None


def _scaffold(module, addr):
    import subprocess
    r = subprocess.run([sys.executable, f"{KIT}/scaffold.py", module, addr], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=KIT)
    return r.stdout + r.stderr


@check("scaffold names a callee by its symbols.txt name, never by a scratch source's definition",
       "a tracked scratch file defining `Func020c976c` under `// USA: func_020c976c` made main:020d22f4's "
       "scaffold declare a callee that does not exist")
def _scaffold_symbols_name():
    out = _scaffold("main", "020d22f4")
    if 'extern "C" void func_020c976c();' not in out or "Func020c976c" in out:
        return "callee at 0x020c976c is not declared as func_020c976c: %s" % out[-300:]
    return None


@check("scaffold declares a mangled callee as C++, never extern \"C\"",
       "main:020c8bd4's scaffold declared `extern \"C\" void EnableSystemControlBit0();` for the ROM's "
       "_Z23EnableSystemControlBit0v, which links to a symbol that does not exist")
def _scaffold_mangled_callee():
    out = _scaffold("main", "020c8bd4")
    if "void EnableSystemControlBit0_020c89f8();" not in out:
        return "no C++ declaration of EnableSystemControlBit0_020c89f8: %s" % out[-300:]
    if re.search(r'(?m)^extern "C" void (?:_Z|EnableSystemControlBit0)', out):
        return "a mangled callee was declared extern \"C\""
    return None


@check("scaffold maps a bl that relocs.txt lacks",
       "relocs.txt has no entry for main:020c8bd4's bl to DisableSystemControlBit0 at +0x50, so the call "
       "map left it out")
def _scaffold_rom_call():
    out = _scaffold("main", "020c8bd4")
    if not re.search(r"(?m)^\s+\+0x50\s+DisableSystemControlBit0_020c8a08$", out):
        return "the call map has no +0x50 DisableSystemControlBit0_020c8a08: %s" % out[-300:]
    return None


@check("prready.py accepts a region-only source tagged for its region and still refuses an untagged one",
       "#151's nine JPN-only functions (`#if defined(jpn)`, `// JPN: func_020e12ec`) have no USA symbol to "
       "tag, so NO USA TAG refused them and no JPN-only function could ever land")
def _prready_region_only():
    P = load("prready")
    jpn = '#if defined(jpn)\n// JPN: func_020e12ec\nextern "C" ARM int func_020e12ec(char* d) {\n    return 0;\n}\n#endif\n'
    usa = '// USA: func_0201d044\nARM int f(void) {\n    return 1;\n}\n'
    bare = 'extern "C" ARM int func_020e12ec(char* d) {\n    return 0;\n}\n'
    unguarded = '// JPN: func_020e12ec\nextern "C" ARM int func_020e12ec(char* d) {\n    return 0;\n}\n'
    if not P.region_tagged(jpn) or not P.region_tagged(usa):
        return "prready.py refused a region-only JPN source or a USA-tagged one"
    if P.region_tagged(bare) or P.region_tagged(unguarded):
        return "prready.py accepted a source with no USA tag outside a region guard"
    old = "_Z26TryApplyElemFields0205d5d0P15StructA0205d5d0iiih"
    if not P.signature_only(old, "_Z26TryApplyElemFields0205d5d0P15StructA0205d5d0iii"):
        return "prready.py calls a one-region signature change (a region-split prototype) a half rename"
    if P.signature_only(old, "_Z26TryApplyElemFieldsXXXXXXXXP15StructA0205d5d0iiih") or P.signature_only("Foo", "Bar"):
        return "prready.py treats a changed function name as a signature-only change"
    return None


@check("prready.py decomp reads a pull request in a fixed number of git calls, not several per file",
       "one git show and two git diffs per changed file took prready.py decomp 17 minutes on a large pull request")
def _prready_batched():
    import subprocess
    P = load("prready")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        def git(*args):
            return subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
                                   *args], capture_output=True, text=True, check=True).stdout.strip()

        def commit(files):
            for path, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(d, path)), exist_ok=True)
                with open(os.path.join(d, path), "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
            git("add", "-A")
            git("commit", "-qm", "x")

        git("init", "-q", "-b", "main")
        wired = "".join("src/F%d.cpp:\n    complete\n    .text start:0x%08x end:0x%08x\n" % (i, 0x02000000 + 16 * i,
                                                                                         0x02000010 + 16 * i)
                        for i in range(40))
        commit({"config/usa/arm9/delinks.txt": wired, "config/usa/arm9/symbols.txt": "",
                **{"src/F%d.cpp" % i: "// USA: F%d\nvoid F%d() {}\n" % (i, i) for i in range(40)}})
        tip = git("rev-parse", "HEAD")
        commit({"src/F%d.cpp" % i: "// USA: F%d\nvoid F%d() { }\n" % (i, i) for i in range(40)})
        P.REPO, calls, real = d, [0], subprocess.run

        def counted(*args, **kwargs):
            calls[0] += 1
            return real(*args, **kwargs)
        subprocess.run = counted
        try:
            problems = P.decomp(tip)
        finally:
            subprocess.run = real
    if problems:
        return "prready.py decomp refused a clean 40-file change: %r" % problems[:3]
    if calls[0] > 12:
        return "prready.py decomp ran %d git commands for 40 changed files" % calls[0]


@check("prready.py refuses a pull request built on a stale kit or decomp, and passes a current one",
       "pull requests built on stale checkouts reverted the CI workflow, re-added a file for an address "
       "another file owned, renamed a symbol in one region only, recorded dead ends for matched "
       "functions and cited matches that never landed; one READY pull request added 24 codegen pragma lines")
def _prready():
    import subprocess
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        def git(repo, *args):
            r = subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t",
                                "-c", "core.autocrlf=false", *args], capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")

        def commit(repo, files):
            for path, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(repo, path)), exist_ok=True)
                with open(os.path.join(repo, path), "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "x")

        pub_decomp, pub_kit, decomp, kit = (f"{d}/{n}" for n in ("pub_decomp", "pub_kit", "decomp", "kit"))
        for repo, branch in ((pub_decomp, "decomp-matching"), (pub_kit, "main")):
            os.makedirs(repo)
            git(repo, "init", "-q", "-b", branch)
        commit(pub_decomp, {
            ".github/workflows/match.yml": "on: push\n",
            "config/usa/arm9/delinks.txt": "    .text       start:0x02000000 end:0x02001000 kind:code align:32\n\n"
                                           "src/A.cpp:\n    complete\n    .text start:0x02000010 end:0x02000020\n",
            "config/usa/arm9/symbols.txt": "Foo kind:function(arm,size=0x10) addr:0x02000010\n"
                                           "data_02000030 kind:data(any) addr:0x02000030\n"
                                           "data_02000040 kind:data(any) addr:0x02000040\n",
            "config/eur/arm9/symbols.txt": "Foo kind:function(arm,size=0x10) addr:0x02000010\n",
            "config/jpn/arm9/symbols.txt": "data_02000040 kind:data(any) addr:0x02000040\n",
            "config/usa/arm9/overlays/ov001/delinks.txt": "src/B.cpp:\n    complete\n"
                                                          "    .text start:0x02150000 end:0x02150100\n",
            "config/usa/arm9/overlays/ov001/symbols.txt": "Baz kind:function(arm,size=0x100) addr:0x02150000\n",
            "config/usa/arm9/overlays/ov002/delinks.txt": "",
            "config/usa/arm9/overlays/ov002/symbols.txt": "Qux kind:function(arm,size=0x10) addr:0x02150010\n",
            "src/A.cpp": "void Foo() {}\n",
            "src/B.cpp": "void Baz() {}\n"})
        commit(pub_kit, {n: open(f"{KIT}/{n}", encoding="utf-8").read()
                         for n in ("prready.py", "delinked.py", "kitpaths.py", "pragmas.py", "plausible.py", "mangle.py",
                                   "gitread.py")}
               | {"worker_src/deadends.md": "# dead ends\n", "worker_src/core.md": "# core\n"})
        git(d, "clone", "-q", pub_decomp, decomp)
        git(d, "clone", "-q", pub_kit, kit)
        env = dict(os.environ, DQIX_KIT_URL=pub_kit, DQIX_KIT_BRANCH="main", DQIX_DECOMP_URL=pub_decomp,
                   DQIX_DECOMP_BRANCH="decomp-matching", DQIX_REPO=decomp, DQIX_STATE=f"{d}/state")

        def prready(*args, stdin=None):
            r = subprocess.run([sys.executable, f"{kit}/prready.py", *args], env=env, input=stdin,
                               capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr

        for mode in ("kit", "decomp"):
            code, out = prready(mode)
            if code != 0:
                return f"a current checkout was refused by prready.py {mode}: {out.strip()[-300:]}"
        commit(decomp, {"tools/configure.py": "PYTHON = 1\n"})
        code, out = prready("decomp")
        if code != 1 or "OUTSIDE A MATCH tools/configure.py" not in out:
            return f"prready.py decomp passed a contributor's unreviewed tooling change: exit {code}"
        env["PRREADY_REVIEWED"] = "tools/configure.py"
        code, out = prready("decomp")
        del env["PRREADY_REVIEWED"]
        if code != 0:
            return f"prready.py decomp refused a tooling change landpr supplied itself: {out.strip()[-300:]}"
        git(decomp, "reset", "-q", "--hard", "HEAD~1")
        commit(decomp, {".github/workflows/match.yml": "on: pull_request\n",
                        "include/A.h": "inline int* view(char* p) { return reinterpret_cast<int*>(p); }\n",
                        "src/Dead.cpp": "void Dead() {}\n",
                        "src/Untagged.cpp": "void Untagged() {}\n",
                        "config/jpn/arm9/delinks.txt": "src/Untagged.cpp:\n    complete\n"
                                                       "    .text start:0x02000020 end:0x02000030\n",
                        "src/A.cpp": "#pragma optimize_for_size off\nvoid Foo() {}\n#pragma optimize_for_size reset\n",
                        "src/B.cpp": "#pragma ipa file\nvoid Baz() {}\n",
                        "config/usa/arm9/symbols.txt": "Bar kind:function(arm,size=0x10) addr:0x02000010\n"
                                                       "data_02000030 kind:data(any) addr:0x02000030\n"
                                                       "data_02000040 kind:data(any) addr:0x02000040\n",
                        "config/jpn/arm9/symbols.txt": "data_02000030 kind:data(any) addr:0x02000040\n",
                        "config/usa/arm9/overlays/ov001/symbols.txt": "_Z3Bazv kind:function(arm,size=0x100) addr:0x02150000\n",
                        "config/usa/arm9/overlays/ov002/symbols.txt":
                            "_Z19Qux_ov002_02150010v kind:function(arm,size=0x10) addr:0x02150010\n"})
        commit(kit, {"pragma_allow.txt": "src/B.cpp  ipa  Eakeys  whole-TU data layout\n",
                     "worker_src/deadends.md": "# dead ends\n02000010\tstale\n02000040\topen\n",
                     "worker_src/core.md": "# core\nrule (02000010)\nrule (02000400)\nrule (02150010)\n"})
        commit(pub_decomp, {"src/A.cpp": "void Foo() { }\n"})
        commit(pub_kit, {"README.md": "x\n"})
        want = {"decomp": ("KIT BEHIND", "DECOMP BEHIND", "OUTSIDE A MATCH .github/workflows/match.yml",
                           "DEAD FILE src/Dead.cpp", "HALF RENAME Foo", "CODEGEN PRAGMA src/A.cpp: adds 2",
                           "NO USA TAG src/Untagged.cpp", "NAME WITHOUT ADDRESS _Z3Bazv",
                           "REINTERPRET-CAST include/A.h"),
                "kit": ("KIT BEHIND", "NO DEAD ENDS", "UNPROVEN CITATION 02000400", "UNPROVEN CITATION 02150010")}
        for mode, needles in want.items():
            code, out = prready(mode)
            missing = [n for n in needles if n not in out]
            if code != 1 or missing:
                return f"prready.py {mode}: exit {code}, missing {missing}: {out.strip()[-400:]}"
            if mode == "kit" and "CITATION 02000010" in out:
                return f"prready.py kit flagged a landed citation: {out.strip()[-400:]}"
            if mode == "decomp" and "HALF RENAME data_02000040" in out:
                return f"prready.py decomp flagged a region port taking the USA name: {out.strip()[-400:]}"
            if mode == "decomp" and "Qux_ov002_02150010" in out:
                return f"prready.py decomp flagged a name that carries its address: {out.strip()[-400:]}"
            if mode == "decomp" and "CODEGEN PRAGMA src/B.cpp" in out:
                return f"prready.py decomp refused a pragma pragma_allow.txt lists for that file: {out.strip()[-400:]}"
        code, out = prready("--hook", stdin=json.dumps({"tool_input": {"command": "gh pr create -R ZevyaDev/dqix-decomp"}}))
        if code != 2 or "HALF RENAME" not in out:
            return f"the hook let gh pr create through on a stale decomp: exit {code}"
        code, out = prready("--hook", stdin=json.dumps({"tool_input": {"command": "gh pr merge 5 -R ZevyaDev/dqix-decomp"}}))
        if code != 2 or "landpr.sh" not in out:
            return f"the hook let gh pr merge land a decomp pull request without landpr.sh: exit {code}"
        for command in ("git status", "gh pr merge 5 -R ZevyaDev/dqix-decomp-kit"):
            code, out = prready("--hook", stdin=json.dumps({"tool_input": {"command": command}}))
            if code != 0:
                return f"the hook blocked `{command}`: exit {code} {out.strip()[-200:]}"
    return None


# ------------------------------------------------------- END-TO-END (slow, compiles)
# The tests above pin what each rewrite RENDERS. They cannot tell you whether the sweep still
# CRACKS a function: adding a rule enlarges the neighbourhood, so a winning path that used to fit
# inside the budget can fall outside it and the only symptom is a function quietly going back to
# unmatched. Every function cracked by hand gets an entry here.
FUNCTIONAL = [
    # (module, addr, prior file, expected, budget, what it proves)
    ("main", "0209ed0c", "regress_fixtures/GatherEnabledRecords_0209ed0c.cpp", "MATCH", 200,
     "cmpflip > declfnscope: comparison operand order then function-scope declaration order"),
    ("012", "0218a9ec", "regress_fixtures/BitfieldNoCast_0218a9ec.cpp", "MATCH", 60,
     "shortcast: a bitfield read feeding an add folds its extract into the add and steals the "
     "register; a (short) cast blocks the fold and emits nothing"),
    ("025", "021ebb90", "regress_fixtures/ShortSpill14_021ebb90.cpp", "MATCH", 60,
     "shortspill+ret: a short local's spill reload stays below the previous store, and its int "
     "callee declared returning short adds no truncation"),
    ("main", "02065990", "regress_fixtures/InPlaceField5_02065990.cpp", "MATCH", 60,
     "inplace+fold: the copy's shift folded into its initialiser closes the last one-shift fold; the "
     "prior is r52's output, since from the 40-byte one the first level alone exceeds the budget"),
    ("017", "021bd5d0", "regress_fixtures/SyncCombatantFlagAndDispatch_021bd5d0.cpp", "MATCH", 150,
     "declmove: one non-adjacent declaration move fixes the register ladder that decides stm fusion"),
    ("main", "0205f9cc", "regress_fixtures/AllocateAndInsertTimedNode_0205f9cc.cpp", "MATCH", 400,
     "mlaacc: binding a multiply-accumulate's MULTIPLICAND to the result local reverses the operand "
     "load order and stops the destination reusing the addend's register, then declmove colours it"),
    ("main", "020db3f4", "regress_fixtures/RefreshCacheBuffers_020db3f4.cpp", "MATCH", 60,
     "litarm: inside a `field == K` arm the arithmetic must be written on K, which reuses the "
     "register the compare materialised; naming the field emits a fresh ldr and colours it wrong"),
    ("main", "020307d0", "regress_fixtures/SearchAndEmitEntries_020307d0.cpp", "MATCH", 150,
     "reread: re-reading a field the source already holds in a local reproduces the ROM's redundant "
     "ldr -- without it the function is one instruction SHORT"),
    ("main", "02098a84", "regress_fixtures/CompactAndCopySlots_02098a84.cpp", "MATCH", 80,
     "cse: one named binding reused at both ends of a block keeps the offset live in a callee-saved "
     "register; two identical `&arr[i]` expressions are re-formed independently"),
    ("main", "020e2110", "regress_fixtures/DrawBorderTiles_020e2110.cpp", "MATCH", 200,
     "loopbound: a compound `for` bound bound to a local ahead of the loop is computed before the "
     "loop's own inits, which is the ROM's order"),
    ("main", "02012538", "regress_fixtures/AdvanceActorState_02012538.cpp", "MATCH", 60,
     "sinkstore: storing from each arm instead of through a named flag local lets mwcc predicate "
     "the sequence in one register"),
    ("main", "020c0a40", "regress_fixtures/HashUpdate_020c0a40.cpp", "MATCH", 100,
     "signflip: a field's signedness picks asr against lsr and blt against blo -- those diff rows "
     "are a type declaration, not a colouring"),
    ("015", "0218ee38", "regress_fixtures/DispatchSumOrCopyHalfwords_0218ee38.cpp", "MATCH", 60,
     "chainconst: two adjacent stores of the same constant materialise it AFTER the pointer save; "
     "chaining them reverses that, and the chain's direction fixes the store order too"),
    ("main", "02037d88", "regress_fixtures/HandleCombatantTick_02037d88.cpp", "MATCH", 250,
     "callmove: which call runs first decides who owns the callee-saved register for the rest of "
     "the block, and the move has to be allowed to hop a braced dispatch"),
    ("main", "02053634", "regress_fixtures/BindCall_02053634.cpp", "MATCH", 90,
     "bindcall: a call left inline in a compare always takes Rm, for BOTH operand orders; naming "
     "the result restores left-to-right placement"),
    ("main", "02076df4", "regress_fixtures/NoOpCase_02076df4.cpp", "MATCH", 60,
     "nocase: an explicit `case K: return;` gives mwcc a detached epilogue copy; deleting it lets "
     "the shared one-instruction epilogue inline into the jump-table slot"),
    ("023", "021ddc98", "regress_fixtures/ShortCanvasX_021ddc98.cpp", "MATCH", 60,
     "shortspill on a brace-below function: `short x` loads with ldrsh into the product temp; the "
     "prior already loads x before y, since neither step alone moves the score"),
    ("main", "020d22f4", "regress_fixtures/ConstQueueTable_020d22f4.cpp", "MATCH", 60,
     "constextern on a pointer table: `T* const tbl[9]` takes the indexed load out of the worst-case "
     "alias set, so it is no longer ordered before the store to the read index"),
]


def run_functional():
    import subprocess
    import shutil
    import tempfile
    bad = 0
    for module, addr, prior, expected, budget, what in FUNCTIONAL:
        src = os.path.join(KIT, prior)
        if not os.path.exists(src):
            print("FAIL  %s: prior %s is gone -- the base a crack depends on must not be deleted"
                  % (addr, prior))
            bad += 1
            continue
        work = os.path.join(tempfile.mkdtemp(), os.path.basename(prior))
        # The gate checks the EXPORTED symbol, so the file has to carry the config's name.
        text = open(src, encoding="utf-8").read()
        stem = os.path.basename(prior)[:-4].split("_")[0]
        # An overlay function is bound as func_ovNNN_<addr>; renaming it to func_<addr> like main
        # makes the gate report WRONG-SYMBOL and the crack looks lost when it is only misnamed.
        bound = "func_" + addr if module == "main" else "func_ov%s_%s" % (module, addr)
        if stem and not stem.startswith("func_"):
            text = text.replace(stem + "_" + addr, bound).replace(stem, bound)
        # C linkage on the DEFINITION line only, and never on one that already has it: a blanket
        # string replace put `extern "C" extern "C"` in front of 0209ed0c, every candidate failed to
        # compile, and the sweep reported no RESULT at all -- which reads as "the crack was lost".
        text = re.sub(r'(?m)^(?!extern "C" )((?:ARM|THUMB) [\w* ]*?%s\()' % re.escape(bound),
                      r'extern "C" \1', text)
        open(work, "w", encoding="utf-8", newline="\n").write(text)
        # Every prior here IS a committed address -- that is what makes the crack checkable -- and
        # wgate reports ALREADY-COMMITTED instead of MATCH on some of them, which colorsweep scores
        # as a compile failure and the case reads as "the crack was lost".
        r = subprocess.run([sys.executable, os.path.join(KIT, "colorsweep.py"), module, addr, work,
                            "--depth", "3", "--budget", str(budget)],
                           capture_output=True, text=True, cwd=_kp.REPO,
                           env={**os.environ, "WGATE_ALLOW_COMMITTED": "1"})
        out = (r.stdout or "") + (r.stderr or "")
        got = "MATCH" if "RESULT MATCH" in out else "no match"
        if got != expected:
            last = [l for l in out.strip().splitlines() if l.startswith("RESULT")]
            print("FAIL  %s functional: expected %s, got %s (%s)"
                  % (addr, expected, got, last[-1] if last else "no RESULT line"))
            print("      it proves: %s" % what)
            bad += 1
        else:
            print("ok    %s functional: colorsweep still reaches %s" % (addr, expected))
    return bad


def sweep_fingerprint():
    """Hash of everything that decides whether a crack still lands."""
    import hashlib
    h = hashlib.md5()
    for p in ("colorsweep.py", "wdiff.py", "wgate.py"):
        try:
            h.update(open(f"{KIT}/{p}", "rb").read())
        except OSError:
            h.update(b"missing")
    h.update(repr(FUNCTIONAL).encode())
    return h.hexdigest()


@check("recovery delegates Python to the current interpreter and can import its ELF dependency",
       "native Windows child lookup selected a different Python and crashed integrate.py before mutation")
def _recovery_python_interpreter():
    import ast
    import subprocess
    from types import SimpleNamespace
    tree = ast.parse(open(f"{KIT}/ov_recover.py", encoding="utf-8").read())
    nodes = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == "sh"]
    if len(nodes) != 1: return "shared recovery launcher missing"
    ns = {"sys":sys,"subprocess":subprocess,"_TRACKED":None,"_INDEX_MUTATORS":frozenset()}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"recovery-launcher","exec"),ns)
    code = "import json,sys,elftools; from elftools.elf.elffile import ELFFile; print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'elftools':elftools.__file__}))"
    result = ns["sh"]("python","-c",code)
    if result.returncode: return "selected interpreter cannot import ELF dependency: " + result.stderr[-300:]
    proof = json.loads(result.stdout)
    normalize = lambda path: os.path.normcase(os.path.abspath(path))
    if normalize(proof["executable"]) != normalize(sys.executable):
        return "delegated Python differs from parent"
    if normalize(proof["prefix"]) != normalize(sys.prefix): return "delegated environment differs"
    if os.path.commonpath((normalize(sys.prefix),normalize(proof["elftools"]))) != normalize(sys.prefix):
        return "ELF dependency loaded outside selected environment"
    calls = []
    ns["subprocess"] = SimpleNamespace(run=lambda argv,**kwargs: calls.append((argv,kwargs)))
    for command in (("git","status","--porcelain"),("ninja","check"),(sys.executable,"-V")):
        ns["sh"](*command)
        if calls[-1] != (list(command),{"capture_output":True,"text":True}):
            return "non-bare-Python command changed: " + repr(command)

@check("delegated integrator startup failure stops before gate while preserving source snapshots",
       "try_set ignored a nonzero integrator exit and ran an expensive gate or quiet-green wave")
def _delegated_failure_stops_gate():
    import ast
    import subprocess
    import shutil
    src = open(f"{KIT}/ov_recover.py", encoding="utf-8").read()
    tree = ast.parse(src)
    wanted = {"sh","try_set"}
    nodes = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
    if {n.name for n in nodes} != wanted: return "launcher/try_set missing"
    os.makedirs(f"{SP}/handwork",exist_ok=True)
    root = tempfile.mkdtemp(prefix="delegate_regress_",dir=f"{SP}/handwork")
    source,hold,stage = (os.path.join(root,name) for name in ("src","hold_main","staging"))
    for directory in (source,hold,stage,os.path.join(root,"wlog")): os.makedirs(directory)
    candidate = b"// USA: func_02000000\nvoid func_02000000() {}\n"
    for directory in (hold,stage):
        with open(os.path.join(directory,"candidate.cpp"),"wb") as out: out.write(candidate)
    events = []
    def place(addrs):
        events.append("place")
        shutil.copyfile(os.path.join(hold,"candidate.cpp"),os.path.join(source,"candidate.cpp"))
    def gate():
        events.append("gate")
        return True
    ns = {"sys":sys,"os":os,"glob":__import__("glob"),"re":re,"subprocess":subprocess,
          "_TRACKED":{"stale"},"_INDEX_MUTATORS":frozenset(),"clean":lambda:events.append("clean"),
          "dirty_tracked":lambda:set(),"place":place,"tracked":lambda path:True,"gate":gate,
          "committed_addrs":lambda:set(),"REPO":root,"SRCDIR":source,"SRCDIRS":[source],
          "src_cpps":lambda:__import__("glob").glob(os.path.join(source,"*.cpp")),"SP":root,"HOLD":hold,
          "SUF":"main","TAGPRE":"func_","INTARGS":[],"INT":os.path.join(root,"delegate.py")}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"try-set-regression","exec"),ns)
    with open(ns["INT"],"w") as out: out.write("import dqix_intentionally_missing_startup_dependency\n")
    try:
        ns["try_set"](["02000000"])
    except RuntimeError as exc:
        if "delegated integrator exited" not in str(exc): return "failure lacks visible diagnostic"
    else:
        return "startup failure did not abort"
    if "gate" in events or ns["_TRACKED"] is not None: return "startup failure reached gate or retained stale cache"
    log = open(os.path.join(root,"wlog","integ_main.txt")).read()
    if "ModuleNotFoundError" not in log: return "startup traceback not preserved"
    for directory in (source,hold,stage):
        if open(os.path.join(directory,"candidate.cpp"),"rb").read() != candidate:
            return "startup failure lost source snapshot"
    events.clear()
    with open(ns["INT"],"w") as out: out.write("print('REPAIR per-candidate rejection; other candidates remain valid')\n")
    if ns["try_set"](["02000000"]) is not True or events.count("gate") != 1:
        return "ordinary rc0 partial/rejected candidates no longer reach gate"
    if "REPAIR per-candidate rejection" not in open(os.path.join(root,"wlog","integ_main.txt")).read():
        return "ordinary integrator output not preserved"
    for directory in (source,hold,stage):
        if open(os.path.join(directory,"candidate.cpp"),"rb").read() != candidate:
            return "rc0 changed source snapshots"

@check("recovery tracked snapshots are batch, fail closed and refresh after index writes",
       "per-file Git made Windows waves spend minutes scanning; stale/failed caches could delete committed source")
def _tracked_snapshot_behaviour():
    import ast
    from types import SimpleNamespace
    src = open(f"{KIT}/ov_recover.py", encoding="utf-8").read()
    tree = ast.parse(src)
    wanted = {"sh", "repo_relative_path", "read_tracked_paths", "tracked"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    if {n.name for n in nodes} != wanted:
        return "tracked snapshot functions missing"
    paths = {f"src/Combat/Main/f{i}.cpp" for i in range(4000)} | {"src/Combat/Main/has space.cpp"}
    reads = [0]
    fail = [False]
    truncated = [False]
    def run(args, **kwargs):
        if args[:2] == ["git", "ls-files"]:
            reads[0] += 1
            payload = ("\0".join(sorted(paths)) + "\0").encode() if paths else b""
            return SimpleNamespace(returncode=128 if fail[0] else 0, stdout=payload[:-1] if truncated[0] else payload, stderr=b"simulated Git error")
        if args[:2] == ["git", "add"]:
            paths.add("src/Combat/Main/new.cpp")
        if args[:2] == ["git", "reset"]:
            paths.discard("src/Combat/Main/new.cpp")
        return SimpleNamespace(returncode=128 if fail[0] else 0, stdout="", stderr="")
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    root = tempfile.mkdtemp(prefix="tracked_regress_", dir=f"{SP}/handwork")
    mutators = [n for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id == "_INDEX_MUTATORS" for t in n.targets)]
    if len(mutators) != 1: return "index mutation policy missing"
    nodes = mutators + nodes
    ns = {"os":os, "sys":sys, "REPO":root, "subprocess":SimpleNamespace(run=run), "_TRACKED":None}
    exec(compile(ast.Module(body=nodes,type_ignores=[]), "tracked-regression", "exec"), ns)
    for _ in range(2):
        for path in paths:
            if not ns["tracked"](path): return "tracked path became untracked"
    if reads[0] != 1: return "membership still starts per-file Git"
    if not ns["tracked"](os.path.join(root,"src","Combat","Main","has space.cpp")):
        return "absolute/space path mismatch"
    if not ns["tracked"]("src\\Combat\\Main\\has space.cpp"):
        return "Windows slash alias mismatch"
    if not ns["tracked"]("../outside.cpp"): return "out-of-repo path not protected"
    if ns["tracked"]("src/Combat/Main/new.cpp"): return "untracked candidate protected as tracked"
    ns["sh"]("git","add","-A")
    if not ns["tracked"]("src/Combat/Main/new.cpp") or reads[0] != 2:
        return "newly staged source is not protected after refresh"
    for command in ("checkout","reset","commit","rm","mv","read-tree","update-index"):
        ns["sh"]("git",command)
        if ns["_TRACKED"] is not None: return "index mutation did not invalidate: " + command
        if ns["tracked"]("src/Combat/Main/new.cpp") != ("src/Combat/Main/new.cpp" in paths):
            return "membership did not refresh after " + command
    fail[0] = True
    ns["sh"]("git","reset")       # unsuccessful write must invalidate too
    removals = []
    try:
        if not ns["tracked"]("src/Combat/Main/new.cpp"): removals.append("new.cpp")
    except RuntimeError:
        pass
    else:
        return "failed/partial snapshot did not stop destructive phase"
    if removals or ns["_TRACKED"] is not None: return "failed snapshot published/reused a set"
    fail[0] = False
    truncated[0] = True
    try:
        ns["tracked"]("src/Combat/Main/new.cpp")
    except RuntimeError:
        pass
    else:
        return "successful-but-truncated snapshot did not fail closed"
    if ns["_TRACKED"] is not None: return "truncated snapshot published a set"
    truncated[0] = False
    paths.clear()
    if ns["tracked"]("src/empty.cpp"): return "successful empty index was not accepted"
    if '_r = sh("python", INT, *INTARGS)\n    _TRACKED = None' not in src:
        return "delegated mutation boundary no longer invalidates"

@check("finish_wave bulk index snapshot preserves tracked paths and fails closed before quarantine",
       "failed, unreadable or truncated snapshots could quarantine tracked source")
def _finish_bulk_snapshot_behaviour():
    import subprocess
    src = open(f"{KIT}/finish_wave.sh", encoding="utf-8").read()
    first = src.find("# BULK-TRACKED-BEGIN")
    last = src.find("# BULK-TRACKED-END")
    if first < 0 or last < first: return "bulk snapshot block missing"
    stop = src.find("# 5. STAGING", last)
    if stop < last: return "duplicate loop boundary missing"
    duplicate_phase = src[first:stop]
    addr_begin = src.find("addr_of() {")
    addr_end = src.find("# 4. QUARANTINE", addr_begin)
    if addr_begin < 0 or addr_end < addr_begin: return "address reader missing"
    address_reader = src[addr_begin:addr_end]
    if 'git ls-files --error-unmatch "$f"' in src: return "per-file Git query remains"
    bash, benv = _kp.bash()
    for mode in ("valid","empty","git-error","missing","unreadable","truncated","load-error"):
        os.makedirs(f"{SP}/handwork", exist_ok=True)
        root = tempfile.mkdtemp(prefix="fw_snapshot_",dir=f"{SP}/handwork").replace("\\","/")
        source = os.path.join(root,"src","Combat","Main")
        q = os.path.join(root,"quarantine")
        os.makedirs(source)
        os.makedirs(q)
        for filename, addr in (("has space.cpp","02000000"),("duplicate.cpp","02000000"),("new.cpp","02000001")):
            with open(os.path.join(source,filename),"w") as out:
                out.write("// USA: func_" + addr + "\n")
        with open(os.path.join(q,".done_main"),"w") as out: out.write("02000000\n")
        body = 'cd "$1" || exit 99; SP="$1/state"; Q="$1/quarantine"; OV=main; REGION_TAG=USA; TAGPRE=func_; SRCDIR="src/Combat/Main"; OWNDIRS=("$SRCDIR"); calls="$1/calls"\n'
        # Record actual quarantine moves without changing their arguments or result.
        body += 'mv() { printf "%s\\n" "$1" >> "$SP/../moves"; command mv "$@"; }\n'
        body += 'git() { echo x >> "$calls"; '
        if mode != "empty":
            body += 'printf "src/Combat/Main/has space.cpp' + ('"; ' if mode == "truncated" else '\\0"; ')
        if mode == "missing": body += 'rm -f "$_tracked_tmp"; '
        if mode == "unreadable": body += 'rm -f "$_tracked_tmp"; mkdir "$_tracked_tmp"; '
        body += 'return ' + ('128' if mode == "git-error" else '0') + '; }\n'
        if mode == "load-error": body += 'mapfile() { return 1; }\n'
        body += address_reader + duplicate_phase + '\n'
        body += 'echo safe > "$1/phase-entered"\n'
        r = subprocess.run([bash,"--noprofile","--norc","-c",body,"snapshot-test",root],capture_output=True,text=True,
                           env=benv)
        entered = os.path.isfile(root + "/phase-entered")
        success = mode in ("valid","empty")
        if success and (r.returncode != 0 or not entered):
            return mode + " snapshot failed: " + r.stderr[-200:]
        if not success and (r.returncode != 6 or entered):
            return mode + " snapshot reached destructive phase"
        expected = {"duplicate.cpp"} if mode == "valid" else ({"duplicate.cpp","has space.cpp"} if mode == "empty" else set())
        actual = {name for name in os.listdir(q) if name.endswith(".cpp")}
        if actual != expected: return mode + " quarantined wrong sources: " + repr(actual)
        remaining = {name for name in os.listdir(source) if name.endswith(".cpp")}
        if remaining != {"duplicate.cpp","has space.cpp","new.cpp"} - expected:
            return mode + " did not preserve source inputs"
        moves_path = root + "/moves"
        moves = open(moves_path).read().splitlines() if os.path.isfile(moves_path) else []
        if len(moves) != len(expected): return mode + " unexpected move calls"
        if len(open(root + "/calls").read().splitlines()) != 1:
            return "bulk loader did not run exactly one Git query"


@check("a red build log names its culprit for every attributable failure class",
       "only layout drift was parsed, so a duplicate symbol, compile error, undefined reference or "
       "malformed config line sent the wave into sequential full-ROM bisection")
def _culprits_from_red_logs():
    c = load("culprits")
    mwld = ".\\tools\\mwccarm\\2.0\\sp2p2\\mwldarm.exe: "
    cands = {"src/Combat/Overlay_28/func_ov028_021d9494.cpp": ("028", "021d9494"),
             "src/Combat/Overlay_0/ProcessCombatTurn_0215d63c.cpp": ("000", "0215d63c"),
             "src/Combat/Overlay_17/func_ov017_021d4e38.cpp": ("017", "021d4e38"),
             "src/Combat/Main/ReinitController02043204.cpp": ("main", "02043204"),
             "src/Combat/Main/Innocent_02000c9c.cpp": ("main", "02000c9c")}
    logs = {
        "021d9494": mwld + 'Multiply-defined: "func_ov028_021d9494"\n' + mwld + "in Committed_021d9494.o\n"
                    + mwld + "Previously defined in\n" + mwld + "func_ov028_021d9494.o\n",
        "0215d63c": "src\\Combat\\Overlay_0\\ProcessCombatTurn_0215d63c.cpp:726: undefined label 'L_0da4'\n",
        "021d4e38": mwld + "Linker command file error at line 10100\n" + mwld + "File not found: func_ov017_021d4e38.o\n",
        "02043204": mwld + "Undefined :\n" + mwld + '"ReinitController02043204(MessageWork*,\n' + mwld + 'int)"\n'
                    + mwld + 'Referenced from\n' + mwld + '"Committed_02050000()" in\n' + mwld + "Committed_02050000.o\n",
    }
    for want, log in logs.items():
        got = [a for _m, a, _p, _w in c.name(log + mwld + 'warning: The name "Innocent_02000c9c" was reused\n', cands)]
        if got != [want]:
            return f"{want}: named {got}"
    drift = "Symbol 'func_ov017_021d4e38' is expected to be at 0x021d4e38 but is at 0x00000010\n"
    if [a for _m, a, _p, _w in c.name(drift, cands)] != ["021d4e38"]:
        return "an unplaced object was not named"
    shifted = "Symbol 'x' is expected to be at 0x021d4e38 but is at 0x021d4e40\n"
    if c.name(shifted, cands):
        return "a shifted symbol blamed its own function instead of falling back to the boundary scan"
    crash = "FAILED: [code=3221225794] build/usa/src/Combat/Main/Innocent_02000c9c.o\n"
    if not c.transient(crash) or c.transient(logs["0215d63c"] + "FAILED: [code=1] build/usa/arm9.o\n"):
        return "a crashed tool was not told apart from a real compile or link failure"


@check("culprits ignores ninja's progress lines",
       "ninja prints `[n/N] <command>` for every object it compiles, so a red log blamed every candidate "
       "the build compiled and a cull set the good ones aside with the bad")
def _culprits_skip_progress():
    c = load("culprits")
    cands = {"src/Combat/Main/Innocent_02000c9c.cpp": ("main", "02000c9c"),
             "src/Combat/Main/Bad_02000d00.cpp": ("main", "02000d00")}
    mwcc = '"C:\\Python\\python.exe" tools/mwcc.py build\\usa\\src\\Combat\\Main\\%s.o ".\\mwccarm.exe" -c %s -o x\n'
    log = ("[1/3] " + mwcc % ("Innocent_02000c9c", "src\\Combat\\Main\\Innocent_02000c9c.cpp")
           + "[2/3] " + mwcc % ("Bad_02000d00", "src\\Combat\\Main\\Bad_02000d00.cpp")
           + "FAILED: [code=1] build/usa/src/Combat/Main/Bad_02000d00.o\n"
           + mwcc % ("Bad_02000d00", "src\\Combat\\Main\\Bad_02000d00.cpp")
           + "src\\Combat\\Main\\Bad_02000d00.cpp:3: undefined identifier 'x'\n")
    got = [a for _m, a, _p, _w in c.name(log, cands)]
    if got != ["02000d00"]:
        return f"named {got}"
    return None


@check("a symbol rename leaves another region's address defines pointing at that region",
       "the upstream merge renamed func_020c6ff8 (a JPN address) to the USA symbol at 0x020c6ff8 and "
       "turned redundant JPN defines into redirects to undeclared names: the JPN build stopped compiling")
def _rename_respects_region_blocks():
    ns = {"rewrite": load("regionblocks").rewrite}
    renames = {"func_020c2208": "Mat4x4_ConvertTo4x3", "func_020c552c": "_Z24SubmitBlock0x80IfNotBusyi",
               "func_020c6ff8": "_Z18MarkGBABusReleasedv"}
    pat = re.compile(r"\b(%s)\b" % "|".join(map(re.escape, renames)))
    jpn = {"func_020c3cd4": "Mat4x4_ConvertTo4x3", "func_020c6ff8": "func_020c6ff8"}
    text = ("#if defined(jpn)\n#define func_020c2208 func_020c3cd4\n#define func_020c552c func_020c6ff8\n"
            "#endif\nvoid f() { func_020c2208(); func_020c6ff8(); }\n")
    out, _n = ns["rewrite"](text, pat, renames, lambda region, raw: jpn.get(raw))
    want = ("#if defined(jpn)\n#define _Z24SubmitBlock0x80IfNotBusyi func_020c6ff8\n"
            "#endif\nvoid f() { Mat4x4_ConvertTo4x3(); _Z18MarkGBABusReleasedv(); }\n")
    if out != want:
        return "rewrote a region block wrongly:\n" + out


@check("regionsync keeps the ported modules that build when another ported module is red",
       "one bad JPN port turned ov025 red; regionsync restored all of config/jpn, so every later "
       "integration ported nothing to JPN")
def _regionsync_restores_only_red_modules():
    import subprocess
    from types import SimpleNamespace
    try:
        rs = load("regionsync")
    except SystemExit:
        return "importing regionsync ran it"
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="regionsync_regress_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        def git(*args):
            return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True).stdout.strip()
        main, ov025 = f"{root}/config/jpn/arm9", f"{root}/config/jpn/arm9/overlays/ov025"
        for folder in (ov025, f"{root}/extract/jpn", f"{root}/tools"):
            os.makedirs(folder)
        for folder in (main, ov025):
            with open(f"{folder}/delinks.txt", "w") as f:
                f.write("    .text start:0x02000000 end:0x02000004\n")
        with open(f"{root}/tools/port.py", "w") as f:
            f.write('import sys\nif "--help" in sys.argv:\n    print("--sync")\n    sys.exit()\n'
                    'for folder, name in (("config/jpn/arm9", "a"), ("config/jpn/arm9/overlays/ov025", "b")):\n'
                    '    with open(folder + "/delinks.txt", "a") as f:\n'
                    '        f.write(f"\\nsrc/{name}.cpp:\\n    complete\\n    .text start:0x2 end:0x4\\n")\n')
        git("init", "-q")
        git("config", "user.name", "regress")
        git("config", "user.email", "regress@localhost")
        git("add", "-A")
        git("commit", "-q", "-m", "base")

        def green():
            red = "src/b.cpp" in open(f"{ov025}/delinks.txt").read()
            return not red, "[INFO ] Check ARM9 main: OK\n[INFO ] Check overlay 25: checksum failed\n" if red else ""
        real = rs.run
        rs.run = lambda *args: (0, "") if args[0] == "ninja" else real(*args)
        rs.green = lambda regions: {region: green() for region in regions}
        rs.configure, rs.kitpaths = lambda region: (0, ""), SimpleNamespace(SP=root)
        cwd = os.getcwd()
        os.chdir(root)
        try:
            [(code, line)] = rs.sync([("jpn", "tools/port.py")])
        finally:
            os.chdir(cwd)
        if "src/a.cpp" not in git("show", "HEAD:config/jpn/arm9/delinks.txt"):
            return f"the module that built was not committed: {line}"
        if ("src/b.cpp" in git("show", "HEAD:config/jpn/arm9/overlays/ov025/delinks.txt")
                or git("status", "--porcelain", "--", "config")):
            return f"the red module was committed or left in the tree: {line}"
        if git("log", "-1", "--format=%s") != "Port 1 matched files to JPN" or code != 1:
            return f"reported as {code}: {line}"
    return None


@check("regionsync wires into usa a file another region delinks and usa does not",
       "#99 delinked five ov031 functions in JPN only, and nothing ported them to USA or EUR")
def _regionsync_into_usa():
    import subprocess
    from types import SimpleNamespace
    rs = load("regionsync")
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="regionsync_usa_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        files = {
            "config/usa/arm9/delinks.txt": "    .text       start:0x02000000 end:0x02001000 kind:code align:32\r\n"
                                           "\r\nsrc/Old.cpp:\r\n    complete\r\n    .text start:0x02000000 end:0x02000010\r\n",
            "config/usa/arm9/symbols.txt": "Old kind:function(arm,size=0x10) addr:0x02000000\n"
                                           "New kind:function(arm,size=0x20) addr:0x02000100\n"
                                           "Big kind:function(arm,size=0x8) addr:0x02000200\n"
                                           "Data kind:function(arm,size=0x10) addr:0x02000300\n"
                                           "Curated kind:function(arm,size=0x10) addr:0x02000700\n"
                                           "Grown kind:function(arm,size=0x30) addr:0x02000900\n",
            "config/jpn/arm9/delinks.txt": "src/New.cpp:\n    complete\n    .text start:0x02000180 end:0x020001a0\n\n"
                                           "src/Big.cpp:\n    complete\n    .text start:0x02000400 end:0x02000410\n\n"
                                           "src/Data.cpp:\n    complete\n    .text start:0x02000500 end:0x02000510\n"
                                           "    .data start:0x02100000 end:0x02100008\n\n"
                                           "src/Untagged.cpp:\n    complete\n    .text start:0x02000600 end:0x02000620\n\n"
                                           "src/Raw.cpp:\n    complete\n    .text start:0x02000800 end:0x02000810\n\n"
                                           "src/Grown.cpp:\n    complete\n    .text start:0x02000a00 end:0x02000a20\n",
            "src/Old.cpp": "// USA: Old\nvoid Old() {}\n",
            "src/New.cpp": "// USA: New\nvoid New() {}\n",
            "src/Big.cpp": "// USA: Big\nvoid Big() {}\n",
            "src/Data.cpp": "// USA: Data\nvoid Data() {}\n",
            "src/Untagged.cpp": "void Untagged() {}\n",
            "src/Raw.cpp": "// USA: func_02000700\nvoid Curated() {}\n",
            "src/Grown.cpp": "// USA: Grown\nvoid Grown() {}\n"}
        for path, text in files.items():
            os.makedirs(os.path.dirname(f"{root}/{path}"), exist_ok=True)
            with open(f"{root}/{path}", "w", encoding="utf-8", newline="") as f:
                f.write(text)
        for args in (("init", "-q"), ("config", "user.name", "regress"), ("config", "user.email", "regress@localhost"),
                     ("add", "-A"), ("commit", "-q", "-m", "base")):
            subprocess.run(["git", "-C", root, "-c", "core.autocrlf=false", *args], capture_output=True)
        real = rs.run
        rs.run = lambda *args: (0, "") if args[0] == "ninja" else real(*args)
        rs.green = lambda regions: {region: (True, "") for region in regions}
        rs.configure, rs.kitpaths = (lambda region: (0, "")), SimpleNamespace(SP=root)
        rs.usa_gate = lambda module, start, src: "MATCH" if src.endswith("Grown.cpp") else "RESIDUE SIZE 4"
        cwd = os.getcwd()
        os.chdir(root)
        try:
            runs = [rs.sync([("usa", None)])[0], rs.sync([("usa", None)])[0]]
        finally:
            os.chdir(cwd)
        with open(f"{root}/config/usa/arm9/delinks.txt", encoding="utf-8", newline="") as f:
            text = f.read()
        for name, start, end in (("New", "02000100", "02000120"), ("Raw", "02000700", "02000710"),
                                 ("Grown", "02000900", "02000930")):
            if f"\r\nsrc/{name}.cpp:\r\n    complete\r\n    .text start:0x{start} end:0x{end}\r\n" not in text:
                return f"{name}.cpp was not wired at its usa function: {text!r}"
        wrong = [n for n in ("Old", "Big", "Data", "Untagged") if text.count(f"src/{n}.cpp:") != (n == "Old")]
        if wrong:
            return f"wired into usa: {wrong}"
        for code, line in runs:
            missing = [n for n in ("Big.cpp: jpn: 0x10 bytes here, Big is 0x8 in usa, and the usa gate says RESIDUE",
                                   "Data.cpp: jpn: owns .text, .data",
                                   "Untagged.cpp: jpn: no `// USA:` tag") if f"NOT IN USA src/{n}" not in line]
            if code != 1 or missing or "in sync" in line:
                return f"exit {code}, unreported {missing}: {line}"
        if "Port 3 matched files to USA" not in runs[0][1]:
            return f"the port was not committed: {runs[0][1]}"
    return None


_FAKE_CONFIGURE = "\n".join([
    "import os, sys",
    "region = sys.argv[1]",
    "obj, arm9 = os.path.join('build', region, 'src', 'a.o'), os.path.join('build', region, 'arm9.o')",
    "lines = ['python = \"%s\"' % sys.executable,",
    "         'rule download_tool', '  command = $python tools/fake.py download $out',",
    "         'rule mwcc', '  command = $python tools/fake.py cc $out',",
    "         'rule mwld', '  command = $python tools/fake.py link $out',",
    "         'rule sha1', '  command = $python tools/fake.py sha1 $out',",
    "         'build tool.exe: download_tool',",
    "         'build %s: mwcc src/a.cpp | tool.exe' % obj,",
    "         'build %s: mwld %s' % (arm9, obj),",
    "         'build check: phony %s' % arm9,",
    "         'build sha1: sha1 %s' % arm9]",
    "open('build.ninja', 'w').write('\\n'.join(lines) + '\\n')",
    ""])
_FAKE_TOOL = "\n".join([
    "import os, sys, time",
    "what, out = sys.argv[1], sys.argv[2]",
    "os.makedirs('events', exist_ok=True)",
    "def note(edge):",
    "    name = '%s %s %s %d' % (what, out.replace('\\\\', '_').replace('/', '_'), edge, os.getpid())",
    "    open(os.path.join('events', name), 'w').write(repr(time.time()))",
    "note('start')",
    "if what == 'link':",
    "    time.sleep(2)",
    "if what == 'sha1':",
    "    sys.stderr.write('dqix.nds: OK\\n')",
    "else:",
    "    open(out, 'w').write(what)",
    "note('end')",
    ""])


@check("regionsync builds the regions at once from their own ninja files and compiles JPN objects without a link",
       "every three-region ninja check + sha1 ran one region after another (3.3-4 min a landing), the JPN "
       "port linked JPN only to read its objects, and a region file that kept download_tool made each "
       "region re-download mwccarm.exe and dsd.exe at once (PermissionError)")
def _regionsync_parallel_regions():
    import shutil
    rs = load("regionsync")
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="regionsync_par_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        for path, text in (("tools/configure.py", _FAKE_CONFIGURE), ("tools/fake.py", _FAKE_TOOL), ("src/a.cpp", "a\n")):
            os.makedirs(os.path.dirname(f"{root}/{path}"), exist_ok=True)
            with open(f"{root}/{path}", "w", encoding="utf-8") as fh:
                fh.write(text)

        def events():
            out = {name: open(os.path.join("events", name)).read() for name in os.listdir("events")}
            shutil.rmtree("events")
            return out
        cwd = os.getcwd()
        os.chdir(root)
        try:
            results = rs.green(["usa", "jpn", "eur"])
            built = events()
            files = {r: open(f"build/{r}/build.ninja", encoding="utf-8").read() for r in ("jpn", "eur")}
            logs = [r for r in ("jpn", "eur") if os.path.isfile(f"build/{r}/.ninja_log")]
            home = open("build.ninja", encoding="utf-8").read()
            os.utime(os.path.join("build", "jpn", "src", "a.o"), (1, 1))
            rs.compile_objects("jpn")
            compiled = events() if os.path.isdir("events") else {}
        finally:
            os.chdir(cwd)
    if sorted(results) != ["eur", "jpn", "usa"] or not all(ok for ok, _ in results.values()):
        return f"green() returned {results}"
    if sum(1 for name in built if name.startswith("download ") and " start " in name) > 1:
        return "more than one build downloaded the tools"
    links = {}
    for name, stamp in built.items():
        what, out, edge, _ = name.split(" ")
        if what == "link":
            links.setdefault(out, {})[edge] = float(stamp)
    if len(links) != 3 or max(t["start"] for t in links.values()) >= min(t["end"] for t in links.values()):
        return f"the regions did not link at the same time: {links}"
    for region, text in files.items():
        if not text.startswith(f"builddir = build/{region}\n") or "build tool.exe" in text:
            return f"build/{region}/build.ninja has no builddir of its own or still downloads tools"
    if logs != ["jpn", "eur"] or os.path.join("build", "usa", "arm9.o") not in home:
        return f"region logs {logs}; build.ninja left configured for another region"
    if not any(name.startswith("cc ") and "jpn" in name for name in compiled) or any(
            name.startswith("link ") for name in compiled):
        return f"compile_objects did not compile JPN's object without linking: {sorted(compiled)}"
    return None


@check("regionsync's JPN port compiles the objects it reads instead of linking JPN first",
       "regionsync ran a full `ninja -k 0 check` for JPN before every port only so port_jpn_config.py "
       "could read build/jpn/*.o; the link is 75-85% of a check")
def _regionsync_port_compiles_only():
    rs = load("regionsync")
    calls = []
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(f"{root}/extract/jpn")
        os.makedirs(f"{root}/tools")
        with open(f"{root}/tools/port.py", "w", encoding="utf-8") as fh:
            fh.write("")
        rs.run = lambda *args: calls.append(args) or (0, "--sync" if "--help" in args else "")
        rs.compile_objects = lambda region: calls.append(("compile_objects", region))
        rs.configure = lambda region: calls.append(("configure", region)) or (0, "")
        cwd = os.getcwd()
        os.chdir(root)
        try:
            done, _ = rs.port("jpn", "tools/port.py")
        finally:
            os.chdir(cwd)
    if done or ("compile_objects", "jpn") not in calls or any(c[:1] == ("ninja",) for c in calls):
        return f"the JPN port ran {calls}"
    return None


@check("regionsync's gate links every region with its port at once, and committing the port links nothing",
       "a landing linked USA in its gate, then regionsync ported it and linked JPN and EUR after it: two link "
       "phases per landing (335 s for a 29-function integrate_fast, 161 s of it regionsync)")
def _regionsync_gate_prebuilds_ports():
    import shutil
    import subprocess
    from types import SimpleNamespace
    rs = load("regionsync")
    if not hasattr(rs, "gate"):
        return "regionsync.py has no gate()"
    link = "'build %s: mwld %s' % (arm9, obj)"
    if link not in _FAKE_CONFIGURE:
        return "the fake configure no longer has the link edge this test makes depend on the config"
    configure = _FAKE_CONFIGURE.replace(link, "'build %s: mwld %s | config/%s/delinks.txt' % (arm9, obj, region)")
    port = ('import sys\nif "--help" in sys.argv:\n    print("--sync")\n    sys.exit()\n'
            'open("port_calls", "a").write("%s\\n")\n'
            'p = "config/%s/delinks.txt"\nif "src/b.cpp:" not in open(p).read():\n'
            '    open(p, "a").write("\\nsrc/b.cpp:\\n    .text start:0x2 end:0x4\\n")\n')
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="regionsync_gate_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        files = {"tools/configure.py": configure, "tools/fake.py": _FAKE_TOOL, "src/a.cpp": "a\n",
                 "tools/port_jpn.py": port % ("jpn", "jpn"), "tools/port_eur.py": port % ("eur", "eur"),
                 ".gitignore": "build/\nevents/\nport_calls\n*.ninja\n.ninja_*\ntool.exe\n"}
        files.update({f"config/{r}/delinks.txt": "src/a.cpp:\n    .text start:0x0 end:0x2\n" for r in ("usa", "jpn", "eur")})
        for path, text in files.items():
            os.makedirs(os.path.dirname(f"{root}/{path}"), exist_ok=True)
            with open(f"{root}/{path}", "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        for region in ("jpn", "eur"):
            os.makedirs(f"{root}/extract/{region}")
        for args in (("init", "-q"), ("config", "user.name", "regress"), ("config", "user.email", "regress@localhost"),
                     ("add", "-A"), ("commit", "-q", "-m", "base")):
            subprocess.run(["git", "-C", root, *args], capture_output=True)

        def links():
            if not os.path.isdir("events"):
                return {}
            out = {}
            for name in os.listdir("events"):
                what, target, edge, _ = name.split(" ")
                if what == "link":
                    out.setdefault(target, {})[edge] = float(open(os.path.join("events", name)).read())
            shutil.rmtree("events")
            return out
        with open(f"{root}/src/b.cpp", "w", encoding="utf-8") as fh:
            fh.write("b\n")
        with open(f"{root}/config/usa/delinks.txt", "a", encoding="utf-8") as fh:
            fh.write("\nsrc/b.cpp:\n    .text start:0x2 end:0x4\n")
        rs.PORTS = {"jpn": "tools/port_jpn.py", "eur": "tools/port_eur.py"}
        rs.kitpaths = SimpleNamespace(SP=root)
        cwd = os.getcwd()
        os.chdir(root)
        try:
            results, blocking = rs.gate(["jpn", "eur"])
            gated = links()
            ported = subprocess.run(["git", "status", "--porcelain", "--", "config/jpn", "config/eur"],
                                    capture_output=True, text=True).stdout.split("\n")[:-1]
            for args in (("add", "-A", "--", ".", ":(exclude)config/jpn", ":(exclude)config/eur"),
                         ("commit", "-q", "-m", "Match 1")):
                subprocess.run(["git", *args], capture_output=True)
            lines = rs.sync(list(rs.PORTS.items()))
            relinked = links()
            log = subprocess.run(["git", "log", "--format=%s"], capture_output=True, text=True).stdout.split("\n")
            calls = open("port_calls").read().split()
            again, _ = rs.gate(["jpn", "eur"])
            untouched = links()
        finally:
            os.chdir(cwd)
    if sorted(results) != ["eur", "jpn", "usa"] or not all(ok for ok, _ in results.values()) or blocking:
        return f"gate() returned {results} {blocking}"
    if len(gated) != 3 or max(t["start"] for t in gated.values()) >= min(t["end"] for t in gated.values()):
        return f"the gate did not link the three regions at once: {gated}"
    if sorted(p[3:] for p in ported) != ["config/eur/delinks.txt", "config/jpn/delinks.txt"]:
        return f"the gate left these changes for regionsync: {ported}"
    if relinked:
        return f"committing the ports the gate had built linked again: {sorted(relinked)}"
    if sorted(calls) != ["eur", "jpn"]:
        return f"the port tools ran again after the landing committed, on unchanged inputs: {calls}"
    if log[:3] != ["Port 1 matched files to EUR", "Port 1 matched files to JPN", "Match 1"]:
        return f"regionsync committed {log[:3]} ({lines})"
    if sorted(again) != ["usa"] or untouched:
        return f"a gate with nothing to port built {sorted(again)} and linked {sorted(untouched)}"
    return None


@check("a port tool that rewrites a config file unchanged leaves its timestamp alone",
       "a rewrite with identical bytes still bumps the mtime, and every delinks.txt feeds the region's delink "
       "step, so ninja relinks the whole region for nothing")
def _regionsync_port_keeps_mtime():
    rs = load("regionsync")
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(f"{root}/extract/jpn")
        os.makedirs(f"{root}/config/jpn/arm9")
        os.makedirs(f"{root}/tools")
        path = f"{root}/config/jpn/arm9/delinks.txt"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("src/a.cpp:\n")
        os.utime(path, (1_000_000_000, 1_000_000_000))
        with open(f"{root}/tools/port.py", "w", encoding="utf-8") as fh:
            fh.write('import sys\nif "--help" in sys.argv:\n    print("--sync")\n    sys.exit()\n'
                     'p = "config/jpn/arm9/delinks.txt"\nt = open(p).read()\nopen(p, "w").write(t)\n')
        rs.compile_objects = lambda region: None
        cwd = os.getcwd()
        os.chdir(root)
        try:
            done, _ = rs.port("jpn", "tools/port.py")
        finally:
            os.chdir(cwd)
        mtime = os.stat(path).st_mtime
    if done or mtime != 1_000_000_000:
        return f"port returned {done} and left the unchanged file's mtime at {mtime}"
    return None


@check("a region's depfiles and objects are read in parallel before ninja and mwld read them one at a time",
       "landpr #166 #167 spent 62-90 s at the start of each region's ninja before running anything: "
       "ninja reads the 13k depfiles one after another, 5.6 ms each when not cached, and mwld then reads "
       "every object the same way; 32 threads read 6378 cold depfiles in 2.2 s instead of 35.9 s")
def _regionsync_prewarms_depfiles():
    import threading
    import time as _time
    rs = load("regionsync")
    seen, ninja = {}, []
    real_open = open

    def opened(path, *args, **kwargs):
        seen[os.path.normpath(path)] = threading.get_ident()
        _time.sleep(0.005)
        return real_open(path, *args, **kwargs)
    with tempfile.TemporaryDirectory() as root:
        depfiles = [os.path.normpath(os.path.join("build", "jpn", top, f"d{n}", f"x{n}{ext}"))
                    for top in ("src", "libs", "delinks") for n in range(16) for ext in (".d", ".o")]
        for path in depfiles + [os.path.join("build", "jpn", "arm9.lcf")]:
            os.makedirs(os.path.dirname(f"{root}/{path}"), exist_ok=True)
            with real_open(f"{root}/{path}", "w") as fh:
                fh.write("x.o: x.cpp\n")
        rs.open = opened
        rs.run = lambda *args: ninja.append(dict(seen)) or (0, "OK")
        cwd = os.getcwd()
        os.chdir(root)
        try:
            rs.build("jpn")
        finally:
            os.chdir(cwd)
    if not ninja or set(ninja[0]) != set(depfiles):
        return "ninja ran before every depfile and object was read (%d of %d)" % (
            len(ninja[0]) if ninja else 0, len(depfiles))
    if len(set(ninja[0].values())) < 4:
        return "the depfiles and objects were read one at a time"
    return None


@check("regionsync builds usa alongside the regions it ports",
       "landpr built JPN and EUR for the ports, then usa alone afterwards: 3.2 minutes of a 12-minute "
       "landing spent on a build that could have run beside the others")
def _regionsync_builds_home_with_ports():
    rs = load("regionsync")
    calls = []
    rs.changed = lambda region: True
    rs.ported = lambda region: 1
    rs.green = lambda regions: calls.append(sorted(regions)) or {r: (True, "") for r in regions}
    rs.finish = lambda region, ok, dropped, files, log: (0, region)
    done = rs.settle({"jpn": "", "eur": ""})
    if calls != [["eur", "jpn", "usa"]] or sorted(done) != ["eur", "jpn"]:
        return "settle() built %s and reported %s" % (calls, sorted(done))
    return None


@check("integrate_all ports to the other regions once: in its last module's wave, or after the loop",
       "finish_wave ran regionsync (4-5 minutes) after each module it landed, so integrate_all paid it "
       "once per module; then regionsync.sh after the loop threw away the ports the last module's gate "
       "had already built and linked JPN and EUR a second time")
def _regionsync_once_per_integrate_all():
    import shutil
    import subprocess
    fw = open(f"{KIT}/finish_wave.sh", encoding="utf-8").read()
    if '[ "${DQIX_REGIONSYNC:-}" = defer ] || python "$KIT/regionsync.py"' not in fw:
        return "finish_wave runs regionsync.py even when its caller defers it"
    rs = open(f"{KIT}/regionsync.sh", encoding="utf-8").read()
    if "wave_lock_acquire" not in rs or "integ_tree.py\" publish" not in rs:
        return "regionsync.sh does not hold the wave lock and publish its ports"
    bash, benv = _kp.bash()
    got = {}
    for moves in ("004 main", "004"):
        with tempfile.TemporaryDirectory() as d:
            root = d.replace("\\", "/")
            kit, sp, repo = f"{root}/kit", f"{root}/sp", f"{root}/repo"
            for folder in (kit, f"{sp}/wlog", f"{sp}/staging/main", f"{sp}/staging/ov004", repo):
                os.makedirs(folder)
            shutil.copyfile(f"{KIT}/integrate_all.sh", f"{kit}/integrate_all.sh")
            files = {
                f"{kit}/kitpaths.py": f"import sys\nprint({{'state': {sp!r}, 'repo': {repo!r}}}[sys.argv[1]])\n",
                f"{kit}/cov.py": "",
                f"{kit}/finish_wave.sh": (f'echo "$1 ${{DQIX_REGIONSYNC:-inline}}" >> "{root}/calls"\n'
                                          f'case " {moves} " in *" $1 "*) git -C "{repo}" commit -q --allow-empty -m "$1";; esac\n'),
                f"{kit}/regionsync.sh": f'echo regionsync.sh >> "{root}/calls"\n',
                f"{sp}/staging/main/a.cpp": "", f"{sp}/staging/ov004/b.cpp": "", f"{sp}/staging/ov004/c.cpp": ""}
            for path, text in files.items():
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
            for args in (("init", "-q", "-b", "decomp-matching"), ("config", "user.name", "regress"),
                         ("config", "user.email", "regress@localhost"), ("commit", "-q", "--allow-empty", "-m", "base")):
                subprocess.run(["git", "-C", repo, *args], capture_output=True)
            subprocess.run([bash, f"{kit}/integrate_all.sh"], capture_output=True, text=True, env=benv)
            got[moves] = open(f"{root}/calls").read().split("\n")[:-1] if os.path.exists(f"{root}/calls") else []
    want = {"004 main": ["004 defer", "main inline"], "004": ["004 defer", "main inline", "regionsync.sh"]}
    bad = {moves: calls for moves, calls in got.items() if calls != want[moves]}
    if bad:
        return "modules that moved the branch -> calls: " + "; ".join(f"[{m}] {c}" for m, c in bad.items())
    return None


@check("landpr keeps both sides of a delinks.txt conflict and refuses a symbolic link",
       "#100 conflicted only because both sides appended delinks blocks; a pull request's symlink under src/ "
       "would have had the comment strip write through it")
def _landpr_merge():
    import subprocess
    lp = load("landpr")
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="landpr_regress_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        def git(*args):
            return subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                                  capture_output=True, text=True).stdout.strip()

        def commit(name):
            with open(f"{root}/delinks.txt", "a", encoding="utf-8") as f:
                f.write(f"\nsrc/{name}.cpp:\n    complete\n    .text start:0x{name} end:0x{name}4\n")
            git("commit", "-qam", name)

        git("init", "-q", "-b", "main")
        with open(f"{root}/delinks.txt", "w", encoding="utf-8") as f:
            f.write("src/A.cpp:\n    complete\n    .text start:0x0 end:0x4\n")
        git("add", "-A")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        git("checkout", "-qb", "pr")
        commit("2")
        blob = subprocess.run(["git", "-C", root, "hash-object", "-w", "--stdin"], input="/etc/passwd",
                              capture_output=True, text=True).stdout.strip()
        git("update-index", "--add", "--cacheinfo", f"120000,{blob},src/link.cpp")
        git("commit", "-qm", "link")
        pr = git("rev-parse", "HEAD")
        git("checkout", "-q", "main")
        commit("1")
        if not subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "--no-ff",
                               "-m", "Merge #5", pr], capture_output=True).returncode:
            return "the fixture did not conflict"
        if not lp.keep_both_delinks(root, pr):
            return f"a delinks.txt conflict where both sides added blocks was not resolved: {git('status', '-s')}"
        merged = git("show", "HEAD:delinks.txt")
        if git("log", "-1", "--format=%s") != "Merge #5" or not all(f"src/{n}.cpp:" in merged for n in "A12"):
            return f"the merge lost a side: {merged!r}"
        if lp.symlinks(root, base, pr) != ["src/link.cpp"]:
            return f"the symbolic link was not reported: {lp.symlinks(root, base, pr)}"
    return None


@check("landclean keeps every green rewrite and drops only the ones that red a region",
       "a cleaned source lands into a file already on decomp-matching; one bad rewrite in a batch must "
       "not cost the others, and a file that changed since its rewrite must not be overwritten")
def _landclean_settle():
    import subprocess
    lc = load("landclean")
    entries = [(f"src/{n}.cpp", "b", "") for n in "abcdef"]
    bad = {"src/c.cpp", "src/f.cpp"}
    got = lc.settle(entries, lambda part: (not bad & {rel for rel, _, _ in part}, set()))
    if [rel for rel, _, _ in got] != ["src/a.cpp", "src/b.cpp", "src/d.cpp", "src/e.cpp"]:
        return "settle() kept %s" % [rel for rel, _, _ in got]
    coupled = [(f"src/r{n}.cpp", "b", "remangle") for n in range(200)] + [("config/usa/s.txt", "b", "remangle")]
    calls = []
    got = lc.settle(coupled + [("src/x.cpp", "b", "")],
                    lambda part: calls.append(len(part)) or (not any(rel == "src/r7.cpp" for rel, _, _ in part), set()))
    if [rel for rel, _, _ in got] != ["src/x.cpp"] or len(calls) > 4:
        return ("settle() split a rename batch whose symbols.txt and sources only build together "
                "(%d checks, kept %d rows); 241 such rows once bisected for an hour" % (len(calls), len(got)))
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="landclean_regress_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        def git(*args):
            return subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                                  capture_output=True, text=True).stdout.strip()

        git("init", "-q", "-b", "main")
        for name in ("x", "y"):
            with open(f"{root}/{name}.cpp", "w", encoding="utf-8") as fh:
                fh.write(name)
        git("add", "-A")
        git("commit", "-qm", "base")
        x, y = git("rev-parse", "HEAD:x.cpp"), git("rev-parse", "HEAD:y.cpp")
        old = lc.CLEAN
        lc.CLEAN = root
        try:
            fresh, stale = lc.split_stale(root, [("x.cpp", x, ""), ("y.cpp", x, "")])
        finally:
            lc.CLEAN = old
        if [r for r, _, _ in fresh] != ["x.cpp"] or [r for r, _, _ in stale] != ["y.cpp"]:
            return "split_stale() kept %s and dropped %s" % (fresh, stale)
        rels = ["src/%s_%04d.cpp" % ("n" * 100, i) for i in range(400)]
        os.makedirs(f"{root}/src")
        for rel in rels:
            with open(f"{root}/{rel}", "w", encoding="utf-8") as fh:
                fh.write("x")
        lc.stage(root, rels)
        if len(git("diff", "--cached", "--name-only").splitlines()) != len(rels):
            return "landclean could not stage 400 long paths: 1586 cleaned sources once died at git add (WinError 206)"
    src = open(f"{KIT}/landclean.py", encoding="utf-8").read()
    if 'write_rows(MANIFEST, [], "w")' in src or "not in done" not in src:
        return "landclean empties the whole manifest, dropping rows cleanwork appended while it ran"
    with tempfile.TemporaryDirectory(prefix="landclean_strip_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        os.makedirs(f"{root}/clean/src", exist_ok=True)
        os.makedirs(f"{root}/tree/src", exist_ok=True)
        with open(f"{root}/clean/src/a.cpp", "w", encoding="utf-8") as fh:
            fh.write("// USA: func_a\nint a; // 0x70\n")
        old, old_git = lc.CLEAN, lc.git
        lc.CLEAN, lc.git = f"{root}/clean", lambda *a: (0, "")
        try:
            lc.apply(f"{root}/tree", "tip", [("src/a.cpp", "b", "")])
        finally:
            lc.CLEAN, lc.git = old, old_git
        landed = open(f"{root}/tree/src/a.cpp", encoding="utf-8").read()
        if "0x70" in landed or "// USA: func_a" not in landed:
            return "landclean landed a rewrite with its worker comments, or lost the region tag: %r" % landed
    return None


@check("landclean lands a rewrite saved as .c over a landed .cpp, renaming it in every delinks.txt",
       "landclean wrote a rewrite only over the same path, so canonical MSL C for 02009edc and 02001bdc, "
       "which matches only compiled as C, could not replace the invented unions their C++ files carry")
def _landclean_swaps_language():
    import subprocess
    lc = load("landclean")
    with tempfile.TemporaryDirectory(prefix="landclean_swap_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        tree, clean = f"{root}/tree", f"{root}/clean"

        def git(*args):
            return subprocess.run(["git", "-C", tree, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                                  capture_output=True, text=True).stdout.strip()

        for d in (f"{tree}/src", f"{tree}/config/usa", f"{tree}/config/eur", f"{clean}/src"):
            os.makedirs(d)
        block = "src/a.cpp:\n    complete\n    .text start:0x02000000 end:0x02000004\n"
        for region in ("usa", "eur"):
            with open(f"{tree}/config/{region}/delinks.txt", "w", encoding="utf-8", newline="\n") as fh:
                fh.write("src/b.cpp:\n    complete\n\n" + block)
        for name in ("a", "b"):
            with open(f"{tree}/src/{name}.cpp", "w", encoding="utf-8") as fh:
                fh.write(name)
        with open(f"{clean}/src/a.c", "w", encoding="utf-8") as fh:
            fh.write("// USA: func_a\nint a; // note\n")
        git("init", "-q", "-b", "main")
        git("add", "-A")
        git("commit", "-qm", "base")
        tip = git("rev-parse", "HEAD")
        row = ("src/a.cpp", git("rev-parse", "HEAD:src/a.cpp"), "")
        old = lc.CLEAN
        lc.CLEAN = clean
        try:
            fresh, stale = lc.split_stale(tree, [row])
            if fresh != [row]:
                return "split_stale() set aside a row whose rewrite is saved as .c: %r" % stale
            lc.apply(tree, tip, [], fresh)
            lc.apply(tree, tip, [row], fresh)
            lc.stage(tree, lc.touched(tree, tip, [row]))
            git("commit", "-qm", "clean")
        finally:
            lc.CLEAN = old
        files = sorted(git("ls-files").split())
        if files != ["config/eur/delinks.txt", "config/usa/delinks.txt", "src/a.c", "src/b.cpp"]:
            return "after landing the .c rewrite the tree holds %r" % files
        for region in ("usa", "eur"):
            text = git("show", f"HEAD:config/{region}/delinks.txt")
            if "src/a.c:" not in text or "src/a.cpp:" in text or "src/b.cpp:" not in text:
                return "%s delinks.txt after the swap: %r" % (region, text)
        if "note" in git("show", "HEAD:src/a.c"):
            return "the swapped rewrite kept its worker comment"
        lc.CLEAN = clean
        try:
            lc.apply(tree, tip, [], [row])
        finally:
            lc.CLEAN = old
        if os.path.exists(f"{tree}/src/a.c") or not os.path.exists(f"{tree}/src/a.cpp") or \
                "src/a.cpp:" not in open(f"{tree}/config/usa/delinks.txt", encoding="utf-8").read():
            return "apply() left a set-aside swap half applied: a.c %s, a.cpp %s" % (
                os.path.exists(f"{tree}/src/a.c"), os.path.exists(f"{tree}/src/a.cpp"))
    return None


@check("landclean sets aside the rows a red build names instead of halving the batch",
       "landclean.sh took 28 minutes for 61 rows with one bad row: settle() halved blind and rebuilt every "
       "region for each half, though the failure log named the file")
def _landclean_culls_named():
    lc = load("landclean")
    entries = [(f"src/f{n:02d}.cpp", "b", "") for n in range(61)]
    bad = entries[37]
    calls = []

    def check(part):
        calls.append(len(part))
        return bad not in part, {bad} if bad in part else set()
    got = lc.settle(entries, check)
    if set(got) != set(entries) - {bad} or len(calls) > 2:
        return "settle() kept %d of 60 good rows (bad row kept: %s) in %d builds" % (
            len(set(got) - {bad}), bad in got, len(calls))
    return None


@check("landclean builds the tip once instead of bisecting a batch the tip already reds",
       "an all-red batch cost 10-20 minutes of halving, and every row was rejected though the red was "
       "decomp-matching's own")
def _landclean_red_tip():
    lc = load("landclean")
    entries = [(f"src/f{n:02d}.cpp", "b", "") for n in range(20)]
    calls = []
    got = lc.settle(entries, lambda part: calls.append(len(part)) or (False, set()))
    if got is not None or len(calls) > 2:
        return "settle() returned %r after %d builds of a batch the tip reds" % (got, len(calls))
    calls.clear()
    got = lc.settle(entries[:4], lambda part: calls.append(len(part)) or (len(part) < 2, set()))
    if got is None or len(got) != 1:
        return "settle() treated a green tip as red, or kept %r" % got
    return None


@check("landclean lands only a set it built green as one",
       "settle() returned the union of halves it had built apart, so two rewrites green alone and red "
       "together would land without ever being built together")
def _landclean_lands_what_it_built():
    lc = load("landclean")
    a, b, c = [(f"src/{n}.cpp", "b", "") for n in "abc"]
    built = []

    def check(part):
        ok = not (a in part and b in part)
        built.append((frozenset(part), ok))
        return ok, set()
    got = frozenset(lc.settle([a, b, c], check))
    if not got or (got, True) not in built:
        return "settle() kept %s, a set it never built green" % sorted(r for r, _, _ in got)
    return None


@check("landclean rebuilds once when a tool crashed instead of blaming the batch",
       "three regions build at once now; an out-of-memory or crashed tool in one of them would have "
       "set rows aside that build, and settle() trusts a red result it has seen once")
def _landclean_retries_crash():
    from types import SimpleNamespace
    lc = load("landclean")
    logs = ["FAILED: [code=3221225794] build/jpn/src/a.o\n", ""]
    calls = []

    def green(regions):
        log = logs[len(calls)]
        calls.append(log)
        return {region: (not log or region != "jpn", log) for region in regions}
    lc.regionsync = SimpleNamespace(green=green, failed_folders=lambda log, region: set(), BLOCK=re.compile("x"))
    lc.apply = lambda *args: None
    ok, blamed = lc.verdict("tree", "tip", [("src/a.cpp", "b", "")], [])
    if not ok or len(calls) != 2:
        return "a crashed build counted as red (%d builds, ok=%s)" % (len(calls), ok)
    return None


@check("landclean rewrites only the files whose content changes between builds",
       "apply() checked the tree out again and rewrote every row each round, so every row and every "
       "includer of a rewritten header recompiled in each region on every bisection step")
def _landclean_apply_keeps_mtimes():
    import subprocess
    lc = load("landclean")
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="landclean_apply_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        tree, clean = f"{root}/tree", f"{root}/clean"

        def git(*args):
            return subprocess.run(["git", "-C", tree, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                                  capture_output=True, text=True).stdout.strip()
        for n in "ab":
            for folder, text in ((tree, f"int {n};\n"), (clean, f"int {n}2;\n")):
                os.makedirs(f"{folder}/src", exist_ok=True)
                with open(f"{folder}/src/{n}.cpp", "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
        git("init", "-q", "-b", "main")
        git("config", "core.autocrlf", "false")
        git("add", "-A")
        git("commit", "-qm", "base")
        tip = git("rev-parse", "HEAD")
        rows = [("src/a.cpp", "x", ""), ("src/b.cpp", "x", "")]
        a, b = f"{tree}/src/a.cpp", f"{tree}/src/b.cpp"
        lc.CLEAN = clean
        lc.apply(tree, tip, rows[:1], rows)
        os.utime(a, ns=(10 ** 9, 10 ** 9))
        lc.apply(tree, tip, rows, rows)
        if os.stat(a).st_mtime_ns != 10 ** 9:
            return "apply() rewrote src/a.cpp though its rewrite was already in place"
        os.utime(a, ns=(10 ** 9, 10 ** 9))
        lc.apply(tree, tip, rows[:1], rows)
        if open(b, encoding="utf-8").read() != "int b;\n" or os.stat(a).st_mtime_ns != 10 ** 9:
            return "apply() did not restore only the row that left the batch"
        os.utime(b, ns=(10 ** 9, 10 ** 9))
        lc.apply(tree, tip, rows[:1], rows)
        if os.stat(b).st_mtime_ns != 10 ** 9:
            return "apply() checked out a row already at the tip"
    return None


@check("landclean reads every row's blob at HEAD in one git process",
       "split_stale() ran one git rev-parse per row, one process start per cleaned file")
def _landclean_split_stale_batched():
    import subprocess
    lc = load("landclean")
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="landclean_stale_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        for n in "xyz":
            with open(f"{root}/{n}.cpp", "w", encoding="utf-8") as fh:
                fh.write(n)
        for args in (("init", "-q"), ("add", "-A"), ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "b")):
            subprocess.run(["git", "-C", root, *args], capture_output=True)
        blob = {n: subprocess.run(["git", "-C", root, "rev-parse", f"HEAD:{n}.cpp"], capture_output=True,
                                  text=True).stdout.strip() for n in "xyz"}
        calls = []
        lc.git = lambda *args: calls.append(args) or (0, "")
        lc.CLEAN = root
        fresh, stale = lc.split_stale(root, [("x.cpp", blob["x"], ""), ("y.cpp", blob["x"], ""),
                                             ("z.cpp", blob["z"], ""), ("gone.cpp", blob["z"], "")])
        if calls:
            return "split_stale() ran git once per row (%d calls)" % len(calls)
        if [r for r, _, _ in fresh] != ["x.cpp", "z.cpp"] or [r for r, _, _ in stale] != ["y.cpp", "gone.cpp"]:
            return "split_stale() kept %s and dropped %s" % (fresh, stale)
    return None


@check("landpr builds the three regions in one parallel build",
       "landpr.sh took 9.6 minutes for 2 functions, 6.5 of them region links run one after another")
def _landpr_builds_regions_at_once():
    from types import SimpleNamespace
    lp = load("landpr")
    calls = []
    with tempfile.TemporaryDirectory() as root:
        for region in lp.REGIONS:
            os.makedirs(f"{root}/extract/{region}")
        lp.regionsync = SimpleNamespace(
            green=lambda regions: calls.append(tuple(regions)) or {r: (True, "") for r in regions},
            configure=lambda region: calls.append(("configure", region)))
        lp.build_every_region(root)
    if calls != [tuple(lp.REGIONS)]:
        return "landpr built %s" % calls
    return None


@check("cleancheck accepts dropping only the invented volatile and refuses touching a real one",
       "0205e330's queue counts are written by a VCount interrupt consumer; a cleanup that strips every "
       "volatile in a file would remove the real ones with the invented")
def _cleancheck():
    C = load("cleancheck")
    before = ["struct Q { volatile int count; };", "    x = *(volatile int*)&e->id;", "    y = 1;"]
    good = ["struct Q { volatile int count; };", "    x = e->id;", "    y = 1;"]
    bad = ["struct Q { int count; };", "    x = *(volatile int*)&e->id;", "    y = 1;"]
    if C.check(before, good, {2})[0] or C.check(before, good, {2})[2] >= 2:
        return "cleancheck refused a rewrite that dropped only the invented volatile"
    if not C.check(before, bad, {2})[0]:
        return "cleancheck accepted a rewrite that dropped a real volatile"
    pun = ["void f(S* p) {", "    if (*(int*)p == 0) return;", "    g(p->ptr);", "}"]
    plain = ["void f(S* p) {", "    if (p->ptr == 0) return;", "    g(p->ptr);", "}"]
    swap = ["void f(S* p) {", "    S* q = p; q++;", "    if ((q - 1)->ptr == 0) return;", "    g(p->ptr);", "}"]
    if not C.accepted(pun, plain, {2})[0]:
        return "cleancheck refused a rewrite that removed an integer-read null test"
    if C.accepted(pun, swap, {2})[0]:
        return "cleancheck accepted a rewrite that swapped one invented construct for another"
    sentinel = pun[:2] + ["    if (p->n > -1) g(p->ptr);", "}"]
    if C.accepted(sentinel, pun[:2] + ["    if (p->n >= 0) g(p->ptr);", "}"], {2})[0]:
        return "cleancheck accepted a rewrite that removed only an advisory finding"
    work = open(f"{KIT}/cleanwork.sh", encoding="utf-8").read()
    if 'plausible.py" --blocking "$1"' not in work:
        return "cleanwork counts advisory findings as work left"
    import subprocess
    finished = re.search(r"(?m)^finished\(\) \{.*\}$", work).group(0)
    with tempfile.TemporaryDirectory(prefix="cleanretry_", dir=f"{SP}/handwork", ignore_cleanup_errors=True) as root:
        log = f"{root}/clean.log"
        with open(log, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("01:00 BLOCKED 0200aaaa x\n01:00 CLEAN 0200bbbb x\n01:05 RETRY 0200bbbb\n"
                     "01:00 KEEP 0200cccc x\n01:05 RETRY 0200cccc\n01:09 BLOCKED 0200cccc y\n")
        script = f"{finished}\nLOG='{log}'\nfor a in 0200aaaa 0200bbbb 0200cccc 0200dddd; do finished $a && echo $a; done\n"
        bash, benv = _kp.bash()
        done = subprocess.run([bash, "-c", script], capture_output=True, text=True, env=benv).stdout.split()
    if done != ["0200aaaa", "0200cccc"]:
        return "cleanwork's finished() after RETRY lines: %r, want ['0200aaaa', '0200cccc']" % done
    if 'grep -qi "^$ADDR " "$KIT/asm_allow.txt"' not in work:
        return "cleanwork stages hand-asm off asm_allow.txt, which the integrator parks and cleanwork restages"
    pull = open(f"{KIT}/pull_all.sh", encoding="utf-8").read()
    if 'claim.py" --best 2>/dev/null); _rc=$?' not in pull or "update_blocked=$SECONDS" not in pull:
        return "pull_all.sh reads claim.py's refusal as drained pools, or latches a blocked kit update forever"
    sweep = re.search(r'(?m)^\s*if \[ "\$SWEEP_EVERY" -gt 0 \].*\n.*then$', pull)
    if not sweep or '[ "${_behind:-0}" -eq 0 ]' not in sweep.group(0):
        return "pull_all.sh starts a 2.5h repair sweep while the kit is behind, so the update and every claim wait on it"
    old = os.environ.get("LEVERCHECK_DOCS")
    os.environ["LEVERCHECK_DOCS"] = "worker_src/core.md"
    try:
        docs = load("levercheck").doc_paths()
    finally:
        if old is None:
            del os.environ["LEVERCHECK_DOCS"]
        else:
            os.environ["LEVERCHECK_DOCS"] = old
    if docs != [os.path.normpath(f"{KIT}/worker_src/core.md")]:
        return "levercheck resolves a relative LEVERCHECK_DOCS entry against the cwd: %r" % docs
    return None


@check("plausible.py flags an extern \"C\" mangled declaration whose parameter count the mangling contradicts",
       "a 020709ec cleanup replaced a volatile local with a fourth argument to InitListBuffers02070a30, "
       "whose mangled name and definition take three")
def _plausible_mangle_arity():
    P = load("plausible")
    name = "_Z23InitListBuffers02070a30P14Struct02070a30P13SafeAllocatorPv"
    bad = 'extern "C" void %s(void*, void*, void*, unsigned int);\n' % name
    good = 'extern "C" void %s(void*, void*, void*);\n' % name
    member = 'extern "C" void _ZN16BackgroundLoader13AddLockGlobalEv(void*);\n'
    if "MANGLE-ARITY-MISMATCH" not in repr(P.findings(bad)):
        return "plausible.py missed a fourth argument to a three-parameter mangled function"
    arity = [h for h in P.findings(good) + P.findings(member) if h[1] == "MANGLE-ARITY-MISMATCH"]
    if arity:
        return "plausible.py flagged a declaration that matches its mangling: %r" % arity
    return None


@check("plausible.py flags an accessor or alias used beside the direct access it re-reads",
       "cleanup workers swapped volatile for `GetSize(s) < s->count; s->size <<= 1;` (0203e6c8) and "
       "`counts = data; if (counts[1]) return x[data[1] - 1];` (020a1fd4): the same reload, a new disguise")
def _plausible_mixed_access():
    P = load("plausible")
    mixed = ("static inline unsigned short GetSize(const L* s) { return s->size; }\n"
             "void f(L* s) {\n    if (GetSize(s) < s->count) s->size <<= 1;\n}\n")
    alias = ("extern unsigned char data[];\nint f(void) {\n    const unsigned char* counts = data;\n"
             "    if (counts[1] != 0) return x[data[1] - 1];\n    return 0;\n}\n")
    plain = ("static inline unsigned short GetSize(const L* s) { return s->size; }\n"
             "void f(L* s) {\n    if (GetSize(s) < s->count) Grow(s);\n}\n")
    if "MIXED-ACCESS-RELOAD" not in repr(P.findings(mixed)):
        return "plausible.py missed an accessor beside a direct access to the same field"
    if "ALIAS-REREAD" not in repr(P.findings(alias)):
        return "plausible.py missed a one-use alias beside the global it aliases"
    if [k for _, k, _ in P.findings(plain) if k in ("MIXED-ACCESS-RELOAD", "ALIAS-REREAD")]:
        return "plausible.py flagged an accessor used alone: %r" % P.findings(plain)
    return None


@check("plausible.py flags source transliterated from the listing: register-named variables or address labels",
       "83 functions were written one instruction per statement (`unsigned int r4 = 0; r4 = r0; ... goto L1c;`); "
       "a contributor reported his agent doing the same")
def _plausible_transliterated():
    P = load("plausible")
    bad = ("extern \"C\" unsigned int f(unsigned int r0, unsigned int r1) {\n    unsigned int r4 = 0;\n"
           "    r4 = r0;\n    if (r4 == 0) goto L1c;\n    g(r4);\nL1c:;\n    return r0;\n}\n")
    good = ("extern \"C\" void f(Obj* self, int id) {\n    if (self->count != 0) {\n        g(self, id);\n"
            "    }\n}\n")
    if "TRANSLITERATED" not in repr(P.findings(bad)):
        return "plausible.py missed register-named variables and an address label"
    if [k for _, k, _ in P.findings(good) if k == "TRANSLITERATED"]:
        return "plausible.py flagged natural source as transliterated"
    return None


@check("plausible.py catches the mirrored `-1 < x` and the inline split add a worker used to dodge it",
       "cleanup workers rewrote `index > -1` as `-1 < index` (0204027c) and `p += 0x2c00; p[0x5c]` as "
       "`((sub + 0x5c) + 0x2c00)` (020abd20)")
def _plausible_dodges():
    P = load("plausible")
    wrap = "void f(void) {\n    %s\n}\n"
    for bad, kind in (("if (-1 < index) g();", "COMPARE-MINUS-ONE"),
                      ("x = *(int*)((sub + 0x5c) + 0x2c00);", "SPLIT-POINTER-ADD")):
        if kind not in repr(P.findings(wrap % bad)):
            return "plausible.py missed %s in %r" % (kind, bad)
    for good in ("x = (a - 1 < b);", "y = (p + i) + 0x100;", "z = base + 0x2c5c;"):
        if P.findings(wrap % good):
            return "plausible.py flagged %r: %r" % (good, P.findings(wrap % good))
    return None


@check("asmgen spells capstone's UAL mnemonics the way mwasmarm and the inline assembler accept",
       "the CW soft-float runtime (_dflt, _feq, _fmul, _dmul ...) failed to assemble on `lsls`, `andseq`, "
       "`popeq` emitted as `ldmiaeq`, and `msr apsr_nzcvq`")
def _asmgen_ual():
    G = load("asmgen")
    cases = [(("lsls", "r0, r0, ip"), ("movs", "r0, r0, lsl ip")),
             (("lsrle", "r3, r3, #0x10"), ("movle", "r3, r3, lsr #0x10")),
             (("lslseq", "r2, r2, #1"), ("moveqs", "r2, r2, lsl #1")),
             (("andseq", "r2, r0, #1"), ("andeqs", "r2, r0, #1")),
             (("ldmiaeq", "sp!, {r4, lr}"), ("ldmeqia", "sp!, {r4, lr}")),
             (("ldm", "r0, {r1, r2}"), ("ldmia", "r0, {r1, r2}")),
             (("popeq", "{r4, lr}"), ("ldmeqia", "sp!, {r4, lr}")),
             (("push", "{r4, lr}"), ("stmdb", "sp!, {r4, lr}")),
             (("msr", "apsr_nzcvq, ip"), ("msr", "cpsr_f, ip")),
             (("mrs", "ip, apsr"), ("mrs", "ip, cpsr")),
             (("ldrhne", "r3, [r0, #-1]"), ("ldrneh", "r3, [r0, #-1]")),
             (("bls", "_L18"), ("bls", "_L18")),
             (("subs", "r2, r2, #1"), ("subs", "r2, r2, #1")),
             (("rsbmi", "r0, r0, #0"), ("rsbmi", "r0, r0, #0"))]
    for given, want in cases:
        got = G.normalise(*given)
        if got != want:
            return "asmgen.normalise%r gave %r, want %r" % (given, got, want)
    return None


@check("plausible.py flags a ternary whose two arms are the same expression",
       "ov024 021dc93c matched with `f(c, obj->action ? obj->context : obj->context)` to hoist a load")
def _plausible_same_arms():
    P = load("plausible")
    wrap = "void f(Obj* obj) {\n    %s\n}\n"
    for bad in ("g(c, obj->action ? obj->context : obj->context);", "x = k ? h(a) : h(a);", "p = k ? 'a' : 'a';"):
        if "TERNARY-SAME-ARMS" not in repr(P.findings(wrap % bad)):
            return "plausible.py missed TERNARY-SAME-ARMS in %r" % bad
    for good in ("g(c, obj->action ? obj->context : 0);", "x = k ? a + b : b;", "y = k ? s->a : s->ab;",
                 "int pad = (flag & 16) ? '0' : ' ';"):
        if [k for _, k, _ in P.findings(wrap % good) if k == "TERNARY-SAME-ARMS"]:
            return "plausible.py flagged %r" % good
    return None


@check("plausible.py blocks an extern \"C\" declaration or definition of a mangled C++ name",
       "Eakeys: 9332 `extern \"C\" void _Z20Clear12Bytes020e46c4Pv(void*);` redeclarations in 2362 landed "
       "sources call C++ functions under their symbol instead of their name")
def _plausible_extern_c_mangled():
    P = load("plausible")
    for bad in ('extern "C" void* _Z20Clear12Bytes020e46c4Pv(void*);\n',
                'extern "C" ARM int _Z3Fooi(int x) { return x; }\n',
                'extern "C" void _ZN16BackgroundLoader13AddLockGlobalEv(void);\n'):
        if "EXTERN-C-MANGLED" not in [k for _, k, _ in P.blocking(bad)]:
            return "plausible.py did not block %r" % bad
    dtor = 'extern "C" ARM Loader* _ZN20Ov33BackgroundLoaderD1Ev(Loader* self)%s\n'
    if "EXTERN-C-MANGLED" not in [k for _, k, _ in P.blocking(dtor % ";")]:
        return "plausible.py did not block a destructor declared under its mangled name"
    for good in ('void* Clear12Bytes020e46c4(void*);\n', 'extern "C" void func_0204500c(void*);\n',
                 '// extern "C" void _Z3Fooi(int);\n', dtor % " { return self; }"):
        if [k for _, k, _ in P.findings(good) if k == "EXTERN-C-MANGLED"]:
            return "plausible.py flagged %r" % good
    return None


@check("plausible.py blocks a source defining a game class a header already defines",
       "cleanwork rewrote 0201e574's extern \"C\" view as a member of a local `class ZoneFeatures` with "
       "an invented layout instead of including World/ZoneFeatures.h")
def _plausible_type_redefined():
    P = load("plausible")
    P.GAME_TYPES = {"ZoneFeatures", "Vector3i", "VRAMSubregion"}
    for bad in ("class ZoneFeatures {\npublic:\n    int count;\n};\n", "struct Vector3i { int x, y, z; };\n",
                "enum VRAMSubregion {\n    VRAMSubregion_TexturePalette = 0\n};\n"):
        if "TYPE-REDEFINED" not in [k for _, k, _ in P.blocking(bad)]:
            return "plausible.py did not block %r" % bad
    for good in ('#include "World/ZoneFeatures.h"\nstruct ZoneFeatures;\n', "struct Entry0201e574 { int f0; };\n",
                 "// struct Vector3i { int x; };\n", "ZoneFeatures::Opcode64Entry* e;\n"):
        if [k for _, k, _ in P.findings(good) if k == "TYPE-REDEFINED"]:
            return "plausible.py flagged %r" % good
    return None


@check("retype_returns gives a function the class every call casts its result to, and drops the casts",
       "121 casts of call results to one class stood in for a void* or int return type nobody fixed at the "
       "definition")
def _retype_returns():
    R = load("retype_returns")
    original = {"src/a.cpp": "void* Lookup(int i) {\n    return 0;\n}\n",
                "src/b.cpp": "struct Entry { int a; };\nvoid* Lookup(int i);\n"
                             "void f() { ((Entry*)Lookup(1))->a = 0; static_cast<Entry*>(Lookup(2))->a = 1; }\n",
                "src/c.cpp": "struct Other;\nvoid* Find(int i) {\n    return 0;\n}\n"
                             "void g() { (Other*)Find(1); (Entry*)Find(2); }\n"}
    found = R.candidates(original)
    if found != {"Lookup": ("Entry", "void*")}:
        return "candidates gave %r" % found
    a = R.rewrite(original["src/a.cpp"], "Lookup", "Entry", "void*")
    b = R.rewrite(original["src/b.cpp"], "Lookup", "Entry", "void*")
    if "Entry* Lookup(int i) {" not in a or "struct Entry;" not in a:
        return "the definition was not retyped and given the class: %r" % a
    if "Entry* Lookup(int i);" not in b or "{ Lookup(1)->a = 0;" not in b or "Lookup(2)->a = 1" not in b:
        return "the declaration or the casts were left: %r" % b
    return None


@check("plausible.py blocks reinterpret_cast and a byte-pointer parameter cast to the game class it really is",
       "a source took `char* self` and wrote `reinterpret_cast<MessageSystem*>(self)` under jpn instead of "
       "typing the parameter MessageSystem* and carrying that type to its callers")
def _plausible_casts():
    P = load("plausible")
    P.GAME_TYPES = {"MessageSystem"}
    hack = 'extern "C" void f(char* self, int state) {\n    MessageSystem* m = %s;\n}\n'
    for bad, kind in ((hack % "reinterpret_cast<MessageSystem*>(self)", "REINTERPRET-CAST"),
                      (hack % "(MessageSystem*)self", "PARAM-RETYPED"),
                      ("int g(void* p) { return reinterpret_cast<int>(p); }\n", "REINTERPRET-CAST")):
        if kind not in [k for _, k, _ in P.blocking(bad)]:
            return "plausible.py did not block %s in %r" % (kind, bad)
    for good in ('extern "C" void f(MessageSystem* self, int state) {\n    MessageSystem* m = self;\n}\n',
                 'void f(char* buf) {\n    char* p = (char*)(buf + 4);\n}\n',
                 'void f(void* p) {\n    MessageSystem* m = (MessageSystem*)p;\n}\n'):
        if [k for _, k, _ in P.findings(good) if k in ("REINTERPRET-CAST", "PARAM-RETYPED", "BYTE-SELF")]:
            return "plausible.py flagged %r" % good
    raw = 'extern "C" void f(char* self, int state) {\n    int i = *(int*)(self + 0x78);\n}\n'
    if "BYTE-SELF" not in [k for _, k, _ in P.blocking(raw)]:
        return "plausible.py did not block a function taking its object as `char* self`"
    twice = ("void f(S* s) {\n    g(static_cast<MapEntryList*>(s->list));\n    h((MapEntryList*)s->list);\n}\n",
             "void f() {\n    ((Entry*)Lookup(1))->a = 0;\n    ((Entry*)Lookup(2))->b = 0;\n}\n")
    for bad in twice:
        if "REPEATED-CAST" not in [k for _, k, _ in P.blocking(bad)]:
            return "plausible.py did not block one shared value cast to the same type twice: %r" % bad
    once = "void f(S* s) {\n    g(static_cast<MapEntryList*>(s->list));\n    h((Other*)s->list);\n}\n"
    if [k for _, k, _ in P.findings(once) if k == "REPEATED-CAST"]:
        return "plausible.py flagged two different casts as a repeat"
    apart = "void f() {\n    ((Entry*)Lookup(1))->a = 0;\n}\nvoid g() {\n    ((Entry*)Lookup(2))->b = 0;\n}\n"
    if [k for _, k, _ in P.findings(apart) if k == "REPEATED-CAST"]:
        return "plausible.py flagged one cast in each of two functions as a repeat"
    return None


@check("addrname appends the USA address to a mangled function's own name and maps it through the object",
       "Eakeys maps our matches onto his branch by address: 1593 landed names like `_Z10SetWord0x0Pii` "
       "carried none")
def _addrname():
    import shutil
    A = load("addrname")
    cases = [("_Z10SetWord0x0Pii", "_0200fb84", "_Z19SetWord0x0_0200fb84Pii"),
             ("_ZNK9GameState7GetTimeEv", "_ov017_021afe00", "_ZNK9GameState22GetTime_ov017_021afe00Ev"),
             ("_ZN6Script9Parameter5ToIntEv", "_02030b0c", "_ZN6Script9Parameter14ToInt_02030b0cEv")]
    for old, suffix, want in cases:
        if A.renamed(old, suffix) != want:
            return "renamed(%s) gave %s, want %s" % (old, A.renamed(old, suffix), want)
    for skipped in ("_ZN20Ov33BackgroundLoaderD1Ev", "_ZN5Vec3iaSERKS_", "_Z3maxIiET_S0_S0_", "func_02000000"):
        if A.own_name(skipped):
            return "own_name accepted %s, which has no plain own name to extend" % skipped
    if A.renamed("fix32_Atan2_Rescaled", "_02001234") != "fix32_Atan2_Rescaled_02001234":
        return "a plain C name did not take the suffix"
    for name, want in (("fix32_Atan2_Rescaled", True), ("labs", False), ("_dmul", False), ("func_02000000", False)):
        if A.plain_name(name) != want:
            return "plain_name(%s) is %s; runtime and C library names keep theirs" % (name, not want)
    if shutil.which("c++filt"):
        info = ("_Z3FooP3Objit", None, "Foo", ["Obj*", "int", "short"], ["Obj*", "int", "unsigned short"])
        decl = A.retype("struct Obj;\nvoid Foo(Obj* o, int a, short b);\nvoid g(Obj* o) { Foo(o, 1, 2); }\n",
                        "_Z3FooP3Objis", info)
        if "void Foo(Obj* o, int a, unsigned short b);" not in decl or "Foo(o, 1, 2); }" not in decl:
            return "retype left the old declaration: %r" % decl
        view = A.retype('struct Obj;\nextern "C" void _Z3FooP3Objis(Obj*, int, unsigned short);\n'
                        "void h(Obj* o) { _Z3FooP3Objis(o, 1, 2); }\n", "_Z3FooP3Objis", info)
        if "void Foo(Obj*, int, unsigned short);" not in view or "{ Foo(o, 1, 2); }" not in view:
            return "retype left the extern \"C\" view: %r" % view
        import collections
        probe, A.probe_name = A.probe_name, lambda qual, ident, params, const: "_Z7Get_0x1P3Ctxi"
        views = {"src/a.cpp": 'struct Ctx;\nextern "C" int _Z7Get_0x1v(Ctx* c, int i);\n'
                              "int f(Ctx* c) { return _Z7Get_0x1v(c, 1); }\n",
                 "src/b.cpp": 'struct Ctx;\nextern "C" int _Z7Get_0x1v(Ctx* p, int i);\n'
                              "int g(Ctx* p) { return _Z7Get_0x1v(p, 2); }\n"}
        try:
            got = A.remangle_targets(views, collections.defaultdict(set, {"Get_0x1": {"_Z7Get_0x1v"}}))
            split = A.remangle_targets(dict(views, **{"src/b.cpp": views["src/b.cpp"].replace("Ctx* p", "char* p")}),
                                       collections.defaultdict(set, {"Get_0x1": {"_Z7Get_0x1v"}}))
            generic = A.remangle_targets({rel: t.replace("Ctx* ", "void* ") for rel, t in views.items()},
                                         collections.defaultdict(set, {"Get_0x1": {"_Z7Get_0x1v"}}))
        finally:
            A.probe_name = probe
        if got.get("_Z7Get_0x1v", (None,) * 5)[4] != ["Ctx*", "int"]:
            return "callers passing two arguments to a no-parameter name were not remangled to (Ctx*, int): %r" % got
        if split or generic:
            return "callers disagreeing on the added pointer's class, or passing void*, still renamed it: %r" % (
                split or generic)
        info = got["_Z7Get_0x1v"]
        body = A.retype("int Get_0x1(void) {\n    return 0;\n}\n", "_Z7Get_0x1v", info)
        if "int Get_0x1(Ctx*, int) {" not in body:
            return "the definition did not take the callers' parameters: %r" % body
        if "struct Ctx;\n" not in A.declare('#include "a.h"\n' + body, "int Get_0x1(void) {}\n", info[4]):
            return "a definition retyped to a class its file never names got no forward declaration"
        probe, A.probe_name = A.probe_name, lambda qual, ident, params, const: "_Z3BarP3Obj"
        try:
            got = A.remangle_targets({"src/a.cpp": 'struct Obj;\nextern "C" void _Z3Bari(Obj* o);\n'
                                                   "void f(Obj* o) { _Z3Bari(o); }\n"},
                                     collections.defaultdict(set, {"Bar": {"_Z3Bari"}}))
        finally:
            A.probe_name = probe
        if got.get("_Z3Bari", (None,) * 5)[4] != ["Obj*"]:
            return "a caller passing a pointer to a guessed int parameter kept the int: %r" % got
        cast = A.uncast("void Bar(Obj*);\nvoid f(Obj* o) { Bar((int)o); }\n", got["_Z3Bari"])
        if "{ Bar(o); }" not in cast:
            return "the (int) an earlier rewrite added to fit the old name was kept: %r" % cast
        probe, A.probe_name = A.probe_name, lambda qual, ident, params, const: "_Z3BazP10GameObjecti"
        try:
            got = A.cast_targets({"src/b.cpp": "struct GameObject;\nint Baz(int, int);\n"
                                               "int g(GameObject* self, short s) { return Baz((int)self, (int)s); }\n"
                                               "int h(char* raw) { return Baz((int)raw, 0); }\n"},
                                 collections.defaultdict(set, {"Baz": {"_Z3Bazii"}}))
            refined = A.refine_targets({"src/c.cpp": "struct GameObject;\nint Baz(void*, int);\n"
                                                     "int k(GameObject* g) { return Baz(g, 1); }\n"},
                                       collections.defaultdict(set, {"Baz": {"_Z3BazPvi"}}), {"_Z3BazPvi"})
        finally:
            A.probe_name = probe
        if got:
            return "calls casting a GameObject* and a char* to the same parameter still proposed a type: %r" % got
        if refined.get("_Z3BazPvi", (None,) * 5)[4] != ["GameObject*", "int"]:
            return "a void* parameter every call passes a GameObject* to was not retyped: %r" % refined
        probe, A.probe_name = A.probe_name, lambda qual, ident, params, const: "_Z3BazP10GameObjecti"
        try:
            got = A.cast_targets({"src/b.cpp": "struct GameObject;\nint Baz(int, int);\n"
                                               "int g(GameObject* self, short s) { return Baz((int)self, (int)s); }\n"},
                                 collections.defaultdict(set, {"Baz": {"_Z3Bazii"}}))
        finally:
            A.probe_name = probe
        if got.get("_Z3Bazii", (None,) * 5)[4] != ["GameObject*", "int"]:
            return "an (int) cast of a GameObject* did not type the parameter GameObject*: %r" % got
    sig = [(("_Z3Foov", 0, 4, "STT_FUNC", "STB_GLOBAL", ".text"), ("_Z3Barv", 0, 0, "STT_NOTYPE", "STB_GLOBAL",
                                                                  "SHN_UNDEF")),
           (".text", b"\x00" * 4), (".rela.text", ((0, 1, "_Z3Barv"),))]
    got = A.remap(sig, {"_Z3Barv": "_Z12Bar_02000000v"})
    if got[2] != (".rela.text", ((0, 1, "_Z12Bar_02000000v"),)) or "_Z12Bar_02000000v" not in repr(got[0]):
        return "remap left the old name: %r" % got
    return None


@check("retype reads function, signature and member requests the way cleanup workers write them",
       "105 BLOCKED RETYPE rows each waited on a hand edit across files the worker was told not to touch")
def _retype_parse():
    R = load("retype")
    funcs = {"AllocateEntryArrayFromVariant0207f12c", "SetVecYFromValue02033874", "GetField0x17dBits4To5IfFlag8_020795cc",
             "IssueSlotCommand3_17_02239e48", "ApplyEventTag_021cf024", "DispatchWithHalfwords_021ca2d8",
             "CopyObjectFields02048588", "RegisterCombatantSlot_0200fd38"}
    known = set(R.mechclean.BUILTIN_WORDS) | {"Script", "Parameter", "GameObject", "Obj02033874", "Struct02012ff0",
                                              "Animation3D", "GameResources", "GameState", "Object3D"}
    read = lambda text: [got for _g, got in R.parse_request(text, funcs, known)]
    one = read("AllocateEntryArrayFromVariant0207f12c(p) Script::Parameter*")
    if one != [[{"kind": "fn", "name": "AllocateEntryArrayFromVariant0207f12c", "names": ["p"], "olds": [], "index": [],
                 "sig": None, "ret": None, "type": "Script::Parameter*", "all": False}]]:
        return "a named parameter request read as %r" % one
    two = read("SetVecYFromValue02033874(Obj02033874*)+GetField0x17dBits4To5IfFlag8_020795cc(unsigned char*) GameObject*")
    if [(c["name"], c["olds"], c["type"]) for c in two[0]] != [
            ("SetVecYFromValue02033874", ["Obj02033874*"], "GameObject*"),
            ("GetField0x17dBits4To5IfFlag8_020795cc", ["unsigned char*"], "GameObject*")]:
        return "two functions selected by their old parameter types read as %r" % two
    sig = read("IssueSlotCommand3_17_02239e48 int (void (*)(void*), unsigned short)")[0][0]
    if sig["ret"] != "int" or [t for t, _ in sig["sig"]] != ["void (*)(void*)", "unsigned short"]:
        return "a whole signature with a function pointer read as %r" % sig
    pos = read("ApplyEventTag_021cf024(param 4 base) GameResources* — bytes match")[0][0]
    named = read("DispatchWithHalfwords_021ca2d8 parameter ov should be GameResources* (bytes stay exact)")[0][0]
    third = read("RegisterCombatantSlot_0200fd38 Object3D* (its third parameter; also more)")[0][0]
    if (pos["index"], pos["names"], named["names"], third["index"]) != ([3], ["base"], ["ov"], [2]):
        return "positional, named and ordinal parameters read as %r, %r, %r" % (pos, named, third)
    members = read("Struct02012ff0::field8/fieldc Animation3D *")[0]
    if [(m["cls"], m["member"], m["type"]) for m in members] != [("Struct02012ff0", "field8", "Animation3D *"),
                                                                   ("Struct02012ff0", "fieldc", "Animation3D *")]:
        return "two members of one class read as %r" % members
    placed = read("GameObject::(member at 0x150, 0x144 on jpn) GameObject*")[0][0]
    if (placed["member"], placed["offset"]) != (None, 0x150):
        return "an unnamed member placed by its USA offset read as %r" % placed
    for prose in ("GameState::unk_397d/unk_6fc0 GameState needs real members", "GameObject::source a pointer to it",
                  "CopyObjectFields02048588"):
        if not all(isinstance(got, str) for got in read(prose)):
            return "prose with no type was read as a request: %r" % read(prose)
    return None


@check("retype drops the casts a retyped parameter, return or member forced, and retargets only a C-style cast",
       "a retype that left `reinterpret_cast<Old*>(x)` at every call kept the cast it was made to remove; one that "
       "retargeted a reinterpret_cast added a line prready refuses")
def _retype_rewrites():
    R = load("retype")
    A = load("addrname")
    info = ("_Z1FP3New", None, "F", ["Old*"], ["New*"])
    text = ("void F(New*);\nvoid g(New* x, Other* y) {\n    F(reinterpret_cast<Old*>(x));\n    F((Old*)y);\n"
            "    F(reinterpret_cast<Old*>(y));\n    F((Old*)(y + 1));\n}\n")
    got = A.uncast(text, info, {(2, 0), (3, 0)})
    want = ("void F(New*);\nvoid g(New* x, Other* y) {\n    F(x);\n    F((New*)y);\n    F(y);\n    F(y + 1);\n}\n")
    if got != want:
        return "call casts rewritten to %r" % got
    reads = ("void f(S* a, T* t) {\n    if (a->f8) reinterpret_cast<Anim *>(a->f8)->Go();\n"
             "    t->f8 = reinterpret_cast<int>(alloc());\n    ((Anim*)(t->f8))->Go();\n}\n")
    plain = R.member_uncast(reads, "f8", "Anim*", "int")
    kept = R.member_uncast(reads, "f8", "Anim*", "int", {0})
    if "if (a->f8) a->f8->Go();" not in plain or "t->f8 = alloc();" not in plain or "    t->f8->Go();" not in plain:
        return "member reads and stores rewritten to %r" % plain
    if "t->f8 = static_cast<Anim*>(alloc());" not in kept:
        return "a store the new type cannot take bare was not retargeted with static_cast: %r" % kept
    value = R.member_uncast("void f(S* s) {\n    g(&(*reinterpret_cast<Foo*>(s->m)));\n    Foo* p = (Foo*)s->m;\n}\n",
                            "m", "Foo", "char[0x88]")
    if "g(&s->m);" not in value or "Foo* p = &s->m;" not in value:
        return "a padding array retyped to a class was not taken by address: %r" % value
    body = "    ((Manager*)(obj))->Reset();\n"
    at = body.index("obj")
    done = R.drop_cast_around(body, at, at + 3, {A.unconst("Manager*")})
    if not done or done[0] != "    obj->Reset();\n":
        return "a cast of a retyped parameter left %r" % (done and done[0])
    pad = {"type": "char", "name": "unk_6fc0", "dims": "[0x7ff4 - 0x6fc0]"}
    split = R.split_pad(pad, 0x6fc0, 0x7ff4, 0x7f58, 2, "short unk_7f58", "    ")
    if split != "char unk_6fc0[0x7f58 - 0x6fc0];\n    short unk_7f58;\n    char unk_7f5a[0x7ff4 - 0x7f5a]":
        return "a member added inside padding split it as %r" % split
    return None


@check("addrname.settle drops only the change whose unit compiles differently and names that unit",
       "retype and --remangle each grew their own verify-and-drop loop")
def _addrname_settle():
    A = load("addrname")
    real = A.mechclean.verify

    def verify(original, new, mapping, jobs, work, first=False):
        bad = [rel for rel, text in sorted(new.items()) if "bad" in text]
        return (bad[:1] if first else bad), {rel: [] for rel in bad}
    texts = lambda targets: ({"src/%s.cpp" % k: v for k, v in targets.items()}, {})
    dropped = {}
    A.mechclean.verify = verify
    try:
        got = A.settle({}, {"a": "bad", "b": "ok", "c": "ok"}, texts, lambda bad, seen, t: set(t), 1, "", dropped)
    finally:
        A.mechclean.verify = real
    if got is None or sorted(got[0]) != ["b", "c"] or dropped != {"a": "src/a.cpp"}:
        return "settle kept %r and dropped %r" % (got and sorted(got[0]), dropped)
    return None


@check("retype mangles a nested or typedef'd class the way mwcc does",
       "MessageGlyphSlot is a typedef of State0204166c and Script::Parameter a nested struct; a probe that declared "
       "them as plain structs computed a name no object exports")
def _retype_mangle():
    A = load("addrname")
    R = load("retype")
    nested = A.probe_name(None, "Foo", ["Script::Parameter*", "int"], False)
    if nested != "_Z3FooPN6Script9ParameterEi":
        return "a nested class parameter mangled as %r" % nested
    plan = object.__new__(R.Plan)
    plan.aliases = {"MessageGlyphSlot": "State0204166c", "Vector3fix": "Vector3i", "fix32_t": "int32_t",
                    "int32_t": "signed int"}
    canon = [plan.canon(t) for t in ("MessageGlyphSlot*", "Vector3fix*", "fix32_t")]
    if canon != ["State0204166c*", "Vector3i*", "signed int"]:
        return "typedefs resolved to %r" % canon
    got = A.probe_name(None, "Foo", canon[:2], False)
    if got != "_Z3FooP13State0204166cP8Vector3i":
        return "typedef'd parameters mangled as %r" % got
    return None


@check("mechclean renames an extern \"C\" mangled free function only when the object stays identical",
       "the 5978 redeclarations whose parameters spell the mangling are a rename; the 410 whose widths "
       "contradict it change the call and need a worker")
def _mechclean_extern_c():
    import shutil
    M = load("mechclean")
    text = ('extern "C" void* _Z20Clear12Bytes020e46c4Pv(void*);\nextern "C" void _ZN3Foo3BarEv(void*);\n'
            'extern "C" ARM void f(void* p) { _Z20Clear12Bytes020e46c4Pv(p); _ZN3Foo3BarEv(p); }\n'
            'void* table[] = { (void*)&_Z20Clear12Bytes020e46c4Pv };\n')
    want = ('void* Clear12Bytes020e46c4(void*);\nextern "C" void _ZN3Foo3BarEv(void*);\n'
            'extern "C" ARM void f(void* p) { Clear12Bytes020e46c4(p); _ZN3Foo3BarEv(p); }\n'
            'void* table[] = { (void*)&Clear12Bytes020e46c4 };\n')
    if M.extern_c_mangled(text) != want:
        return "rewrite gave %r" % M.extern_c_mangled(text)
    member = ('extern "C" int _ZNK9GameState7GetTimeEv(void* gs);\n'
              'extern "C" GameState* _ZN9GameState11GetInstanceEv(void);\n'
              'int f(S* s) { return _ZNK9GameState7GetTimeEv(s->gs) + '
              '_ZNK9GameState7GetTimeEv(&s->state) + _ZNK9GameState7GetTimeEv(_ZN9GameState11GetInstanceEv()); }\n')
    want = ('int f(S* s) { return s->gs->GetTime() + s->state.GetTime() + '
            'GameState::GetInstance()->GetTime(); }\n')
    got = M.apply_names(member, {"_ZNK9GameState7GetTimeEv", "_ZN9GameState11GetInstanceEv"})
    if got != want:
        return "member rewrite gave %r" % got
    if shutil.which("c++filt"):
        free = ('struct Entry;\nextern "C" void _Z10SetFlag0x1Pj(Entry* e);\n'
                'void f(Entry* e) { _Z10SetFlag0x1Pj((Entry*)g(e)); }\n')
        want = 'struct Entry;\nvoid SetFlag0x1(unsigned int*);\nvoid f(Entry* e) { SetFlag0x1((unsigned int*)g(e)); }\n'
        if M.typed_call(free, "_Z10SetFlag0x1Pj", False, False) != want:
            return "typed rewrite gave %r" % M.typed_call(free, "_Z10SetFlag0x1Pj", False, False)
        member = ('struct Model3D {\n    int x;\n};\nextern "C" void _ZN7Model3D4DrawEb(void* m, short b);\n'
                  'void f(void* p, int k) { _ZN7Model3D4DrawEb(p, k); }\n')
        got = M.typed_call(member, "_ZN7Model3D4DrawEb", True, False) or ""
        if "    void Draw(bool);\n};" not in got or "((Model3D*)p)->Draw((short)k)" not in got:
            return "typed member rewrite gave %r" % got
        nested = ('class Script {\npublic:\n    struct Parameter {\n        int ToInt() const;\n    };\n};\n'
                  'extern "C" int _ZNK6Script9Parameter5ToIntEv(void* p);\nint f(void* p) { return '
                  '_ZNK6Script9Parameter5ToIntEv(p); }\n')
        got = M.typed_call(nested, "_ZNK6Script9Parameter5ToIntEv", False, False) or ""
        if "return ((Script::Parameter*)p)->ToInt(); }" not in got:
            return "nested member rewrite gave %r" % got
        punned = 'struct Obj;\nextern "C" void _Z3Bari(Obj* o);\nvoid f(Obj* o) { _Z3Bari(o); }\n'
        for scalar_cast in (False, True):
            got = M.typed_call(punned, "_Z3Bari", scalar_cast, False)
            if got is not None:
                return "a pointer passed to a guessed int parameter was cast to a number: %r" % got
        assign = ('struct Vector3i { int x, y, z; Vector3i& operator=(const Vector3i&); };\n'
                  'extern "C" void _ZN8Vector3iaSERKS_(void* dst, const void* src);\n'
                  'void f(Vector3i* a, char* b) { Vector3i v; _ZN8Vector3iaSERKS_(&v, b + 4); }\n')
        got = M.typed_call(assign, "_ZN8Vector3iaSERKS_", False, False) or ""
        if "v = *(Vector3i const*)(b + 4);" not in got:
            return "operator= rewrite gave %r" % got
        if M.apply_names(assign, {"_ZN8Vector3iaSERKS_": 0}) is not None:
            return "a strategy that leaves the mangled name in place counted as a rewrite"
        definition = ('struct ZoneFeatures {\n    int n;\n};\nstruct Foo;\nstruct SafeAllocator;\n'
                      'extern "C" ARM void _ZN12ZoneFeatures23AllocateOpcode64EntriesEiP13SafeAllocator('
                      'struct Foo* obj, int count, SafeAllocator* alloc) {\n    g(obj, count, alloc);\n}\n')
        got = M.typed_def(definition, "_ZN12ZoneFeatures23AllocateOpcode64EntriesEiP13SafeAllocator", False) or ""
        if ("ARM void ZoneFeatures::AllocateOpcode64Entries(int count, SafeAllocator* alloc) {\n"
                "    struct Foo* obj = (struct Foo*)this;\n    g(obj" not in got
                or "    void AllocateOpcode64Entries(int, SafeAllocator*);\n};" not in got):
            return "definition rewrite gave %r" % got
        header = "#pragma once\nclass Model3D {\npublic:\n    int x;\n};\n"
        source = 'extern "C" void _ZN7Model3D4DrawEb(void* m, int on);\nvoid f(void* p) { _ZN7Model3D4DrawEb(p, 1); }\n'
        old = M.class_header
        M.class_header = lambda qual: "Graphics/Model3D.h" if qual == "Model3D" else None
        try:
            got = M.method_decls({"include/Graphics/Model3D.h": header, "src/A.cpp": source})
        finally:
            M.class_header = old
        if got.get("include/Graphics/Model3D.h") != header.replace("};", "    void Draw(bool);\n};"):
            return "method_decls gave %r" % got
        for arg, declared, real, want in (("(Actor*)self", "Actor*", "void*", "(Actor*)self"),
                                          ("(struct Ref*)(base + 0x4c8)", "struct Ref* r", "Mutex*",
                                           "(Mutex*)(base + 0x4c8)")):
            if M.convert(arg, declared, real, False) != want:
                return "convert(%r) gave %r, want %r" % (arg, M.convert(arg, declared, real, False), want)
    if M.TREE_FIXABLE != {"EXTERN-C-MANGLED"}:
        return "--tree rewrites kinds that need a gate, which it cannot run without a module: %s" % M.TREE_FIXABLE
    work = tempfile.mkdtemp()
    try:
        path = f"{work}/probe.cpp"
        mixed = ('#include <globaldefs.h>\nextern "C" void _Z3Bari(int);\nextern "C" void _Z3Foot(int);\n'
                 'extern "C" ARM void f(int x) { _Z3Bari(x); _Z3Foot(x); }\n')
        got = M.externc_clean(mixed, path)
        if "void Bar(int);" not in got or 'extern "C" void _Z3Foot(int);' not in got:
            return "externc_clean kept the wrong renames: %r" % got
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


@check("implausible code is held, not landed: prready refuses new findings and the fleet holds a flagged match",
       "plausible.py findings only triggered one cleanup try and then landed anyway, and landpr never "
       "checked them (user, 2026-10-12: block, clean, then land)")
def _implausible_blocks():
    import subprocess
    pr = load("plausible")
    clean = "void f(S* p) {\n    if (p->ptr == 0) return;\n}\n"
    pun = "void f(S* p) {\n    if (*(int*)p == 0) return;\n}\n"
    if pr.gained(clean, pun) != ["INT-PUN-NULL-TEST"]:
        return "prready did not report a finding the change adds: %r" % pr.gained(clean, pun)
    if pr.gained(pun, pun):
        return "prready blamed a change for a finding the tip already had"
    regs = "// USA: func_0202c9ac\nvoid f(Info* d, u32 r1, u32 r2) {\n    d->p = r1 | r2 << 4;\n}\n"
    if pr.gained("", regs) != ["TRANSLITERATED"]:
        return "register-named variables do not block: %r" % pr.gained("", regs)
    natural = "void f(int* p) {\n    int ret = *p;\n    ret = (ret < 0) ? -ret : ret;\n    *p = ret;\n}\n"
    if pr.gained("", natural):
        return "a construct real game code uses blocks: %r" % pr.gained("", natural)
    old = pr.ALLOW_FILE
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write("0202c9ac TRANSLITERATED reviewer the SDK names these r1/r2\n")
    pr.ALLOW_FILE = fh.name
    try:
        if pr.gained("", regs):
            return "an approved exception in plausible_allow.txt still blocks"
    finally:
        pr.ALLOW_FILE = old
        os.unlink(fh.name)
    worker = open(f"{KIT}/pull_worker.sh", encoding="utf-8").read()
    if 'plausible.py" --hold' not in worker or 'if [ -n "$_held" ]; then' not in worker:
        return "pull_worker.sh still stages a match plausible.py flags after its cleanup"
    for script in ("integrate.py", "ov_recover.py"):
        if "_plausible.hold(" not in open(f"{KIT}/{script}", encoding="utf-8").read():
            return "%s lands a staged match plausible.py flags (gated/ rescue bypasses the worker's hold)" % script
    with tempfile.TemporaryDirectory(prefix="plaushold_", dir=f"{SP}/handwork", ignore_cleanup_errors=True) as sp:
        src = f"{sp}/f_0202c9ac.cpp"
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("// USA: func_0202c9ac\n" + pun)
        if pr.hold(src, "main", "0202c9ac", sp) != ["INT-PUN-NULL-TEST"]:
            return "plausible.hold did not hold a flagged source"
        row = open(f"{sp}/wlog/clean_queue.tsv", encoding="utf-8").read().split("\t")
        if row[:2] != ["main", "0202c9ac"] or not os.path.exists(row[2]) or row[5].strip() != "staging":
            return "plausible.hold queued %r" % row
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("// USA: func_0202c9ac\n" + clean)
        if pr.hold(src, "main", "0202c9ac", sp):
            return "plausible.hold held a clean source"
    lp = load("landpr")
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="landpr_fixes_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        tree, fixes = f"{root}/tree", f"{root}/fixes"
        os.makedirs(f"{tree}/src", exist_ok=True)
        os.makedirs(f"{fixes}/src", exist_ok=True)

        def git(*args):
            return subprocess.run(["git", "-C", tree, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                                  capture_output=True, text=True).stdout.strip()

        git("init", "-q", "-b", "main")
        with open(f"{tree}/src/a.cpp", "w", encoding="utf-8") as fh:
            fh.write(pun)
        git("add", "-A")
        git("commit", "-qm", "Merge #5")
        with open(f"{fixes}/src/a.cpp", "w", encoding="utf-8") as fh:
            fh.write(clean)
        old = lp.git
        def fake_git(t, *a):
            r = subprocess.run(["git", "-C", t, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                               capture_output=True, text=True)
            return r.returncode, r.stdout

        lp.git = fake_git
        try:
            lp.apply_fixes(tree, fixes, ["5"])
        finally:
            lp.git = old
        if git("log", "-1", "--format=%s") != "Clean #5" or "*(int*)" in open(f"{tree}/src/a.cpp").read():
            return "landpr --fixes did not commit the cleaned source as `Clean #5`"
        os.makedirs(f"{tree}/config/usa", exist_ok=True)
        with open(f"{tree}/src/b.cpp", "w", encoding="utf-8") as fh:
            fh.write(pun)
        with open(f"{tree}/config/usa/delinks.txt", "w", encoding="utf-8") as fh:
            fh.write("src/a.cpp:\n    complete\n    .text start:0x0 end:0x4\n\nsrc/b.cpp:\n    complete\n"
                     "    .text start:0x4 end:0x8\n")
        git("add", "-A")
        git("commit", "-qm", "Merge #6")
        with open(f"{fixes}/DROP", "w", encoding="utf-8") as fh:
            fh.write("src/b.cpp\n")
        lp.git = fake_git
        try:
            lp.apply_fixes(tree, fixes, ["6"])
        finally:
            lp.git = old
        links = open(f"{tree}/config/usa/delinks.txt", encoding="utf-8").read()
        if os.path.exists(f"{tree}/src/b.cpp") or "src/b.cpp" in links or "src/a.cpp" not in links:
            return "landpr --fixes DROP did not remove the held file and only its delinks block"
        os.unlink(f"{fixes}/DROP")
        git("checkout", "-qb", "pr")
        with open(f"{tree}/src/a.cpp", "w", encoding="utf-8") as fh:
            fh.write("struct Unused {};\n" + clean)
        git("commit", "-qam", "theirs")
        git("checkout", "-q", "main")
        with open(f"{tree}/src/a.cpp", "w", encoding="utf-8") as fh:
            fh.write("struct Other {};\n" + clean)
        git("commit", "-qam", "ours")
        with open(f"{fixes}/src/a.cpp", "w", encoding="utf-8") as fh:
            fh.write(clean)
        lp.git = fake_git
        try:
            code = fake_git(tree, "merge", "--no-ff", "-m", "Merge #7", "pr")[0]
            took = code and lp.take_fixes(tree, fixes)
        finally:
            lp.git = old
        if not code or not took or git("rev-parse", "HEAD^2") != git("rev-parse", "pr"):
            return "landpr --fixes did not resolve a conflict in a file it replaces with the fixed version"
        if open(f"{tree}/src/a.cpp", encoding="utf-8").read() != clean:
            return "landpr --fixes resolved a conflict to something other than the fixed version"
        os.makedirs(f"{tree}/tools", exist_ok=True)
        os.makedirs(f"{fixes}/tools", exist_ok=True)
        with open(f"{tree}/tools/configure.py", "w", encoding="utf-8") as fh:
            fh.write("PYTHON = 1\n")
        git("add", "-A")
        git("commit", "-qm", "Merge #8")
        with open(f"{fixes}/tools/configure.py", "w", encoding="utf-8") as fh:
            fh.write("PYTHON = 2\n")
        lp.git = fake_git
        try:
            lp.apply_fixes(tree, fixes, ["8"])
        finally:
            lp.git = old
        if git("log", "-1", "--format=%s") != "Clean #8" or git("status", "--porcelain"):
            return "landpr --fixes left a fixed file outside src/ uncommitted"
    return None


@check("buildcfg falls back to the default assembler flags when a configure.py defines none",
       "wgate.py crashed on eakeys/text because that branch's configure.py has no AS_FLAGS")
def _buildcfg_as_flags():
    src = open(f"{KIT}/buildcfg.py", encoding="utf-8").read()
    if "_cfg.AS_FLAGS.split()" in src or 'getattr(_cfg, "AS_FLAGS"' not in src:
        return "buildcfg.py still requires configure.py to define AS_FLAGS"
    return None


def _member_layout(fields, size=0x40):
    sub = {"size": 8, "fields": [_member_field("x", "short", 0, 2), _member_field("y", "short", 2, 2),
                                 _member_field("z", "int", 4, 4)]}
    return {"types": {"Obj": {"size": size, "fields": fields}, "Sub": sub}, "typedefs": {"u16": "unsigned short"},
            "enums": []}


def _member_field(name, base, off, size, ptr=0, elem=()):
    return {"name": name, "base": base, "ptr": ptr, "dims": len(elem), "off": off, "size": size, "elem": list(elem)}


@check("offsetmembers names the member the compiler places at a byte offset, in every region, never a pad",
       "functions reach their object as `*(int*)((char*)p + 0x78)`; a rewrite from a hand count, into a pad, or "
       "with one region's layout in a file another region builds names a field the code never touched")
def _offsetmembers():
    O = load("offsetmembers")
    f = _member_field
    common = [f("vals", "int", 0xc, 0x10, elem=[4]), f("sub", "Sub", 0x1c, 8), f("raw", "void", 0x24, 4, ptr=1),
              f("name", "char", 0x28, 0x10, elem=[1])]
    usa = _member_layout([f("pad0", "unsigned char", 0, 4, elem=[1]), f("count", "unsigned int", 4, 4),
                          f("buffer", "unsigned short", 8, 4, ptr=1)] + common)
    jpn = _member_layout([f("pad0", "unsigned char", 0, 4, elem=[1]), f("other", "int", 4, 4),
                          f("count", "unsigned int", 8, 4)] + common)
    for (off, mode, want), expect in (((4, "load", "int"), "{v}->count"), ((0x14, "load", "int"), "{v}->vals[2]"),
                                      ((0x1e, "load", "short"), "{v}->sub.y"), ((0xc, "address", "int"), "{v}->vals"),
                                      ((0x1c, "address", "short"), "&{v}->sub.x"), ((0x1c, "address", "Sub"), "&{v}->sub"),
                                      ((0x1c, "arrow", "Sub"), "{v}->sub."),
                                      ((0x2a, "address", "signed char"), "&{v}->name[2]"),
                                      ((0x24, "load", "unsigned short*"), "((unsigned short*){v}->raw)")):
        got = O.resolve(usa, "Obj", off, mode, want)[0]
        if got != expect:
            return "resolve(%#x, %s, %s) gave %r, want %r" % (off, mode, want, got, expect)
    for (off, mode, want), why in (((0, "load", "int"), "pad"), ((4, "load", "short"), "type")):
        if O.resolve(usa, "Obj", off, mode, want) != (None, why):
            return "resolve(%#x, %s, %s) named a member, want none (%s)" % (off, mode, want, why)
    if O.resolve(usa, "Obj", 4, "load", "int", exact=True) != (None, "signedness"):
        return "an exact rewrite read an unsigned member as int"
    pick = "#if defined(jpn)\n#define AT(j, u) j\n#else\n#define AT(j, u) u\n#endif\n"
    text = (pick + "void f(Obj* p, int i) {\n    *(int*)((char*)p + 4) = i;\n    g((short*)((char*)p + 0x1c));\n"
            "    h(*(int*)((char*)p + 0));\n    ((int*)((char*)p + 0xc))[i] = 1;\n    ((Sub*)((char*)p + 0x1c))->z = 2;\n"
            "    unsigned char* b = (unsigned char*)p;\n    b[0x28] = 3;\n#if defined(jpn)\n"
            "    *(int*)((char*)p + 8) = 0;\n#else\n    *(int*)((char*)p + 4) = 0;\n#endif\n"
            "    *(int*)((char*)p + AT(8, 4)) = 5;\n}\n")
    want = (pick + "void f(Obj* p, int i) {\n    *(int*)((char*)p + 4) = i;\n    g(&p->sub.x);\n"
            "    h(*(int*)((char*)p + 0));\n    p->vals[i] = 1;\n    p->sub.z = 2;\n"
            "    p->name[0] = 3;\n#if defined(jpn)\n    p->count = 0;\n#else\n    p->count = 0;\n#endif\n"
            "    p->count = 5;\n}\n")
    code, lo, hi = O.flat(text), text.index("{"), text.rindex("}")
    live, lays = O.line_regions(text, O.REGIONS), {"usa": usa, "jpn": jpn, "eur": usa}
    edits, misses = O.rewrite(text, code, lo, hi, "p", False, "Obj", lays, live, list(O.REGIONS))
    more, missed = O.alias_edits(text, code, lo, hi, "p", "Obj", lays, live, list(O.REGIONS))
    got = O.apply_edits(text, edits + more)
    if got != want:
        return "rewrite gave %r" % got
    if sorted(m["why"] for m in misses + missed) != ["pad", "regions differ"]:
        return "the accesses left were reported as %r" % [m["why"] for m in misses + missed]
    prelude = ("#if defined(jpn)\nstruct Probe { int a; short b[3]; };\n#else\n"
               "struct Probe { short b[3]; int a; unsigned char pad[4]; };\n#endif\n")
    for region, size, where in (("usa", 16, {"b": (0, 6, [2]), "a": (8, 4, []), "pad": (12, 4, [1])}),
                                ("jpn", 12, {"a": (0, 4, []), "b": (4, 6, [2])})):
        lay = O.layouts(prelude, region, "Probe")
        probe = lay and lay["types"].get("Probe")
        if not probe or probe["size"] != size or \
                {x["name"]: (x["off"], x["size"], x["elem"]) for x in probe["fields"]} != where:
            return "the %s layout read from the compiler was %r" % (region, probe)
    return None


@check("memberize turns a free function taking its object into a member and every call into a member call",
       "self-taking functions were written as free functions over `char* self`; a conversion that guessed the "
       "class, kept a byte offset, or left a caller or a symbols.txt on the old name lands code no developer wrote")
def _memberize():
    Z = load("memberize")
    O = Z.om
    f = _member_field
    header = "#pragma once\nstruct Foo {\n    unsigned char pad0[4];\n    int count;\n};\n"
    defs = ('#include <globaldefs.h>\n\n// USA: func_02000010  (semantic: SetCount)\n'
            'extern "C" ARM void func_02000010(char* self, int v) {\n    *(int*)(self + 4) = v;\n}\n\n'
            '// USA: func_02000020\nextern "C" ARM void func_02000020(char* self) {\n    *(int*)(self + 0) = 1;\n}\n')
    calls = ('struct Foo;\nextern "C" void func_02000010(void* obj, int v);\nextern "C" void func_02000020(void* obj);\n'
             '\nvoid g(Foo* f) {\n    func_02000010(f, 3);\n    func_02000020(f);\n}\n')
    mixed = ('struct Bar;\nextern "C" void func_02000030(char* self) {\n    *(int*)(self + 4) = 0;\n}\n'
             'void h(Foo* f, Bar* r) {\n    func_02000030(f);\n    func_02000030(r);\n}\n'
             'extern "C" void func_02000040(void* p) {\n}\nvoid k(Foo* f) {\n    func_02000040(f);\n}\n'
             'extern "C" void func_02000050(char* self) {\n    func_02000040(self);\n}\n'
             '#define func_02000060 func_02000070\nextern "C" void func_02000060(char* self) {\n}\n')
    names = ["func_020000%d0" % n for n in (1, 2, 3, 4, 5, 6)]
    symbols = "".join("%s kind:function(arm,size=0x10) addr:0x%s\n" % (name, name[5:]) for name in names)
    current = {"include/Foo.h": header, "src/a.cpp": defs, "src/b.cpp": calls, "src/c.cpp": mixed,
               "config/usa/arm9/symbols.txt": symbols, "config/eur/arm9/symbols.txt": symbols}
    lay = _member_layout([f("pad0", "unsigned char", 0, 4, elem=[1]), f("count", "int", 4, 4)], 8)
    lay["types"]["Foo"] = lay["types"].pop("Obj")
    old = O.class_layouts
    O.class_layouts = lambda original, cls, regions: {r: lay for r in regions} if cls == "Foo" else None
    try:
        model = Z.Model(current, {"Foo", "Bar"}, 1)
        model.prove()
        if model.proven.get(("src/a.cpp", "func_02000010")) != ("Foo", "caller"):
            return "the class every caller passes was not proven: %r" % model.proven
        if ("src/c.cpp", "func_02000030") in model.proven:
            return "callers passing a Foo* and a Bar* still proved a class"
        if ("src/c.cpp", "func_02000050") in model.proven:
            return "a helper proven only by its callers proved every other caller's object too"
        if not model.other.get(("src/c.cpp", "func_02000060")):
            return "a function a #define renames was treated as called by its name"
        S0 = {k: Z.static_checks(model, k, set(), False)[0] for k in model.defs if k[0] == "src/a.cpp"}
        S, new, reasons = Z.settle_static(model, S0)
    finally:
        O.class_layouts = old
    if sorted(S) != [("src/a.cpp", "func_02000010")] or S[("src/a.cpp", "func_02000010")]["name"] != "SetCount_02000010":
        return "converted %r" % S
    if Z.described(reasons.get(("src/a.cpp", "func_02000020"), [])) != "needs members: 0x0 int pad":
        return "an offset into a pad was not reported as a missing member: %r" % reasons
    if "ARM void Foo::SetCount_02000010(int v) {\n    count = v;\n}" not in new.get("src/a.cpp", "") or \
            '#include "Foo.h"' not in new["src/a.cpp"]:
        return "definition became %r" % new.get("src/a.cpp")
    if new.get("src/b.cpp") != ('#include "Foo.h"\nextern "C" void func_02000020(void* obj);\n\nvoid g(Foo* f) {\n'
                                "    f->SetCount_02000010(3);\n    func_02000020(f);\n}\n"):
        return "caller became %r" % new.get("src/b.cpp")
    if new.get("include/Foo.h") != header.replace("};", "    void SetCount_02000010(int v);\n};"):
        return "header became %r" % new.get("include/Foo.h")
    renamed = Z.rename_symbols(model, {}, {"func_02000010": "_ZN3Foo17SetCount_02000010Ei"})
    if sorted(renamed) != ["config/eur/arm9/symbols.txt", "config/usa/arm9/symbols.txt"] or \
            "_ZN3Foo17SetCount_02000010Ei kind:function" not in renamed["config/eur/arm9/symbols.txt"]:
        return "symbols.txt renamed as %r" % renamed
    return None


@check("mechclean verify checks every unit that reaches a changed header through a relative include",
       "include/World/Zone3D.h includes \"ZoneFeatures.h\"; renaming ZoneFeatures::Reset passed verify "
       "and src/World/Zone3D.cpp then failed to compile in landclean")
def _mechclean_relative_include():
    M = load("mechclean")
    original = {"include/World/ZoneFeatures.h": "struct ZoneFeatures { void Reset(); };\n",
                "include/World/Zone3D.h": '#include "ZoneFeatures.h"\n',
                "src/World/Zone3D.cpp": '#include "World/Zone3D.h"\n',
                "src/Other.cpp": "int x;\n"}
    new = {"include/World/ZoneFeatures.h": "struct ZoneFeatures { void Reset_0201e248(); };\n"}
    _headers, _closure, tus = M.affected(original, new)
    if tus != ["src/World/Zone3D.cpp"]:
        return "units checked: %s" % tus
    return None


@check("mechclean rewrites each one-form construct to its natural spelling and nothing else",
       "workers spent a session each on `x > -1`, a no-op address cast and a getter local that a "
       "rewrite plus one gate settles")
def _mechclean_rewrites():
    M = load("mechclean")
    cases = [
        (["COMPARE-MINUS-ONE"], "    if (obj->count > -1) f();", "    if (obj->count > -1) f();"),
        (["NOOP-ADDR-CAST"], "    v = *(unsigned char*)&e->field24;", "    v = e->field24;"),
        (["TERNARY-SELF"], "    s = s->bit0 ? s : NULL;", "    if (!(s->bit0)) s = NULL;"),
        (["SELF-ASSIGN"], "    a = a;\n    b = 1;", "    b = 1;"),
        (["INLINE-LOCAL-RETURN"], "static inline int Get(S* s) { int v = s->hp; return v; }",
         "static inline int Get(S* s) { return s->hp; }"),
        (["NOOP-ADDR-CAST"], "    x = y > -1;", "    x = y > -1;"),
        (["INLINE-LOCAL-RETURN"], "inline T& GetT() { static T s; return s; }",
         "inline T& GetT() { static T s; return s; }"),
    ]
    for kinds, before, want in cases:
        got = M.rewrite(before, kinds)
        if got != want:
            return "%s: %r became %r, want %r" % (kinds, before, got, want)
    asserted = [
        ("static inline short CurrHP(GameObject* c) { short v = c->stats->hp; return v; }",
         "static inline short CurrHP(GameObject* c) { SDK_NULL_ASSERT(c); return c->stats->hp; }"),
        ("    short GetId() const { short id = s4; return id; }",
         "    short GetId() const { SDK_NULL_ASSERT(this); return s4; }"),
        ("static inline int Sum(int a, int b) { int v = a + b; return v; }",
         "static inline int Sum(int a, int b) { int v = a + b; return v; }"),
        ("struct A;\nstruct B;\nstatic inline B* AsB(A* a) { B* b = (B*)a; return b; }\n"
         "static inline int Hp(S* s) { int v = s->hp; return v; }",
         "struct A;\nstruct B;\nstatic inline B* AsB(A* a) { B* b = (B*)a; return b; }\n"
         "static inline int Hp(S* s) { SDK_NULL_ASSERT(s); return s->hp; }"),
    ]
    for before, want in asserted:
        got = M.rewrite(before, ["INLINE-LOCAL-RETURN"], True)
        if got != want:
            return "asserted: %r became %r, want %r" % (before, got, want)
    return None


@check("mechclean keeps an inline's statement boundary with the assert when the plain return misses",
       "65 INLINE-LOCAL-RETURN findings matched only with the local: any statement before the return "
       "makes mwcc expand the inline at the start of the calling statement, and the plain return "
       "missed on all 35 files tried (021e4c04 SCHED 37) while ((void)0) matched 34")
def _mechclean_assert_fallback():
    import shutil
    M = load("mechclean")
    if (["INLINE-LOCAL-RETURN"], True) not in list(M.candidates(["INLINE-LOCAL-RETURN", "NOOP-ADDR-CAST"])):
        return "a cast rewrite that breaks the match also throws away the getter fix (0219e384, 02157d40)"
    seen = []
    M.gate = lambda mod, addr, path: seen.append(open(path, encoding="utf-8").read()) or "SDK_NULL_ASSERT" in seen[-1]
    M.finished = lambda addr: False
    sp = tempfile.mkdtemp()
    try:
        M.SP, M.WORK, M.CLAIMS, M.LOG = sp, f"{sp}/work", f"{sp}/claims", f"{sp}/clean.log"
        os.makedirs(M.CLAIMS)
        held = f"{sp}/hold_plausible/ov024/func_ov024_021e4c04.cpp"
        os.makedirs(os.path.dirname(held))
        with open(held, "w", encoding="utf-8") as fh:
            fh.write("#include <globaldefs.h>\nstruct S { short hp; };\n"
                     "static inline short GetHP(S* c) { short hp = c->hp; return hp; }\n"
                     'extern "C" ARM int f(S* c) { return GetHP(c) - 1; }\n')
        result = M.job(["024", "021e4c04", held, "3", "INLINE-LOCAL-RETURN", "staging"])
        staged = f"{sp}/staging/ov024/func_ov024_021e4c04.cpp"
        if len(seen) != 2 or "SDK_NULL_ASSERT" in seen[0]:
            return "mechclean did not try the plain return first, then the assert (%d gates)" % len(seen)
        if not os.path.exists(staged) or os.path.exists(held):
            return "the cleaned staging row did not move to staging/ (%s)" % result
        if "{ SDK_NULL_ASSERT(c); return c->hp; }" not in open(staged, encoding="utf-8").read():
            return "the staged file does not carry the assert form"
        return None
    finally:
        shutil.rmtree(sp, ignore_errors=True)


@check("landpr leaves the integration tree on the published tip when it refuses",
       "a prready refusal left Merge #106 checked out; integrate_fast built on it and published the "
       "codegen pragma landpr had refused")
def _landpr_refuse_resets():
    import contextlib
    import io
    import subprocess
    lp = load("landpr")
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="landpr_refuse_", dir=f"{SP}/handwork",
                                     ignore_cleanup_errors=True) as root:
        def git(*args):
            return subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                                  capture_output=True, text=True).stdout.strip()

        git("init", "-q", "-b", "main")
        git("commit", "-q", "--allow-empty", "-m", "base")
        tip = git("rev-parse", "HEAD")
        git("commit", "-q", "--allow-empty", "-m", "Merge #5")
        getattr(lp, "UNDO", []).append((root, tip))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                lp.refuse("prready")
        except SystemExit:
            pass
        if git("rev-parse", "HEAD") != tip:
            return "refuse() left the merged commits checked out for the next integration to publish"
    return None


STAMP = f"{SP}/wlog/functional_stamp.txt"


@check("gate and differ use external state and fail closed on snapshot errors",
       "kit-relative snapshots were invisible to state pools and failed copies still reported MATCH")
def _external_gate_state():
    gate = open(f"{KIT}/wgate.py", encoding="utf-8").read()
    diff = open(f"{KIT}/wdiff.py", encoding="utf-8").read()
    if 'SCR=f"{_kp.SP}/handwork/compile"' not in gate or 'SCR = f"{_kp.SP}/handwork/compile"' not in diff:
        return "compiler scratch is not in external state"
    if 'f"{_kp.SP}/gated/"' not in gate or 'PRESERVATION-FAILED' not in gate:
        return "gate does not preserve to external state with a visible failure"
    if 'os.replace(_tmp,' not in gate or 'ELFFile(io.BytesIO(_fh.read()))' not in diff:
        return "snapshot publication is not atomic or differ retains an open object handle"

@check("repool leaves a member already spelled as the renamed nested symbol",
       "021eefd0 declared GetGrottoStruct inside struct GameState; repool pasted "
       "_ZN9GameState15GetGrottoStructEv over the member and the call, and the source stopped compiling")
def _repool_member():
    R = load("pad/repool")
    spell = {"GetGrottoStruct": "_ZN9GameState15GetGrottoStructEv", "Foo": "_Z3Foov"}
    member = ("struct G;\nstruct GameState {\n    static GameState* GetInstance();\n"
              "    G* GetGrottoStruct();\n};\n\nvoid f() { GameState::GetInstance()->GetGrottoStruct(); }\n")
    new, _what = R.rewrite(member, True, spell, {}, set(), {}, {})
    if new != member:
        return "rewrote a member declaration and its call"
    cxx = "int Foo();\n\nvoid f() { Foo(); }\n"
    new, _what = R.rewrite(cxx, True, spell, {}, set(), {}, {})
    if new != cxx:
        return "rewrote a C++ call whose new symbol is its own mangling, which then clashes with the header"
    free_member = "struct GameState;\nvoid* GetGrottoStruct(GameState*);\n\nvoid f(GameState* g) { GetGrottoStruct(g); }\n"
    new, _what = R.rewrite(free_member, True, spell, {}, set(), {}, {})
    if new is not None:
        return "rewrote a free call into a member's mangled name, which does not compile"


@check("repool renames a C++ callee as a plain identifier and never writes its mangled name",
       "the address renames sent 812 parked sources through repool, which declared each callee as "
       "extern \"C\" _Z19AppendXTag_02041a28Pci, the pattern plausible.py rejects as EXTERN-C-MANGLED")
def _repool_cxx_identifier():
    R = load("pad/repool")
    free = 'extern "C" int Foo();\n\nvoid f() { Foo(); }\n'
    new, _what = R.rewrite(free, True, {"Foo": "_Z3Foov"}, {}, set(), {}, {})
    if new != "int Foo();\n\nvoid f() { Foo(); }\n":
        return "a C declaration of a C++ function kept extern \"C\" or took its mangled name: %r" % new
    spell = {"AppendXTag": "_Z19AppendXTag_02041a28Pci", "_Z10AppendXTagPci": "_Z19AppendXTag_02041a28Pci"}
    renamed = "void AppendXTag(char*, int);\n\nvoid f(char* p) { AppendXTag(p, 1); }\n"
    new, _what = R.rewrite(renamed, True, spell, {}, set(), {}, {})
    if new != "void AppendXTag_02041a28(char*, int);\n\nvoid f(char* p) { AppendXTag_02041a28(p, 1); }\n":
        return "an address rename did not stay a plain C++ identifier: %r" % new
    retypes = {"_Z12SetByte0x1c8Phh": ("_Z12SetByte0x1c8Phi", None, "SetByte0x1c8",
                                       ["unsigned char*", "unsigned char"], ["unsigned char*", "int"])}
    widened = "void SetByte0x1c8(unsigned char* p, unsigned char v);\n\nvoid f(unsigned char* p) { SetByte0x1c8(p, 1); }\n"
    new, _what = R.rewrite(widened, True, {"SetByte0x1c8": "_Z12SetByte0x1c8Phi"}, {}, set(), {}, {}, retypes)
    if new != widened.replace("unsigned char v", "int v"):
        return "a remangled callee's declaration was not retyped: %r" % new


@check("wgate selects ISA and size by physical address, not raw-name suffix",
       "JP021d4af8 was584B but raw name func_ov017_021d4af8 belonged at021d4f48/164B; name-first selected the wrong slot")
def _gate_slot_address():
    import textwrap
    source = open(f"{KIT}/wgate.py", encoding="utf-8").read()
    start = source.rindex("\n", 0, source.index("# accept THUMB as well as ARM.")) + 1
    selection = textwrap.dedent(source[start:source.index("if SEC is None:", start)])
    def missing(message, *args, **kwargs):
        raise ValueError(message)
    cases = [
        ("renamed ARM with colliding raw name", "021d4af8", "func_ov017_",
         "func_ov017_021d4af8"
         " kind:function(thumb,size=0xa4) addr:0x021d4f48\n"
         "func_ov017_021d46a4"
         " kind:function(arm,size=0x248) addr:0x021d4af8\n", ("arm", 584)),
        ("renamed Thumb", "02001000", "func_",
         "SemanticName kind:function(thumb,size=0x20) addr:0x02001000\n", ("thumb", 32)),
        ("ordinary raw ARM", "02001000", "func_",
         "func_02001000"
         " kind:function(arm,size=0x30) addr:0x02001000\n", ("arm", 48)),
        ("ordinary raw Thumb", "02001000", "func_",
         "func_02001000"
         " kind:function(thumb,size=0x10) addr:0x02001000\n", ("thumb", 16)),
        ("missing", "02001000", "func_", "", None),
        ("missing despite same raw name elsewhere", "02001000", "func_",
         "func_02001000"
         " kind:function(arm,size=0x30) addr:0x02002000\n", None),
        ("data at requested address is not a function", "02001000", "func_",
         "data_02001000 kind:data size:0x30 addr:0x02001000\n", None),
    ]
    for label, address, prefix, symbols, expected in cases:
        namespace = dict(re=re, ADDR=address, PFX=prefix, symtxt=symbols, fail=missing)
        try:
            exec(selection, namespace)
            actual = (namespace["ISA"], namespace["slot"])
        except ValueError as error:
            if not str(error).startswith("NO-SLOT:"):
                return label + ": unexpected error " + str(error)
            actual = None
        if actual != expected:
            return "%s: got %r, expected %r" % (label, actual, expected)


def _region_functions(script, root, region):
    import ast
    import functools
    import glob
    from types import SimpleNamespace
    cfg = SimpleNamespace(
        REGION=region,
        config_dir=lambda mod: "config/%s/arm9%s" % (
            region, "" if mod == "main" else "/overlays/ov" + mod),
        pristine=lambda mod: "extract/%s/%s" % (
            region, "arm9/arm9.bin" if mod == "main" else "arm9_overlays/ov" + mod + ".bin"))
    source = open(f"{KIT}/{script}.py", encoding="utf-8").read()
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) or
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
              t.id == "REGION_TAG" for t in n.targets))]
    ns = dict(re=re, os=os, sys=sys, glob=glob, functools=functools,
              buildcfg=cfg, REPO=root, SP=root, KIT=KIT, _SYMS={},
              SYMS={}, BOUNDS={}, __file__=f"{KIT}/{script}.py")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), script, "exec"), ns)
    return ns, source


def _region_files(root):
    from pathlib import Path
    for region, name, isa in (("usa", "UsaName", "arm"), ("jpn", "JpnName", "thumb")):
        for mod, addr in (("main", "02000000"), ("017", "02100000")):
            cfg = Path(root, "config", region, "arm9")
            if mod != "main":
                cfg /= "overlays/ov" + mod
            cfg.mkdir(parents=True)
            (cfg / "symbols.txt").write_text(
                "%s kind:function(%s,size=0x4) addr:0x%s\n" % (name, isa, addr))
            (cfg / "delinks.txt").write_text(
                ".init start:0x%s end:0x%08x kind:code\n" % (addr, int(addr, 16) + 4))
            binary = Path(root, "extract", region,
                          "arm9/arm9.bin" if mod == "main" else "arm9_overlays/ov017.bin")
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(region.encode() + b"\0")


@check("scaffold uses active-region config, pristine bytes and source tags",
       "JPN scaffolds read USA symbol paths or emitted USA markers and could not enter a JPN wave")
def _scaffold_region_fixture():
    with tempfile.TemporaryDirectory() as root:
        _region_files(root)
        for region in ("usa", "jpn"):
            ns, _source = _region_functions("scaffold", root, region)
            for mod, addr in (("main", "02000000"), ("017", "02100000")):
                blob, base = ns["module_image"](mod)
                if blob != region.encode() + b"\0" or base != int(addr, 16):
                    return "%s %s selected the wrong pristine image" % (region, mod)
                ns["rom_calls"] = lambda *args: []
                out, count = ns["scaffold"](mod, addr)
                name = "JpnName" if region == "jpn" else "UsaName"
                prefix = "func_" if mod == "main" else "func_ov017_"
                if ("// %s: %s%s" % (region.upper(), prefix, addr) not in out
                        or name + "(" not in out or count != 0):
                    return "%s %s emitted the wrong symbol or region tag: %s" % (region, mod, out)


@check("autorepair selects active-region symbols and repairs its init/KEEP-NAME tags",
       "JPN files were repaired against USA symbols or their JPN markers bypassed init/KEEP-NAME repairs")
def _autorepair_region_fixture():
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as root:
        _region_files(root)
        for region in ("usa", "jpn"):
            ns, _source = _region_functions("autorepair", root, region)
            ns["_emits_symbol"] = lambda *args: (True, "")
            ns["_text_emits"] = lambda *args: True
            for mod, addr in (("main", "02000000"), ("017", "02100000")):
                expected = "JpnName" if region == "jpn" else "UsaName"
                if ns["_symbols"](mod).get(addr) != expected:
                    return "%s %s selected the wrong symbols" % (region, mod)
                path = Path(root, "candidate.cpp")
                path.write_text('#include <globaldefs.h>\n// %s: func_%s\nARM int %s() { return 0; }\n'
                                % (region.upper(), addr, expected))
                with patch("subprocess.run", return_value=SimpleNamespace(stdout="MATCH\n", stderr="")):
                    applied = ns["repair"](str(path), mod, addr)
                out = path.read_text()
                if ("added initcode pragma" not in applied or "marked KEEP-NAME" not in applied
                        or '__declspec(initcode)' not in out
                        or "// " + region.upper() + ":" not in out):
                    return "%s %s missed its tag repairs: %r" % (region, mod, applied)


@check("integrate discovers active-region tagged candidates using active config and ROM paths",
       "JPN candidates were invisible or integration selected the USA module config/pristine binary")
def _integrate_region_fixture():
    import glob
    with tempfile.TemporaryDirectory() as root:
        _region_files(root)
        os.mkdir(os.path.join(root, "src"))
        for region in ("usa", "jpn"):
            for mod, addr in (("main", "02000000"), ("017", "02100000")):
                ns, source = _region_functions("integrate", root, region)
                ns.update(MAIN=mod == "main", MOD=mod, SRCDIR=os.path.join(root, "src"),
                          glob=glob, tracked=lambda path: True, DELINKED=set(), delinks="")
                start = source.index("if MAIN:", source.index("# ---- the ONLY module-dependent"))
                end = source.index("# Per-file compiler override", start)
                exec(source[start:end], ns)
                expected_cfg = ns["buildcfg"].config_dir(mod)
                if ns["CFG"] != expected_cfg or ns["PRISTINE"] != region.encode() + b"\0":
                    return "%s %s selected wrong config/pristine" % (region, mod)
                for other in ("usa", "jpn"):
                    with open(os.path.join(root, "src", other + ".cpp"), "w") as fh:
                        fh.write("// %s: %s%s\nARM int Fixture() { return 0; }\n" %
                                 (other.upper(), ns["PREFIX"], addr))
                ns["symtxt"] = open(os.path.join(root, expected_cfg, "symbols.txt")).read()
                start = source.index("pending = []")
                exec(source[start:source.index("TU = {}", start)], ns)
                want = [(os.path.join(root, "src", region + ".cpp").replace("\\", "/"), addr)]
                if ns["pending"] != want:
                    return "%s %s discovered %r, expected %r" % (region, mod, ns["pending"], want)


@check("integration shell configure calls preserve JPN and compiler/runner paths with spaces",
       "finish_wave/integrate_fast configured USA or dropped the existing Linux toolchain environment")
def _integration_shell_environment():
    import subprocess
    for script in ("finish_wave.sh", "integrate_fast.sh"):
        source = open(f"{KIT}/{script}", encoding="utf-8").read()
        lines = source.splitlines()
        idx = next(i for i, line in enumerate(lines) if line.startswith("python tools/configure.py "))
        start = idx
        while start and (lines[start - 1].startswith("_compiler_args=") or
                         lines[start - 1].startswith('[ -n "${DQIX_')):
            start -= 1
        snippet = "\n".join(lines[start:idx + 1])
        with tempfile.TemporaryDirectory() as root:
            output = os.path.join(root, "arguments")
            harness = ('python() { printf "%s\\n" "$@" > "$CAPTURE"; }; '
                       'REGION=jpn; LOG=/dev/null;\n' + snippet)
            bash, env = _kp.bash(dict(os.environ, CAPTURE=output, DQIX_WINE="/tools/wine runner",
                                      DQIX_PREINSTALLED_COMPILER="/tools/compiler root"))
            result = subprocess.run([bash, "-c", harness], env=env, capture_output=True, text=True)
            got = open(output).read().splitlines() if os.path.exists(output) else []
            want = ["tools/configure.py", "jpn", "--no-extract", "--compiler",
                    "/tools/compiler root", "-w", "/tools/wine runner"]
            if result.returncode or got != want:
                return "%s forwarded %r, expected %r: %s" % (script, got, want, result.stderr)


def _fixture_assignments(source, ns, names):
    import ast
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.Assign) and
             any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "fixture", "exec"), ns)


@check("ov_recover gathers and retags the selected region",
       "JPN waves gathered no sources because recovery still read USA tags and config")
def _recover_region_fixture():
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as root:
        _region_files(root)
        for region in ("usa", "jpn"):
            for mod, addr in (("main", "02000000"), ("017", "02100000")):
                ns, source = _region_functions("ov_recover", root, region)
                ns.update(REGION=region, TAG=region.upper(), MOD=mod, MAIN=mod == "main",
                          OV=mod, srcdir=SimpleNamespace(for_module=lambda mod: root), _BOUND=None)
                start = source.index("if MAIN:")
                exec(source[start:source.index("def tag_addr", start)], ns)
                if ns["CFG"] != ns["buildcfg"].config_dir(mod):
                    return "wrong recovery config"
                name = "UsaName" if region == "usa" else "JpnName"
                text = '// %s: %s\nextern "C" int %s() { return 0; }\n' % (region.upper(), name, name)
                result = ns["retag"](text, "fixture.cpp")
                if ns["tag_addr"](result) != addr:
                    return "%s %s was not gathered after retag" % (region, mod)
                other = "JPN" if region == "usa" else "USA"
                if ns["tag_addr"](result.replace(region.upper() + ":", other + ":")):
                    return "accepted a foreign region tag"
                gate = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "gate")
                end = next(i for i, n in enumerate(gate.body) if isinstance(n, ast.Assign) and
                           any(isinstance(t, ast.Name) and t.id == "cf" for t in n.targets))
                calls = []
                ns.update(sweep_foreign=lambda: None, sh=lambda *args: calls.append(args))
                for item in (region, "jpn" if region == "usa" else "usa"):
                    binary = Path(root, "build", item, "arm9.o")
                    binary.parent.mkdir(parents=True, exist_ok=True)
                    binary.write_bytes(item.encode())
                cwd = os.getcwd()
                try:
                    os.chdir(root)
                    with patch.dict(os.environ, {"DQIX_PREINSTALLED_COMPILER": "/compiler root", "DQIX_WINE": "/wine runner"}):
                        exec(compile(ast.Module(body=gate.body[:end + 1], type_ignores=[]), "gate", "exec"), ns)
                finally:
                    os.chdir(cwd)
                want = ("python", "tools/configure.py", region, "--no-extract", "--compiler", "/compiler root", "-w", "/wine runner")
                if calls != [want] or Path(root, "build", region, "arm9.o").exists():
                    return "recovery gate selected wrong region/runner"
                other = "jpn" if region == "usa" else "usa"
                if not Path(root, "build", other, "arm9.o").exists():
                    return "recovery removed another region's output"


@check("classify reads selected-region symbols and pristine bytes",
       "JPN integration classified functions against USA config and pristine bytes")
def _classify_region_fixture():
    with tempfile.TemporaryDirectory() as root:
        _region_files(root)
        for region in ("usa", "jpn"):
            ns, source = _region_functions("classify", root, region)
            ns["_CTX"] = {}
            ns["buildcfg"].lcf_symbols = lambda: {}
            for mod in ("main", "017"):
                blob, base, symbols, sizes, ranges = ns["_ctx"](mod)
                expected = "UsaName" if region == "usa" else "JpnName"
                if blob != region.encode() + b"\0" or set(symbols) != {expected}:
                    return "%s %s read another region" % (region, mod)


@check("delinked searches only the selected region",
       "JPN reservations were tested against USA delink ranges")
def _delinked_region_fixture():
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as root:
        _region_files(root)
        for region in ("usa", "jpn"):
            ns, source = _region_functions("delinked", root, region)
            for mod in (None, "main", "017"):
                with patch.dict(sys.modules, {"buildcfg": ns["buildcfg"]}):
                    paths = ns["files"](mod)
                if len(paths) != (2 if mod is None else 1) or any(
                        "/config/" + region + "/" not in p.replace("\\", "/") for p in paths):
                    return "%s %s selected %r" % (region, mod, paths)


@check("culprits identifies selected-region source tags",
       "a failed JPN build could not name its JPN-tagged candidates")
def _culprits_region_fixture():
    for region in ("usa", "jpn"):
        ns, source = _region_functions("culprits", "unused", region)
        _fixture_assignments(source, ns, {"TAG"})
        for prefix, mod in (("func_", "main"), ("func_ov017_", "017")):
            text = "// %s: %s02100000\n" % (region.upper(), prefix)
            if ns["tag_of"](text) != (mod, "02100000"):
                return "selected tag not recognized"
            other = "JPN" if region == "usa" else "USA"
            if ns["tag_of"](text.replace(region.upper(), other)) is not None:
                return "foreign tag accepted"


@check("countfix reads matching region report and modifies only that config",
       "a JPN gate caused countfix to repair config/usa using build/usa/report.json")
def _countfix_region_fixture():
    from pathlib import Path
    import shutil
    with tempfile.TemporaryDirectory() as root:
        _region_files(root)
        for region in ("usa", "jpn"):
            path = Path(root, "build", region, "report.json")
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"units": [{"name": region, "metadata": {"complete": True},
                                                  "functions": [{"fuzzy_match_percent": 50}]}]}))
        for region in ("usa", "jpn"):
            ns, source = _region_functions("countfix", root, region)
            ns.update(json=json, shutil=shutil)
            _fixture_assignments(source, ns, {"CFG", "BACKUP"})
            if ns["report_units"]() != [region]:
                return "read the wrong report"
            name = "UsaName" if region == "usa" else "JpnName"
            locations = ns["function_locations"]()
            if set(locations) != {name}:
                return "read the wrong symbol config"
            other = "jpn" if region == "usa" else "usa"
            other_path = Path(root, "config", other, "arm9", "symbols.txt")
            before = other_path.read_bytes()
            symbol = Path(ns["CFG"], "symbols.txt")
            symbol.write_text("Fixture kind:function(thumb,size=0x6) addr:0x02000000\n")
            changed = ns["apply"]([], [(str(symbol), "Fixture", 6, 4)])
            if changed != [str(symbol)] or "size=0x4" not in symbol.read_text() or other_path.read_bytes() != before:
                return "repair did not stay within selected config"
            ns["restore"]()
            symbol.write_text("%s kind:function(thumb,size=0x4) addr:0x02000000\n" % name)


@check("regionsync forwards the configured compiler runner",
       "region synchronization dropped DQIX_WINE when configuring its next build")
def _regionsync_runner_fixture():
    from unittest.mock import patch
    ns, source = _region_functions("regionsync", "unused", "jpn")
    ns["run"] = lambda *args: args
    for wine in ("", "/tools/wine runner"):
        with patch.dict(os.environ, {"DQIX_PREINSTALLED_COMPILER": "/tools/compiler root", "DQIX_WINE": wine}):
            result = ns["configure"]("jpn")
        want = (sys.executable, "tools/configure.py", "jpn", "--no-extract", "--compiler", "/tools/compiler root")
        if wine:
            want += ("-w", wine)
        if result != want:
            return "configure forwarded %r, expected %r" % (result, want)


@check("a cold integration tree configures and fetches its own compiler before sync returns",
       "a new integration worktree had extract links but no build.ninja or compiler, so classify raised "
       "FileNotFoundError before the wave configured; a junction to the checkout's compiler would let "
       "the tree's first ninja rewrite the checkout's mwccarm.exe (kit PR #102)")
def _integ_bootstrap():
    import subprocess
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        repo, tree, pre = Path(d, "repo"), Path(d, "tree"), Path(d, "pre")
        (repo / "tools/mwccarm/2.0/fx").mkdir(parents=True)
        (repo / "extract").mkdir()
        (repo / "tools/fetch.py").write_text(
            "import sys\nfrom pathlib import Path\nopen('events', 'a').write('fetch\\n')\n"
            "p = Path(sys.argv[1]); p.parent.mkdir(parents=True, exist_ok=True); p.write_text('fetched')\n")
        (repo / "tools/configure.py").write_text(
            "import argparse, os, sys\nfrom pathlib import Path\n"
            "p = argparse.ArgumentParser(); p.add_argument('region'); p.add_argument('--no-extract', "
            "action='store_true'); p.add_argument('--compiler'); p.add_argument('-w')\n"
            "a = p.parse_args()\nMWCC_VERSION = '2.0/fx'\nDECOMP_ME_COMPILER = 'fx'\n"
            "CC_FLAGS = CC_INCLUDES = AS_FLAGS = WINE = ''\n"
            "mwcc_root = Path(a.compiler) if a.compiler else Path('tools/mwccarm')\n"
            "if __name__ == '__main__':\n"
            "    if os.environ.get('FX_CONFIG_FAIL'): sys.exit(17)\n"
            "    open('events', 'a').write('configure %s\\n' % (a.compiler or '-'))\n"
            "    t = (mwcc_root / MWCC_VERSION / 'mwccarm.exe').as_posix()\n"
            "    Path('build.ninja').write_text('rule fetch\\n  command = \"%s\" tools/fetch.py $out\\n"
            "build %s: fetch\\n' % (sys.executable.replace(os.sep, '/'), t))\n")
        main_cc = repo / "tools/mwccarm/2.0/fx/mwccarm.exe"
        main_cc.write_text("checkout compiler")
        (repo / ".gitignore").write_text("tools/mwccarm/\n")
        for args in (["init", "-q", "-b", "decomp-matching"], ["add", "."],
                     ["-c", "user.name=f", "-c", "user.email=f@f", "commit", "-qm", "f"]):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        env = {k: v for k, v in os.environ.items() if k not in ("DQIX_PREINSTALLED_COMPILER", "DQIX_WINE")}
        env.update(DQIX_MAIN_REPO=str(repo), DQIX_INTEG=str(tree), DQIX_PUBLISH="local", DQIX_REGION="jpn")

        def sync(**extra):
            return subprocess.run([sys.executable, f"{KIT}/integ_tree.py", "sync"], capture_output=True,
                                  text=True, env=dict(env, **extra))
        cold = sync()
        if cold.returncode or cold.stdout.strip() != str(tree).replace("\\", "/"):
            return "cold sync: exit %d, stdout %r, %s" % (cold.returncode, cold.stdout, cold.stderr[-300:])
        if (tree / "events").read_text().split("\n")[:2] != ["configure -", "fetch"]:
            return "cold sync did not configure then fetch: %r" % (tree / "events").read_text()
        subprocess.run(["ninja", "-t", "clean"], cwd=tree, capture_output=True)
        subprocess.run(["ninja", "tools/mwccarm/2.0/fx/mwccarm.exe"], cwd=tree, capture_output=True)
        if main_cc.read_text() != "checkout compiler":
            return "the tree's first build rewrote the checkout's compiler"
        if sync(FX_CONFIG_FAIL="1").returncode:
            return "a warm tree was reconfigured"
        (tree / "build.ninja").unlink()
        failed = sync(FX_CONFIG_FAIL="1")
        if failed.returncode == 0 or failed.stdout.strip():
            return "a failed configure still printed a tree path"
        (pre / "2.0/fx").mkdir(parents=True)
        (pre / "2.0/fx/mwccarm.exe").write_text("preinstalled")
        if sync(DQIX_PREINSTALLED_COMPILER=str(pre)).returncode or \
                (tree / "events").read_text().split("\n")[-2] != "configure " + str(pre):
            return "a preinstalled compiler was not passed to configure: %r" % (tree / "events").read_text()
    return None


@check("the integration tree's extract link stays out of the wave's commit",
       "off Windows link_dir makes extract/usa a symlink, which extract/.gitignore's `*/` does not "
       "ignore; the wave committed it and the fast-forward replaced the checkout's extracted ROM with a "
       "link to itself (main 0209a218)")
def _integ_extract_link_ignored():
    import subprocess
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        repo, tree = Path(d, "repo"), Path(d, "tree")
        (repo / "extract").mkdir(parents=True)
        (repo / "extract/.gitignore").write_text("*/\n")
        for args in (["init", "-q", "-b", "decomp-matching"], ["add", "."],
                     ["-c", "user.name=f", "-c", "user.email=f@f", "commit", "-qm", "f"]):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        (repo / "extract/usa").mkdir()
        r = subprocess.run([sys.executable, "-c", "import integ_tree; integ_tree.create()"], cwd=KIT,
                           capture_output=True, text=True,
                           env=dict(os.environ, DQIX_MAIN_REPO=str(repo), DQIX_INTEG=str(tree)))
        if r.returncode or not (tree / "extract/usa").exists():
            return "create() did not link extract/usa: %s" % r.stderr[-300:]
        st = subprocess.run(["git", "-C", str(tree), "status", "--porcelain"], capture_output=True,
                            text=True).stdout.strip()
        if st:
            return "the tree's status shows %r" % st
    return None


@check("proton.py hands configure a wine path without spaces",
       "configure.py writes the -w runner into build.ninja unquoted; Steam's \"Proton 9.0 (Beta)\" path "
       "failed every assembler step with `/bin/sh: Syntax error: \"(\" unexpected`, and the wave parked "
       "main 0209a218 as drift")
def _proton_wine_path():
    import subprocess
    from pathlib import Path
    if os.name == "nt":
        return None
    with tempfile.TemporaryDirectory() as d:
        proton, pfx = Path(d, "Proton 9.0 (Beta)/files"), Path(d, "share/pfx")
        (proton / "bin").mkdir(parents=True)
        (proton / "bin/wine").write_text("")
        pfx.mkdir(parents=True)
        r = subprocess.run([sys.executable, f"{KIT}/frida/proton.py", sys.executable, "-c",
                            "import os; print(os.environ['DQIX_WINE'])"], capture_output=True, text=True,
                           env=dict(os.environ, DQIX_PROTON=str(proton), DQIX_PROTON_PREFIX=str(pfx)))
        wine = r.stdout.strip()
        if r.returncode or not wine:
            return "proton.py failed: %s" % r.stderr[-300:]
        if re.search(r"[\s()]", wine):
            return "DQIX_WINE is %r" % wine
        if os.path.realpath(wine) != os.path.realpath(proton / "bin/wine"):
            return "DQIX_WINE %r does not reach Proton's wine" % wine
    return None


@check("both integrators skip sha1 without an ARM7 BIOS and still require it with one",
       "finish_wave exited 5 at `RED: sha1 mismatch` on every module for a contributor without the "
       "BIOS dump, so countfix, regionsync and the push never ran; CONTRIBUTING.md asks for sha1 only "
       "when you have the BIOS")
def _sha1_without_bios():
    import subprocess
    for script in ("integrate_fast.sh", "finish_wave.sh"):
        src = open(f"{KIT}/{script}", encoding="utf-8").read()
        i, j = src.find("sha1_ok() {"), src.find("\n}\n", src.find("sha1_ok() {"))
        if i < 0 or j < 0:
            return "%s has no sha1_ok()" % script
        if 'ninja sha1 2>&1 | grep -q "OK"' in src[j:]:
            return "%s still runs a raw sha1 check outside sha1_ok()" % script
        bash, env = _kp.bash(dict(os.environ, LOG="/dev/null"))
        with tempfile.TemporaryDirectory() as d:
            harness = src[i:j + 3] + 'ninja() { echo MISMATCH; }\nsha1_ok && echo PASS || echo FAIL\n'
            r = subprocess.run([bash, "-c", harness], cwd=d, capture_output=True, text=True, env=env)
            if "PASS" not in r.stdout:
                return "%s sha1_ok fails without arm7_bios.bin: %r" % (script, r.stdout + r.stderr)
            open(os.path.join(d, "arm7_bios.bin"), "w").close()
            r = subprocess.run([bash, "-c", harness], cwd=d, capture_output=True, text=True, env=env)
            if "FAIL" not in r.stdout:
                return "%s sha1_ok passed a mismatch with the BIOS present" % script
    return None


@check("both integrators build objdiff.json before countfix and report a countfix failure",
       "on a cold integration tree countfix read a missing objdiff.json, raised, corrected nothing, "
       "and integrate_fast still reported GREEN because only exit 3 was handled (kit issue #233)")
def _countfix_prereq():
    for script in ("integrate_fast.sh", "finish_wave.sh"):
        src = open(f"{KIT}/{script}", encoding="utf-8").read()
        i = src.find('countfix.py"')
        pre = src.rfind("ninja objdiff.json", 0, i)
        if i < 0 or pre < 0 or src.count("\n", pre, i) > 2:
            return "%s does not build objdiff.json right before countfix" % script
        if "WARN countfix failed" not in src:
            return "%s does not report an unexpected countfix exit" % script
    return None


@check("a worker MATCH with an invented construct goes back to the worker before it is staged",
       "021f9874, 021edf54 and 02184d80 were staged and landed with a volatile alias, volatile "
       "struct members and an invented parameter, because nothing checked a MATCH for constructs "
       "the developers could not have written until after it had landed")
def _match_quality_gate():
    src = open(f"{KIT}/pull_worker.sh", encoding="utf-8").read()
    i = src.find("matched=$((matched+1)); v=MATCH")
    j = src.find('cp "$f" "$STAGE/', i)
    if i < 0 or j < 0:
        return "the MATCH branch or its staging copy moved"
    block = src[i:j]
    for need in ('plausible.py" "$f"', "--resume", "suspect.tsv"):
        if need not in block:
            return "the MATCH branch no longer has %r before staging" % need
    return None


@check("recipe_select --lean keeps only the procedure and indexes every recipe",
       "the per-function doc runs to 55 KB and is re-sent on every worker turn; 2gifts' workers read "
       "a 3-8 KB brief and look recipes up on demand, so the lean arm must stay that small")
def _lean_doc():
    import subprocess
    out = subprocess.run([sys.executable, f"{KIT}/recipe_select.py", "main", "02000c9c", "--lean"],
                         capture_output=True, text=True).stdout.strip().replace("\\", "/")
    if not out or not os.path.exists(out):
        return "recipe_select --lean produced no doc"
    doc = open(out, encoding="utf-8").read()
    subprocess.run([sys.executable, f"{KIT}/recipe_select.py", "main", "02000c9c"], capture_output=True)
    if len(doc) > 20000:
        return "the lean doc is %d bytes" % len(doc)
    if "RECIPES NOT INCLUDED" not in doc:
        return "the lean doc has no recipe index"
    if "PULL_LEAN" not in open(f"{KIT}/pull_worker.sh", encoding="utf-8").read():
        return "pull_worker has no PULL_LEAN arm"
    return None


@check("an evolve run reserves its address against worker claims",
       "evolve ran on ov009 02185634 while a worker claimed the same address, paying twice for one "
       "function: nothing put an evolve target in wlog/evolve_queue.txt, the list claim.py skips")
def _evolve_reserves_address():
    E = load("evocap")
    with tempfile.TemporaryDirectory() as d:
        q = os.path.join(d, "evolve_queue.txt")
        E.reserve("009", "02185634", q)
        E.reserve("009", "02185634", q)
        E.reserve("main", "0201099c", q)
        lines = open(q, encoding="utf-8").read().split()
        if lines != ["ov009:02185634", "main:0201099c"]:
            return "evolve_queue.txt holds %r" % lines
    if "--reserve ${MOD}" not in open(f"{KIT}/.claude/workflows/dqix-evolve.js", encoding="utf-8").read():
        return "the evolve workflow does not pass --reserve to evocap.py"
    return None


@check("plausible.py flags a const volatile pointer local",
       "`const volatile struct CombatantStruct* c_v = c;` in 021f9874's worker attempt passed "
       "plausible.py because its volatile check required the line to start with `volatile`")
def _plausible_const_volatile():
    text = "void f(struct S* c) {\n    const volatile struct S* c_v = c;\n    g(c_v);\n}\n"
    if "VOLATILE-LOCAL" not in repr(load("plausible").findings(text)):
        return "plausible.py did not flag `const volatile struct S* c_v`"
    return None


@check("plausible.py flags a volatile cast on ordinary data and not on a hardware address",
       "`*(volatile unsigned char*)&entry->id` in 021e7cec forced a reload no developer wrote, and passed "
       "plausible.py because only volatile locals were checked")
def _plausible_volatile_cast():
    P = load("plausible")
    bad = "void f(E* e) {\n    unsigned char id = *(volatile unsigned char*)&e->id;\n}\n"
    good = ("void g(int i) {\n    *(volatile unsigned int*)0x4000488 = 1;\n"
            "    ((volatile int*)0x27ffdc4)[i] = 0;\n}\n")
    if "VOLATILE-CAST" not in repr(P.findings(bad)):
        return "plausible.py did not flag a volatile cast on a struct field"
    if "VOLATILE" in repr(P.findings(good)):
        return "plausible.py flagged a volatile hardware or shared-memory access: %r" % P.findings(good)
    return None


@check("plausible.py scans static inline helpers defined above the `// USA:` line",
       "a volatile read inside a helper above the tag passed plausible.py, which only scanned from "
       "the tag down, while a hardware register struct or extern there must stay unflagged")
def _plausible_helpers_above_tag():
    P = load("plausible")
    tail = '// USA: func_02000000\nextern "C" ARM int f(struct S* s) {\n    return Count(s);\n}\n'
    bad = "static inline int Count(struct S* s) { return *(volatile int*)&s->count; }\n" + tail
    good = ("struct Regs {\n    volatile unsigned int ctrl;\n};\n"
            "extern volatile unsigned int gVBlankCount;\n"
            "static inline unsigned int GetDispCnt(void) { return *(volatile unsigned int*)&DISPCNT; }\n"
            "static inline int Count(struct S* s) { return s->count; }\n" + tail)
    if (1, "VOLATILE-CAST") not in [(l, k) for l, k, _w in P.findings(bad)]:
        return "plausible.py did not flag the volatile cast in the helper above the tag: %r" % P.findings(bad)
    if P.findings(good):
        return "plausible.py flagged hardware or plain code above the tag: %r" % P.findings(good)
    return None


PLAUSIBLE_CASES = [
    ("NULL-PTR-DIFF",
     "`(int)(p - (char *)0)` exists only to emit `sub Rd, Rs, #0`",
     'extern "C" ARM int f(char* p) {\n    int i = (int)(p - (char *)0);\n    return i + 1;\n}\n',
     'extern "C" ARM int f(char* p, char* base) {\n    int i = p - base;\n    return i + 1;\n}\n'),
    ("TERNARY-SELF",
     "`w = c ? 0 : w;` stores a variable back into itself only to move its spill slot",
     'extern "C" ARM void f(S* e, T* obj) {\n    int w = 1;\n'
     '    if (e->mode == 1) w = obj->f311 != 0 ? 0 : w;\n    g(w);\n}\n',
     'extern "C" ARM void f(S* e, T* obj) {\n    int w = 1;\n'
     '    if (e->mode == 1 && obj->f311 != 0) w = 0;\n    g(w);\n}\n'),
    ("COMPARE-MINUS-ONE",
     "`x > -1` written for `x >= 0` only to keep an `mvn`",
     'extern "C" ARM int f(S* o) {\n    if (o->timer > -1) {\n        return 1;\n    }\n    return 0;\n}\n',
     'extern "C" ARM int f(S* o) {\n    if (o->timer >= 0) {\n        return 1;\n    }\n    return 0;\n}\n'),
    ("INDEX-CAST",
     "`tbl[(int)j]` widens an index only to break CSE",
     'extern "C" ARM int f(const short* tbl, unsigned char j) {\n    return tbl[(int)j];\n}\n',
     'extern "C" ARM int f(const short* tbl, unsigned char j, int x) {\n'
     '    return tbl[j] + tbl[(unsigned char)x];\n}\n'),
    ("FNPTR-CAST-CALL",
     "a named function called through a cast to another signature passes an argument it does not take",
     'extern "C" void _Z5Resetv();\nextern "C" ARM void f(char* base) {\n'
     '    ((void (*)(char*))_Z5Resetv)(base);\n}\n',
     'void Reset(char* base);\nextern "C" ARM void f(char* base, void* cb) {\n    Reset(base);\n'
     '    ((void (*)(char*))cb)(base);\n}\n'),
    ("LONGLONG-MASK",
     "`(int)((long long)x | 0x100000000LL)` truncates a 64-bit op straight back to keep `orr Rd, Rs, #0`",
     'extern "C" ARM int f(int x) {\n    return (int)((long long)x | 0x100000000LL);\n}\n',
     'extern "C" ARM long long f(int x) {\n    return (long long)x | 0x100000000LL;\n}\n'),
    ("CC-FLAG-EMULATION",
     "a variable standing in for the CPSR flags is a transliterated listing, not C",
     'extern "C" ARM int f(int r0) {\n    int cc;\n    cc = (int)(r0) - (int)(0x0);\n'
     '    if (cc != 0) {\n        return 1;\n    }\n    return 0;\n}\n',
     'extern "C" ARM int f(int value) {\n    if (value != 0) {\n        return 1;\n    }\n    return 0;\n}\n'),
    ("ABS-ADDRESS-CAST",
     "a data symbol replaced by its absolute address forces a second pool word and bakes in a USA address",
     'extern int data_02249b54;\nextern "C" ARM void f(void) {\n'
     '    g(((__typeof__(&data_02249b54))0x02249B54));\n}\n',
     'extern int data_02249b54;\nextern "C" ARM void f(void) {\n    g(&data_02249b54);\n'
     '    *(volatile unsigned int*)0x04000208 = 0;\n}\n'),
    ("SPLIT-POINTER-ADD",
     "a pointer bound and then bumped by a constant on the next statement only moves an `add`",
     'extern "C" ARM void f(char* obj) {\n    char* p = obj;\n    p += 0x10;\n    g(p);\n}\n',
     'extern "C" ARM void f(char* obj) {\n    char* p = obj + 0x10;\n    while (*p != 0) {\n'
     '        p++;\n    }\n    g(p);\n}\n'),
    ("POINTER-ROUND-TRIP",
     "`p++; (p - 1)->x` cancels out and exists only to defeat copy propagation",
     'struct S { int x; };\nextern "C" ARM void f(struct S* s) {\n    struct S* p = s;\n    p++;\n'
     '    (p - 1)->x = 0;\n}\n',
     'struct S { int x; };\nextern "C" ARM void f(struct S* s, int n) {\n    struct S* end = s + n;\n'
     '    (end - 1)->x = 0;\n}\n'),
    ("INT-PUN-NULL-TEST",
     "a struct's pointer member null-tested through `*(int*)p` only changes the CSE key",
     'struct Inner;\nstruct Outer { struct Inner* inner; };\nextern "C" ARM void f(struct Outer* p) {\n'
     '    if (*(int*)p != 0) {\n        g(p->inner);\n    }\n}\n',
     'struct Inner;\nstruct Outer { struct Inner* inner; };\nextern "C" ARM void f(struct Outer* p) {\n'
     '    if (p->inner != 0) {\n        g(p->inner);\n    }\n}\n'),
    ("NOOP-ADDR-CAST",
     "`*(unsigned char*)&e->id` on an `unsigned char` member is an address-taken read that only breaks CSE",
     'struct E { unsigned char id; };\nextern "C" ARM int f(struct E* e) {\n'
     '    unsigned char v = *(unsigned char*)&e->id;\n    return v;\n}\n',
     'struct E { unsigned char id; };\nextern "C" ARM int f(struct E* e) {\n'
     '    unsigned char v = e->id;\n    return v;\n}\n'),
    ("MEMBER-ADDR-NULL-TEST",
     "the address of a member is never null, so testing it exists only for its codegen",
     'struct Task { int active; };\nstruct Ctx { int pad; struct Task task; };\n'
     'extern "C" ARM int f(struct Ctx* ctx) {\n    struct Task* task = &ctx->task;\n'
     '    if (!(task != 0 && task->active != 0)) {\n        return 1;\n    }\n    return 0;\n}\n',
     'struct Task { int active; };\nstruct Ctx { int pad; struct Task task; };\n'
     'extern "C" ARM int f(struct Ctx* ctx) {\n    struct Task* task = &ctx->task;\n'
     '    if (task->active == 0) {\n        return 1;\n    }\n    return 0;\n}\n'),
    ("SELF-STORE",
     "`p->f = p->f;` stores a member back into itself",
     'struct Obj { int position; };\nextern "C" ARM void f(struct Obj* obj) {\n'
     '    obj->position = obj->position;\n}\n',
     'struct Obj { int position; };\nextern "C" ARM void f(struct Obj* obj, int x) {\n'
     '    obj->position = x;\n}\n'),
    ("INLINE-LOCAL-RETURN",
     "an inline getter that copies into a local and returns it exists only to reorder a load",
     'struct U { int id; };\nstatic inline int UnitId(struct U* u) { int id = u->id; return id; }\n'
     '// USA: func_02000000\nextern "C" ARM int f(struct U* u) {\n    return UnitId(u);\n}\n',
     'struct U { int id; };\nstatic inline int UnitId(struct U* u) { SDK_NULL_ASSERT(u); return u->id; }\n'
     'inline U& Shared() { static U s; return s; }\n'
     '// USA: func_02000000\nextern "C" ARM int f(struct U* u) {\n    return UnitId(u) + Shared().id;\n}\n'),
    ("INLINE-OFFSET-ADD",
     "an inline helper that only adds a constant to a pointer splits an offset the struct should carry",
     'static inline char* Off2400(char* p) { return p + 0x2400; }\n// USA: func_02000000\n'
     'extern "C" ARM void f(char* p) {\n    g(Off2400(p));\n}\n',
     'struct Obj { int pad[0x900]; int field; };\n'
     'static inline int GetField(struct Obj* o) { return o->field; }\n'
     'static inline int Next(int id) { return id + 1; }\n// USA: func_02000000\n'
     'extern "C" ARM void f(struct Obj* o) {\n    g(Next(GetField(o)));\n}\n'),
    ("INLINE-OFFSET-ADD",
     "a compiled-out SDK assert in front of the return made the helper two statements and hid it",
     'static inline char* Off2400(char* p) { SDK_NULL_ASSERT(p); return p + 0x2400; }\n'
     '// USA: func_02000000\nextern "C" ARM void f(char* p) {\n    g(Off2400(p));\n}\n',
     'struct Obj { int pad[0x900]; int field; };\n'
     'static inline int GetField(struct Obj* o) { SDK_NULL_ASSERT(o); return o->field; }\n'
     '// USA: func_02000000\nextern "C" ARM void f(struct Obj* o) {\n    g(GetField(o));\n}\n'),
    ("INLINE-IDENTITY",
     "an inline that returns its own parameter, cast, only adds an inline boundary",
     'struct A;\nstruct B;\nstatic inline struct A* AsA(struct B* b) { return (struct A*)b; }\n'
     '// USA: func_02000000\nextern "C" ARM void f(struct B* b) {\n    g(AsA(b));\n}\n',
     'struct A;\nstruct B;\ninline void* operator new(unsigned int, void* p) { return p; }\n'
     '// USA: func_02000000\nextern "C" ARM void f(struct B* b) {\n    g((struct A*)b);\n}\n'),
    ("SYMBOL-ALIAS",
     "a `_dup`/`_arg` extern names one address twice only to force a second pool word",
     'extern int data_ov031_02249b54;\nextern int data_ov031_02249b54_arg;\nextern "C" ARM void f(void) {\n'
     '    g(data_ov031_02249b54, &data_ov031_02249b54_arg);\n}\n',
     'extern int data_ov031_02249b54;\nextern "C" ARM void f(int start_arg) {\n'
     '    g(data_ov031_02249b54, &data_ov031_02249b54, start_arg);\n}\n'),
    ("HAND-ASM",
     "inline `__asm(\"mov a, b\")` forced registers in four landed functions and counted them as matches",
     '// USA: func_02000000\nextern "C" ARM void f(int* p, int* q) {\n    int* a;\n'
     '    __asm("mov a, p");\n    g(a, q);\n}\n',
     '// USA: func_02000000\nextern "C" ARM void f(int* p, int* q) {\n    /* asm { mov r0, r1 } */\n'
     '    g(p, q);\n}\n'),
]


@check("plausible.py blocks hand asm unless asm_allow.txt names its address or function",
       "landpr and merge_human landed asm with no gate, because only the integrators knew the allowlist")
def _plausible_asm_allowlist():
    P = load("plausible")
    pragmas = load("pragmas")
    allowed = sorted(pragmas.asm_allow())[0]
    body = 'extern "C" ARM asm void %s(void) {\n    bx lr\n}\n'
    if not [h for h in P.blocking("// USA: func_0200aaaa\n" + body % "func_0200aaaa") if h[1] == "HAND-ASM"]:
        return "an asm function off the allowlist is not blocking"
    if [h for h in P.blocking("// USA: func_%s\n" % allowed + body % ("func_" + allowed)) if h[1] == "HAND-ASM"]:
        return "an asm function at allowlisted %s is blocking" % allowed
    if [h for h in P.blocking(body % "Timer1OverflowInterruptRoutine") if h[1] == "HAND-ASM"]:
        return "an untagged asm function the allowlist names is blocking"
    return None


@check("merge_human stops repairing when a round changes nothing",
       "a merge whose link failed on a symbol no repair could reach ran eight repair rounds that each "
       "repointed 0 call sites, then a ninth identical check: nine ~62 s builds, 2026-09-09 02:42-02:51")
def _merge_human_stops_on_noop_round():
    import subprocess
    src = open(f"{KIT}/merge_human.sh", encoding="utf-8").read()
    start = src.find("tree_state() {")
    if start < 0:
        start = src.find("for i in 1 2 3 4 5 6 7 8; do")
    if start < 0:
        return "cannot locate the repair loop in merge_human.sh"
    with tempfile.TemporaryDirectory() as d:
        root = d.replace("\\", "/")
        os.makedirs(f"{root}/kit")
        os.makedirs(f"{root}/sp/wlog")
        os.makedirs(f"{root}/repo")
        with open(f"{root}/kit/relink_undefined.py", "w", encoding="utf-8") as fh:
            fh.write("")
        with open(f"{root}/kit/merge_fixups.sh", "w", encoding="utf-8") as fh:
            fh.write("true\n")
        with open(f"{root}/repo/a.txt", "w", encoding="utf-8") as fh:
            fh.write("a\n")
        for args in (("init", "-q"), ("config", "user.name", "regress"), ("config", "user.email", "regress@localhost"),
                     ("add", "-A"), ("commit", "-q", "-m", "base")):
            subprocess.run(["git", "-C", f"{root}/repo", *args], capture_output=True)
        script = (f'set -u\nKIT="{root}/kit"\nSP="{root}/sp"\nARG=1\ncd "{root}/repo"\n'
                  f'ninja() {{ echo "$*" >> "{root}/calls"; echo "FAILED: build/usa/arm9.o"; return 1; }}\n'
                  + src[start:])
        bash, benv = _kp.bash()
        r = subprocess.run([bash, "-c", script], capture_output=True, text=True, env=benv)
        calls = open(f"{root}/calls").read().split("\n")[:-1] if os.path.exists(f"{root}/calls") else []
    if r.returncode != 1 or "STILL FAILS" not in r.stdout:
        return f"exit {r.returncode}: {(r.stdout + r.stderr).strip()[-300:]}"
    if calls != ["check"]:
        return f"ran ninja {len(calls)} times for a repair that changed nothing: {calls}"
    return None


def _plausible_case(kind, bad, good):
    def run():
        P = load("plausible")
        got = [k for _l, k, _w in P.findings(bad)]
        if kind not in got:
            return "plausible.py did not flag %s (got %r)" % (kind, got)
        if P.findings(good):
            return "plausible.py flagged the natural form: %r" % P.findings(good)
        return None
    return run


for _kind, _fault, _bad, _good in PLAUSIBLE_CASES:
    check("plausible.py flags %s and passes the natural form" % _kind, _fault)(
        _plausible_case(_kind, _bad, _good))


@check("colorforce, schedforce and renum read the size argument the same way",
       "schedforce parsed the size as hex while colorforce took decimal, so the plan's 'same "
       "arguments' run read 2816 as 0x2816 and crashed in struct.unpack on ov000:02165490")
def _forcing_size_arg():
    for tool in ("frida/colorforce.py", "frida/schedforce.py", "pad/renum/renum.py"):
        src = open(f"{KIT}/{tool}", encoding="utf-8").read()
        if "int(sys.argv[4], 0)" not in src:
            return "%s does not parse the size with int(x, 0)" % tool
    return None


@check("schedforce's combo search is not pruned by a flip's standalone score",
       "the combo loop broke on `len(real) >= len(base_real)`, comparing each flip's score ON ITS "
       "OWN to the BASELINE, so once one improving flip landed every combination needing a second, "
       "individually-neutral flip was never compiled -- and the tool reported a finished search. "
       "On ov008 0218aa24 pick_193 (real 5) closed site B and pick_95..99 (all real 8) each "
       "attacked site A; 8 >= 7 ended the loop before pick_193+pick_95 was built")
def _schedforce_combo_not_pruned():
    src = open(f"{KIT}/frida/schedforce.py", encoding="utf-8").read()
    i = src.find("combo_real = ")
    if i < 0:
        return "schedforce.py no longer initialises combo_real; the combo search moved"
    body = src[i:i + 2000]
    for bad in ("len(real) >= len(base_real)", ">= len(base_real)"):
        if bad in body:
            return ("the combo loop still prunes on the baseline (%r): a flip that only helps in "
                    "combination is skipped, and the search reports itself complete" % bad)
    if "SF_COMBO" not in body:
        return "the combo loop has no cost bound; add SF_COMBO to cap the extra compiles"
    return None


@check("every .py the worker guide names actually exists in the kit",
       "core.md's register-pressure recipe named pad/renum/pressforce.py, schedrule.py, "
       "splitforce.py and irdump.py, and three of the four have never existed in this repository "
       "-- no deletion in history. core.md is the one document guaranteed in every worker's "
       "context and WORKFLOW.md tells them to grep it for their symptom, so a recipe pointing at "
       "tools that cannot be run reads as authoritative and costs turns before it is found out")
def _coremd_tools_exist():
    import re as _re
    text = open(f"{KIT}/worker_src/core.md", encoding="utf-8", errors="replace").read()
    names = set(_re.findall(r"`([a-z_0-9/]+\.py)`", text))
    missing = sorted(n for n in names if not os.path.exists(f"{KIT}/{n}"))
    if missing:
        return ("core.md names %d .py that do not exist: %s -- a worker following that recipe "
                "chases a tool that was never written" % (len(missing), ", ".join(missing)))
    return None


@check("the forcing tools accept both the bare and the ov-prefixed module label",
       "wgate/wdiff/wlist/evo_score/gate.sh take the bare label (006) while frida/ and pad/renum/ "
       "took ov006, and nothing said so; passing the label the module-baked gate.sh had just "
       "accepted died as a bare FileNotFoundError on .../overlays/006/delinks.txt. Three workers "
       "in one tranche lost a run each to it")
def _forcing_module_forms():
    import kitpaths as _kp
    for bare, want in (("006", "ov006"), ("ov006", "ov006"), ("main", "main"), ("15", "ov015")):
        if _kp.module_label(bare) != want:
            return ("module_label(%r) is %r, expected %r -- the two module conventions are still "
                    "a trap somewhere" % (bare, _kp.module_label(bare), want))
    tools = ("frida/schedforce.py", "frida/colorforce.py", "pad/renum/renum.py",
             "pad/cf_multi.py", "pad/shiftdiff.py")
    for t in tools:
        src = open(f"{KIT}/{t}", encoding="utf-8", errors="replace").read()
        if "module_label(" not in src:
            return ("%s does not normalise its module argument through module_label(), so it still "
                    "accepts only one of the two forms" % t)
    return None


@check("plausible flags a zero-negation that only exists to emit rsb padding",
       "`zero = 0 - zero;` was invisible to plausible.py, so a candidate whose .text is only exactly "
       "the slot size because of the invented padding assignment scored fitness 11 with no "
       "implausible key and no +200 penalty. evo_score's fitness is the selection function for "
       "every evolve run, so a construct the scorer cannot see is one evolve will select and breed "
       "from. Live on ov008 02186388, where the honest source scores 985 and the padded one 11")
def _plausible_zero_negate():
    p = load("plausible")

    def kinds(src):
        return [k for _l, k, _w in p.findings(src)]

    head = '// USA: func_ov008_02186388\nextern "C" ARM void f(S* s) {\n'
    pad = head + "    int zero = 0;\n    zero = 0 - zero;\n    s->out = zero;\n}\n"
    if "ZERO-NEGATE-PAD" not in kinds(pad):
        return ("plausible did not flag `zero = 0 - zero;` immediately after `int zero = 0;` "
                "(got %r): a self-negation of a provably-zero local has no meaning outside the "
                "`rsb reg, reg, #0` it emits" % kinds(pad))

    real = head + "    unsigned int m = s->m;\n    m = 0u - m;\n    s->out = m;\n}\n"
    if kinds(real):
        return ("plausible flagged legitimate unsigned negation of a live value (got %r): "
                "`0u - m` on a non-constant is ordinary C89 code" % kinds(real))
    gap = head + "    int v = 0;\n    g();\n    v = 0 - v;\n    s->out = v;\n}\n"
    if kinds(gap):
        return ("plausible flagged a negation whose variable may have changed since it was zeroed "
                "(got %r): the check must require the zero to still hold" % kinds(gap))
    return None


@check("landpr refreshes the build report after it publishes",
       "landpr.py never ran `ninja report`, so after a pull-request landing cov.py and health kept "
       "the previous wave's count while CI showed the new one")
def _landpr_report():
    import ast
    tree = ast.parse(open(f"{KIT}/landpr.py", encoding="utf-8").read())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [ast.unparse(c) for c in ast.walk(main) if isinstance(c, ast.Call)]
    if not any("'ninja', 'report'" in c for c in calls):
        return "landpr.main() does not run `ninja report`"
    if not any("integ_tree.py" in c and "'report'" in c for c in calls):
        return "landpr.main() does not copy the report out of the integration tree"
    return None


@check("the cached kit-behind count is dropped when the checkout's HEAD moves",
       "behind() cached `5` for 10 minutes after a manual pull, so every dispatcher restart saw KIT "
       "UPDATE WAITING, ran kit_update (up to date) and restarted again, in a loop")
def _behind_cache_keyed_to_head():
    K = load("kitpaths")
    head = __import__("subprocess").run(["git", "-C", KIT, "rev-parse", "HEAD"], capture_output=True,
                                        text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "wlog"))
        K.SP, K.KIT_URL = d, os.path.join(d, "no-such-remote")
        stamp = os.path.join(d, "wlog", ".kit_fresh")
        open(stamp, "w").write("5 " + head)
        if K.behind() != 5:
            return "a fresh stamp for the current HEAD was not used"
        open(stamp, "w").write("5 0000000000000000000000000000000000000000")
        if K.behind() != 0:
            return "a stamp written for another HEAD still reported 5 commits behind"
    return None


@check("a kit update runs the end-to-end crack tests only when what they prove changed",
       "every update whose commits touched regress.py ran regress.py --slow inside kit_init while the "
       "dispatcher held every slot: 10:56-11:08 on 2026-10-14 for a prready.py fix; 103 of 200 kit "
       "commits touch regress.py, 8 touch the sweep, the gate or the fixtures")
def _kit_update_slow_when_unproven():
    ku = load("kit_update")
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "wlog"))
        ku.SP = d
        with open(os.path.join(d, "wlog", "functional_stamp.txt"), "w", encoding="utf-8") as fh:
            fh.write(sweep_fingerprint())
        if ku.slow(["regress.py", "prready.py"]):
            return "a regress.py change with the crack tests proven for this code ran regress.py --slow"
        missed = [f for f in ("colorsweep.py", "wdiff.py", "wgate.py", "regress_fixtures/x.cpp") if not ku.slow([f])]
        if missed:
            return f"an update touching {missed} skipped the crack tests"
        with open(os.path.join(d, "wlog", "functional_stamp.txt"), "w", encoding="utf-8") as fh:
            fh.write("stale")
        if not ku.slow(["regress.py"]):
            return "a regress.py change with a stale functional stamp skipped the crack tests"
    return None


@check("cov.py reads the newer of the checkout's and the integration tree's build report",
       "waves build in the integration tree, so cov.py and health read a two-day-old report from the "
       "decomp checkout: 90.04% while CI on the same commit said 92.40%")
def _cov_newest_report():
    C = load("cov")
    with tempfile.TemporaryDirectory() as d:
        trees = [os.path.join(d, "repo"), os.path.join(d, "integ")]
        for i, t in enumerate(trees):
            p = os.path.join(t, "build", C.REGION, "report.json")
            os.makedirs(os.path.dirname(p))
            open(p, "w").close()
            os.utime(p, (1000 + i, 1000 + i))
        if os.path.normpath(C.newest_report(trees)) != os.path.normpath(
                os.path.join(trees[1], "build", C.REGION, "report.json")):
            return "cov.py picked the older report"
    return None


@check("kitpaths.bash() finds Git Bash, never WSL, and its PATH runs coreutils",
       "PATH-only selection chose System32 WSL bash under native Windows Python, and Git's usr/bin "
       "bash without usr/bin on PATH failed with `mkdir: command not found` from PowerShell (kit PR #133)")
def _git_bash():
    import subprocess
    from unittest import mock
    if os.name == "nt":
        with tempfile.TemporaryDirectory() as d:
            for p in ("Windows/System32/bash.exe", "Portable/cmd/git.exe", "Portable/usr/bin/bash.exe"):
                os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
                open(os.path.join(d, p), "w").close()
            which = {"bash": os.path.join(d, "Windows/System32/bash.exe")}
            with mock.patch.dict(os.environ, {"PATH": "x"}, clear=True), \
                    mock.patch("shutil.which", lambda n: which.get(n)):
                try:
                    _kp.bash()
                    return "kitpaths.bash() accepted WSL's System32 bash"
                except FileNotFoundError:
                    pass
                which["git"] = os.path.join(d, "Portable/cmd/git.exe")
                sh, env = _kp.bash()
                if os.path.normcase(sh) != os.path.normcase(_kp._norm(os.path.join(d, "Portable/usr/bin/bash.exe"))):
                    return "kitpaths.bash() picked %s, not the Git root beside git.exe" % sh
    sh, env = _kp.bash(dict(os.environ, PATH=os.environ.get("SystemRoot", "/nonexistent")))
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run([sh, "--noprofile", "--norc", "-c", 'mkdir -p "$1/a/b" && find "$1/a" -name b',
                            "x", d.replace("\\", "/")], capture_output=True, text=True, env=env, timeout=30)
        if r.returncode or not r.stdout.strip():
            return "the returned shell cannot run coreutils: " + (r.stderr or r.stdout)[:200]
    return None


@check("psq.sh, fullstop.sh --dry and progress.py see a live pull_worker.sh off Windows",
       "on Linux all three asked powershell.exe for the process table: psq.sh printed nothing, "
       "fullstop --dry said 'none running' and STATE.md called the counts unknown, with a worker alive")
def _posix_process_tools():
    import subprocess
    if os.name == "nt":
        return None
    with tempfile.TemporaryDirectory() as d:
        drv = os.path.join(d, "pull_worker.sh")
        with open(drv, "w") as fh:
            fh.write("read -t 60 x\n")
        sh, env = _kp.bash()
        decoy = subprocess.Popen([sh, drv], stdin=subprocess.PIPE, env=env)
        try:
            time.sleep(0.5)
            run = lambda *a: subprocess.run([sh, f"{KIT}/{a[0]}", *a[1:]], capture_output=True,
                                            text=True, env=env, timeout=120).stdout
            listed = run("psq.sh", "--list")
            if not re.search(r"(?m)^%d " % decoy.pid, listed) or "psq.sh" in listed:
                return "psq.sh --list: %r" % listed[:300]
            if not re.search(r"pid %d " % decoy.pid, run("fullstop.sh", "--dry").split("TIER 2")[0]):
                return "fullstop --dry did not list a live pull_worker.sh in TIER 1"
            if load("progress").fleet()[1] < 1:
                return "progress.fleet() counted no live pull_worker.sh"
        finally:
            decoy.stdin.close()
            decoy.wait()
    return None


@check("compiler sweeps enumerate the configured compiler root",
       "ccsweep and pad/ccscore ignored a preinstalled compiler directory")
def _compiler_sweep_root_fixture():
    import ast
    import glob
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory() as root:
        compiler_root = Path(root, "compiler root")
        compiler = compiler_root / "2.0" / "sp2p2" / "mwccarm.exe"
        compiler.parent.mkdir(parents=True)
        compiler.touch()
        cfg = SimpleNamespace(COMPILER_ROOT=str(compiler_root))
        source = Path(KIT, "pad", "ccscore.py").read_text(encoding="utf-8")
        ns = dict(glob=glob, casediff=SimpleNamespace(REPO=root, buildcfg=cfg))
        _fixture_assignments(source, ns, {"builds"})
        if [os.path.normpath(p) for p in ns["builds"]] != [str(compiler)]:
            return "ccscore did not enumerate the configured compiler"
        source = Path(KIT, "ccsweep.sh").read_text(encoding="utf-8")
        snippet = source[source.index('cd "$REPO"'):]
        harness = ('python() { case "$1" in */buildcfg.py) printf "%s\\n" "$ROOT";; '
                   '*/wdiff.py) printf "%s\\n" "$MWCC";; esac; };\n' + snippet)
        bash, env = _kp.bash(dict(os.environ, ROOT=compiler_root.as_posix(), REPO=root, KIT=KIT))
        result = subprocess.run([bash, "-c", harness], capture_output=True, text=True, env=env)
        if result.returncode or not re.search(r"2\.0/sp2p2\s+2\.0/sp2p2", result.stdout):
            return "ccsweep did not use the configured root: " + result.stdout + result.stderr
        source = Path(KIT, "buildcfg.py").read_text(encoding="utf-8")
        main = next(n for n in ast.parse(source).body if isinstance(n, ast.If) and
                    ast.unparse(n.test) == "__name__ == '__main__'")
        printed = []
        exec(compile(ast.Module(body=main.body, type_ignores=[]), "buildcfg", "exec"),
             dict(sys=SimpleNamespace(argv=["buildcfg.py", "--compiler-root"]),
                  COMPILER_ROOT=str(compiler_root), print=printed.append))
        if printed != [compiler_root.as_posix()]:
            return "buildcfg CLI did not return the configured root"


@check("a residue measured on invented code is not parked, queued or counted as an idiom",
       "a miss on a file with a volatile local was recorded as REGALLOC 4, queued as a near miss and "
       "resumed in the same invented form instead of being stripped back to a natural one first")
def _blocker_implausible():
    B = load("blocker")
    B.gate_residue = lambda mod, addr, src: ("REGALLOC", 4, "r4<->r5")
    body = '// USA: func_02000000\nextern "C" int f(int* p) {\n%s    return p[0];\n}\n'
    with tempfile.TemporaryDirectory() as d:
        bad, good = os.path.join(d, "bad.cpp"), os.path.join(d, "good.cpp")
        with open(bad, "w") as fh:
            fh.write(body % "    volatile int t = p[1];\n")
        with open(good, "w") as fh:
            fh.write(body % "")
        invented, natural = B.measure("main", "02000000", bad), B.measure("main", "02000000", good)
        if invented[0] != "IMPLAUSIBLE" or "VOLATILE-LOCAL" not in invented[2]:
            return "invented file measured %r" % (invented,)
        if natural[0] != "REGALLOC":
            return "natural file measured %r" % (natural,)
        tsv = os.path.join(d, "blockers.tsv")
        with open(tsv, "w") as fh:
            fh.write("1\tmain\t02000000\t64\tIMPLAUSIBLE\t4\tx\t%s\n" % bad)
            fh.write("1\tmain\t02000004\t64\tREGALLOC\t6\tx\t%s\n" % good)
        N = load("nearmiss")
        N.TSV = tsv
        N.matched_ranges, N._last_paid, N._declined_classes = (lambda: []), (lambda a: 0), set
        N.skiplisted = N.staged = N.reserved = set
        queued = [r[3] for r in N.rows(16, verify=False)]
        if queued != ["02000004"]:
            return "near-miss queue held %r" % queued
    if not load("blockercheck").unfinished({"cls": "IMPLAUSIBLE", "metric": "4", "size": 64}):
        return "blockercheck counts IMPLAUSIBLE as an uncracked idiom class"


@check("claim.py skips an address another contributor reserved, and never a range's end",
       "claim.py did not read kit issues, so the xl queue opened on ov003 021539a0 (#178) and "
       "ov012 02184d80 (#227), both reserved by contributors")
def _reserved_skipped():
    R = load("reserved")
    issues = [{"number": 1, "author": {"login": "other"}, "title": "ov012",
               "body": "| Module | Start | End exclusive |\n|---|---|---|\n"
                       "| ov012 | `0x02184d80` | `0x0218558c` |\n"
                       "- Range: [021ce524, 021ce5b4)\nov017 021c0000 021c1000\n"},
              {"number": 2, "author": {"login": "me"}, "title": "Fleet claims",
               "body": "| ov024 | `021da9e0` |"}]
    prs = [{"number": 3, "author": {"login": "other"}, "title": "x", "body": "",
            "files": [{"path": "src/func_ov031_02221f78.cpp"}, {"path": "src/Main/GetData021052b4.cpp"}],
            "diff": "+    .text start:0x020aa000 end:0x020aa100\n-    .text start:0x020bb000 end:0x020bb100\n"}]
    got = set(R.holders(issues, prs, "me"))
    want = {"02184d80", "021ce524", "021c0000", "021c1000", "02221f78", "021052b4", "020aa000"}
    if got != want:
        return "holders() returned %s, want %s" % (sorted(got), sorted(want))
    if set(R.holders(issues, prs, "me", {"someone"})):
        return "holders() honoured a login RESERVED_FROM does not name"
    issues[0]["updatedAt"] = "2020-01-01T00:00:00Z"
    if set(R.holders(issues, prs, "me")) != {"02221f78", "021052b4", "020aa000"}:
        return "holders() honoured an issue untouched for longer than STALE_DAYS"
    C = load("claim")
    old, C.reserved._HELD = C.reserved._HELD, {"0dead000"}
    try:
        if "0dead000" not in C.skiplist():
            return "claim.skiplist() ignores reserved addresses"
    finally:
        C.reserved._HELD = old
    return None


@check("the worker doc never tells a worker to edit the kit checkout",
       "core.md said to add a deadends.md row after spending budget; a worker edited the live kit "
       "checkout, kit_update refused the dirty tree, and the dispatcher stopped claiming")
def _workers_leave_kit_alone():
    core = open(f"{KIT}/worker_src/core.md", encoding="utf-8").read()
    if re.search(r"(?i)add a row (there|to [`']?worker_src/deadends)", core):
        return "core.md still asks workers to add rows to deadends.md"
    if "Never edit that file or anything else in the kit checkout" not in core:
        return "core.md no longer tells workers to keep out of the kit checkout"
    return None


@check("the fleet's claims issue lists no claim older than CLAIM_TTL_MIN",
       "claim.py reaps stale claims only in the module it is claiming from, so #325 published 64 "
       "addresses, 48 of them landed, while no worker was running")
def _published_claims_reaped():
    R = load("reserved")
    C = load("claim")
    with tempfile.TemporaryDirectory(dir=f"{SP}/handwork", ignore_cleanup_errors=True) as sp:
        for mod, a, age in (("017", "0219d250", 3 * 86400), ("main", "02029988", 60)):
            p = os.path.join(sp, "claims", mod, a)
            os.makedirs(p)
            t = time.time() - age
            os.utime(p, (t, t))
        got = R.claims(sp)
    if got != [("main", "02029988")]:
        return "claims() published %s, want only the live main 02029988 (TTL %d min)" % (got, C.CLAIM_TTL_MIN)
    return None


@check("reserved.py reads a pull request too large for gh pr diff from its file patches",
       "#117 changed 900 files; gh pr diff refused it (HTTP 406 too_large) and every refresh fell back "
       "to the last list, so no reservation changed while it was open")
def _reserved_large_pr():
    R = load("reserved")

    def gh(*args):
        if args[:2] == ("pr", "diff"):
            raise RuntimeError("HTTP 406: the diff exceeded the maximum number of files\nPullRequest.diff too_large")
        if args[0] == "api" and "pulls/117/files" in " ".join(args):
            return "@@ -1 +1,3 @@\n+src/x.cpp:\n+    .text start:0x021fe000 end:0x021fe100\n"
        raise RuntimeError("unexpected gh %s" % (args,))

    old, R._gh = R._gh, gh
    try:
        diff = R.pr_diff(117) if hasattr(R, "pr_diff") else ""
    except RuntimeError as e:
        return "pr_diff raised on a too-large pull request: %s" % e
    finally:
        R._gh = old
    if R.DIFF_START.findall(diff) != ["021fe000"]:
        return "a too-large pull request's delink starts were not read: %r" % diff
    return None


@check("a hyphenated residue class ranks by its class, and a failed compile never wins",
       "`RESIDUE \\w+` cannot match LOOP-SHAPE or NO-COMPILE: flagsweep ranked LOOP-SHAPE 308 as `?`, "
       "and permorder scored NO-COMPILE -1 as 1, ahead of UNDERGEN 4 (kit PR #130)")
def _hyphenated_residue():
    F, P = load("flagsweep"), load("pad/permorder")
    if F.rank("RESIDUE LOOP-SHAPE 308") != (2, 308):
        return "flagsweep.rank(LOOP-SHAPE 308) = %r" % (F.rank("RESIDUE LOOP-SHAPE 308"),)
    if not P.score("RESIDUE NO-COMPILE -1") > P.score("RESIDUE UNDERGEN 4"):
        return "permorder scores a failed compile ahead of UNDERGEN 4"
    text = "gate output\nRESIDUE LOOP-SHAPE 308 1 branch target(s) differ\n"
    if load("residue").headline(text) != "RESIDUE LOOP-SHAPE 308":
        return "residue.headline() dropped a hyphenated class"
    if load("blocker").residue.parse_verdict(text)[:2] != ("LOOP-SHAPE", 308):
        return "blocker no longer parses through residue.parse_verdict"
    return None


@check("pull_worker sizes the claimed function from the config",
       "size_of read symbols.txt through a literal \"$REPO\" inside a quoted heredoc, so every claim "
       "logged 0B and got the small doc and the $3 cap: ov016 0218d2f4 (2924B) was served that way")
def _worker_size_of():
    import subprocess
    size, addr = max(load("claim").function_sizes("main"))
    src = open(f"{KIT}/pull_worker.sh", encoding="utf-8").read()
    fn = re.search(r"(?ms)^size_of\(\) \{.*?^\}\n", src).group(0)
    bash, env = _kp.bash(dict(os.environ, MARG="main", KIT=KIT))
    r = subprocess.run([bash, "-c", fn + 'size_of "$1"', "x", addr], capture_output=True, text=True,
                       env=env, timeout=60)
    if r.stdout.strip() != str(size):
        return "size_of main %s printed %r, want %d (%s)" % (addr, r.stdout.strip(), size,
                                                             r.stderr.strip()[-200:])
    return None


def _asmparked_src(src):
    """The asmparked() function text, up to the next top-level def/class.

    A trailing `^\\S` grab takes the first character of the following line instead of stopping at the
    blank lines before it, which splices a stray letter into the extracted source.
    """
    m = re.search(r'(?ms)^def asmparked\(.*?(?=^\S|\Z)', src)
    return m.group(0) if m else ""


@check("repairsweep does not rescue a gated hand-asm file ov_recover already parked",
       "gated/ keeps the file after ov_recover parks it to asm_park_<mod>/, and rescue_gated() copied "
       "anything that gated MATCH into staging/ -- so main 0200c0e4, 0200c14c and 020ca650 went round "
       "rescue -> wave refuses on asm policy -> re-park -> rescue every wave, one full rebuild each "
       "for 0 commits. cleanwork.sh had the same guard; this was the second path into staging/")
def _repairsweep_respects_asmpark():
    import subprocess, tempfile, shutil, os
    src = open(f"{KIT}/repairsweep.py", encoding="utf-8").read()
    if "def asmparked(" not in src:
        return "repairsweep.py has no asmparked() helper"
    helper = _asmparked_src(src)
    if not helper or "asmpark_" not in helper:
        return ("asmparked() never reads wlog/asmpark_<mod>.txt, so a parked hand-asm address is "
                "rescued from gated/ into staging/ on the MATCH verdict alone (main 020ca650, one "
                "rebuild per wave, 0 commits)")
    body = re.search(r'(?ms)^def rescue_gated\(\):\n(.*?)^\S', src)
    if not body:
        return "could not find rescue_gated() in repairsweep.py"
    if "asmparked(" not in body.group(1):
        return "rescue_gated() never calls asmparked(), so it promotes parked hand-asm from gated/"
    if "parked.get(" not in body.group(1):
        return "rescue_gated() loads asmpark but never consults it for the address it is copying"

    # Exercise the real helper against a temp state dir: the listed address must be reported parked,
    # and an unlisted one must not be. repairsweep.py is a SCRIPT (module level driver code), so it
    # cannot be imported; extract asmparked() and exec just that, with SP pointed at the fixture.
    sp = tempfile.mkdtemp(prefix="rs_")
    try:
        os.makedirs(f"{sp}/wlog", exist_ok=True)
        listed, unlisted = "020ca650", "0216dbf0"
        open(f"{sp}/wlog/asmpark_main.txt", "w").write(listed + "\n")
        fn = _asmparked_src(src)
        # Built by concatenation, not %%: fn is the real source and contains % signs in prose.
        prog = ("SP = " + repr(sp) + "\n" + fn + "\n" +
                'p = asmparked({"main"})\n'
                'print("LISTED" if ' + repr(listed) + ' in p.get("main", ()) else "MISSING")\n'
                'print("LEAKED" if ' + repr(unlisted) + ' in p.get("main", ()) else "CLEAN")\n')
        r = subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True,
                           env=dict(os.environ, SP=sp, DQIX_STATE=sp), timeout=120)
        out = r.stdout.split()
        if "LISTED" not in out:
            return ("asmparked() did not report %s as parked (stdout=%r stderr=%r) -- the rescue "
                    "guard would promote it" % (listed, r.stdout.strip(), r.stderr.strip()[-200:]))
        if "CLEAN" not in out:
            return ("asmparked() reported %s as parked, but it is not in asmpark_main.txt -- the "
                    "guard would block a landable match" % unlisted)
        return None
    finally:
        shutil.rmtree(sp, ignore_errors=True)


@check("kitpaths reads HEAD from .git without spawning git, in a worktree and from packed refs",
       "every kit script imports kitpaths, and its freshness check spawned `git rev-parse HEAD` on each import")
def _head_without_git():
    import shutil
    import subprocess
    base = tempfile.mkdtemp(prefix="rh_")
    try:
        repo, wt = os.path.join(base, "repo"), os.path.join(base, "wt")
        os.makedirs(repo)

        def git(cwd, *a):
            return subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                  capture_output=True, text=True).stdout.strip()
        git(repo, "init", "-q", "-b", "trunk")
        git(repo, "commit", "-q", "--allow-empty", "-m", "a")
        git(repo, "worktree", "add", "-q", "-b", "side", wt)
        git(wt, "commit", "-q", "--allow-empty", "-m", "b")
        git(repo, "pack-refs", "--all")
        detached = os.path.join(base, "detached")
        git(repo, "worktree", "add", "-q", "--detach", detached, "trunk")
        want = {r: git(r, "rev-parse", "HEAD") for r in (repo, wt, detached, KIT)}
        if len(set(want.values()) - {""}) < 2:
            return "the fixture repository did not build: %s" % want
        real = subprocess.run

        def refuse(*a, **kw):
            raise AssertionError("spawned %s" % (a[0] if a else kw.get("args"),))
        subprocess.run = refuse
        try:
            got = {r: _kp.head(r) for r in want}
        except AssertionError as e:
            return "kitpaths.head %s" % e
        finally:
            subprocess.run = real
        bad = {r: (got[r], w) for r, w in want.items() if got[r] != w}
        return "kitpaths.head disagrees with git rev-parse: %s" % bad if bad else None
    finally:
        shutil.rmtree(base, ignore_errors=True)


SPAWN_PROBE = ("import subprocess, sys\nsys.path.insert(0, sys.argv[1])\nseen = []\n"
               "orig = subprocess.Popen.__init__\n"
               "def init(self, args, *a, **kw):\n"
               "    seen.append(args if isinstance(args, str) else ' '.join(map(str, args)))\n"
               "    return orig(self, args, *a, **kw)\n"
               "subprocess.Popen.__init__ = init\n"
               "__import__(sys.argv[2])\nprint(repr(seen))\n")


def spawns_on_import(mod):
    import ast
    import subprocess
    r = subprocess.run([sys.executable, "-c", SPAWN_PROBE, KIT, mod], capture_output=True, text=True,
                       env=dict(os.environ, DQIX_NO_FRESHNESS="1"), timeout=120)
    lines = r.stdout.strip().splitlines()
    return ast.literal_eval(lines[-1]) if lines else ["import failed: %s" % r.stderr.strip()[-200:]]


@check("importing buildcfg spawns no process",
       "configure.py's get_platform called platform.system(), which runs `cmd /c ver` on Windows, on every "
       "import of buildcfg by every gate, sweep and claim")
def _buildcfg_spawns_nothing():
    seen = spawns_on_import("buildcfg")
    return "importing buildcfg spawned %s" % seen if seen else None


@check("spans.Spans answers exactly what a linear scan of the ranges answers",
       "claim, resumable, progress and selfcheck scanned every delink range for every function, 16M "
       "comparisons per claim")
def _spans_match_linear():
    import random
    S = load("spans")
    rnd = random.Random(7)
    for _ in range(200):
        ranges = [(lo, lo + rnd.randint(-3, 12)) for lo in (rnd.randint(0, 80) for _ in range(rnd.randint(0, 9)))]
        s = S.Spans(ranges)
        for x in range(-2, 100):
            if (x in s) != any(lo <= x < hi for lo, hi in ranges):
                return "Spans(%r) says %d is %s" % (ranges, x, "inside" if x in s else "outside")
    return None


@check("claim.pools() reads each module's open functions once",
       "pools() rebuilt the unmatched list 51 times per call, 1.4 s each, so every --best and every claim "
       "took seconds")
def _pools_once_per_module():
    C = load("claim")
    calls = []
    real = C.skiplist

    def counted():
        calls.append(1)
        return real()
    with tempfile.TemporaryDirectory() as d:
        sp, C.SP, C.skiplist = C.SP, d, counted
        try:
            C.pools()
            mods = len(C.all_modules())
        finally:
            C.SP, C.skiplist = sp, real
    if len(calls) > mods:
        return "pools() rebuilt the open list %d times for %d modules" % (len(calls), mods)
    return None


@check("claim.py runs its gates in-process, quietly, and a gate that fails holds",
       "each claim spawned two Python children for levercheck and blockercheck")
def _claim_gates_in_process():
    import contextlib
    import io
    import subprocess
    C = load("claim")
    d = tempfile.mkdtemp(prefix="rg_")
    try:
        for name, body in (("rgpass", "def main():\n    print('noise')\n    return 0\n"),
                           ("rghold", "def main():\n    print('noise')\n    return 1\n"),
                           ("rgboom", "def main():\n    raise ValueError('x')\n")):
            open(os.path.join(d, name + ".py"), "w").write(body)
        sys.path.insert(0, d)
        real = subprocess.Popen

        def refuse(*a, **kw):
            raise AssertionError("spawned a process")
        subprocess.Popen = refuse
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                got = (C.gates_hold(("rgpass.py",)), C.gates_hold(("rgpass.py", "rghold.py")),
                       C.gates_hold(("rgboom.py",)))
        finally:
            subprocess.Popen = real
            sys.path.remove(d)
        if got != (False, True, True):
            return "gates_hold gave %s for pass, pass+hold, raising; want (False, True, True)" % (got,)
        if out.getvalue():
            return "a gate's output reached claim.py's stdout: %r" % out.getvalue()
        return None
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


@check("countfix diffs its units concurrently and keeps their order",
       "selfcheck and both landing paths ran objdiff-cli once per unit in series, through one shared "
       "output file")
def _countfix_concurrent():
    import threading
    C = load("countfix")
    live, peak, lock = [0], [0], threading.Lock()

    def slow(unit):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.2)
        with lock:
            live[0] -= 1
        size = 6 if unit == "b" else 8
        left = {"name": unit, "size": str(size + 2), "address": "0",
                "instructions": [{"diff_kind": "DIFF_DELETE", "instruction": {"formatted": "lsl r0, #0x0"}}]}
        return [(left, {"name": unit, "size": str(size), "instructions": []})]
    C.diff_unit = slow
    C.function_locations = lambda: {u: [("cfg", 0)] for u in "abcd"}
    _relocs, sizes = C.plan(list("abcd"))
    if peak[0] < 2:
        return "countfix.plan ran its units one at a time"
    if [s[1] for s in sizes] != list("abcd"):
        return "countfix.plan reordered its units: %s" % [s[1] for s in sizes]
    return None


@check("progress reads selfcheck's and regress's recorded results instead of re-running them",
       "pull_all runs progress.py every 120 s and each run spent 3 minutes re-running both suites")
def _progress_reads_results():
    import subprocess
    P = load("progress")
    with tempfile.TemporaryDirectory() as d:
        sp, _kp.SP = _kp.SP, d
        real = subprocess.run

        def refuse(*a, **kw):
            raise AssertionError("spawned %s" % (a[0] if a else kw.get("args"),))
        try:
            _kp.record("selfcheck", ["ok    x", "56/57 invariants hold"])
            subprocess.run = refuse
            got = P.last_result("selfcheck"), P.last_result("regress")
        except AssertionError as e:
            return "progress %s" % e
        finally:
            subprocess.run = real
            _kp.SP = sp
    if not got[0].startswith("56/57 invariants hold") or got[1] != "did not run":
        return "progress read %r" % (got,)
    return None


@check("selfcheck and regress record their result where progress and health read it",
       "nothing wrote wlog/selfcheck.txt, so health.sh's invariant alert could never fire")
def _suites_record_results():
    with tempfile.TemporaryDirectory() as d:
        sp, _kp.SP = _kp.SP, d
        try:
            R = load("regress")
            R.PASSED[0], R.FAILED[:] = 3, [("a check", "its fault", "what broke")]
            line = R.record()
            text = open(_kp.result_path("regress"), encoding="utf-8").read()
        finally:
            _kp.SP = sp
    if line != "3 passed, 1 failed" or not text.endswith("3 passed, 1 failed\n") or "FAIL  a check" not in text:
        return "regress recorded %r" % text
    src = open(f"{KIT}/selfcheck.py", encoding="utf-8").read()
    if '_kp.record("selfcheck"' not in src or "m.record()" not in src:
        return "selfcheck no longer records its own result and regress's"
    return None


PROCESS_READER = "powershell.exe" if os.name == "nt" else "ps"


@check("fullstop --dry reads the process table once",
       "six PowerShell process queries and a basename per kit script made every dry run take 20-40 s")
def _fullstop_one_snapshot():
    import shutil
    import subprocess
    d = tempfile.mkdtemp(prefix="fs_")
    try:
        log = os.path.join(d, "calls.log").replace("\\", "/")
        for name in (PROCESS_READER, "basename"):
            with open(os.path.join(d, name), "w", newline="\n") as fh:
                fh.write("#!/bin/sh\necho %s >> '%s'\n" % (name, log))
            os.chmod(fh.name, 0o755)
        sh, env = _kp.bash()
        env = dict(env, PATH=d + os.pathsep + env["PATH"], DQIX_NO_FRESHNESS="1")
        r = subprocess.run([sh, f"{KIT}/fullstop.sh", "--dry"], capture_output=True, text=True, env=env,
                           timeout=300)
        calls = open(log).read().split() if os.path.exists(log) else []
        if "TIER 3" not in r.stdout:
            return "fullstop --dry did not finish: %s" % (r.stdout + r.stderr)[-300:]
        if calls.count(PROCESS_READER) != 1 or "basename" in calls:
            return "fullstop --dry ran %s %d time(s) and basename %d time(s)" % (
                PROCESS_READER, calls.count(PROCESS_READER), calls.count("basename"))
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


@check("verdictwatch reports a verdict appended to a slot log it has already seen, once",
       "it never recorded the offset of a log it saw for the first time, so it reported nothing, and each "
       "pass spawned four processes per slot log: 18 s of every 60 s cycle")
def _verdictwatch_reports():
    import shutil
    import subprocess
    sp = tempfile.mkdtemp(prefix="vw_")
    try:
        os.makedirs(os.path.join(sp, "wlog"))
        log = os.path.join(sp, "wlog", "pull_main_s1.log")
        with open(log, "w", newline="\n") as fh:
            fh.write("10:00 s1 MATCH 02000000 old\n")
        sh, env = _kp.bash()
        env = dict(env, DQIX_STATE=sp, DQIX_NO_FRESHNESS="1")

        def once():
            return subprocess.run([sh, f"{KIT}/verdictwatch.sh", "--once"], capture_output=True, text=True,
                                  env=env, timeout=120).stdout.splitlines()
        first = once()
        with open(log, "a", newline="\n") as fh:
            fh.write("10:01 s1 miss 02000004 bytediff 4\nnoise\n")
        second, third = once(), once()
    except subprocess.TimeoutExpired:
        return "verdictwatch --once did not return"
    finally:
        shutil.rmtree(sp, ignore_errors=True)
    if first or third or second != ["pull_main_s1 10:01 s1 miss 02000004 bytediff 4"]:
        return "verdictwatch passes printed %r, %r, %r" % (first, second, third)
    return None


@check("a health.sh cycle reads the process table once and stats its logs in one call",
       "each cycle ran four PowerShell process queries and a subshell plus stat per slot log: 8-10 s of "
       "every 120 s")
def _health_one_snapshot():
    import shutil
    import subprocess
    sp = tempfile.mkdtemp(prefix="hl_")
    d = tempfile.mkdtemp(prefix="hlbin_")
    try:
        os.makedirs(os.path.join(sp, "wlog"))
        for i in range(6):
            open(os.path.join(sp, "wlog", "pull_main_s%d.log" % i), "w").write("10:00 s%d MATCH 02000000\n" % i)
        log = os.path.join(d, "calls.log").replace("\\", "/")
        with open(os.path.join(d, PROCESS_READER), "w", newline="\n") as fh:
            fh.write("#!/bin/sh\necho %s >> '%s'\n" % (PROCESS_READER, log))
        os.chmod(fh.name, 0o755)
        with open(os.path.join(d, "stat"), "w", newline="\n") as fh:
            fh.write("#!/bin/sh\necho stat >> '%s'\nexec /usr/bin/stat \"$@\"\n" % log)
        os.chmod(fh.name, 0o755)
        sh, env = _kp.bash()
        env = dict(env, PATH=d + os.pathsep + env["PATH"], DQIX_STATE=sp, DQIX_NO_FRESHNESS="1")
        r = subprocess.run([sh, f"{KIT}/health.sh", "--once"], capture_output=True, text=True, env=env, timeout=300)
        calls = open(log).read().split() if os.path.exists(log) else []
    except subprocess.TimeoutExpired:
        return "health.sh --once did not return"
    finally:
        shutil.rmtree(sp, ignore_errors=True)
        shutil.rmtree(d, ignore_errors=True)
    if "ALERT driver" not in r.stdout:
        return "health.sh --once did not report the missing dispatcher: %r" % (r.stdout + r.stderr)[-300:]
    if calls.count(PROCESS_READER) != 1 or calls.count("stat") != 1:
        return "one health cycle ran %s %d time(s) and stat %d time(s)" % (
            PROCESS_READER, calls.count(PROCESS_READER), calls.count("stat"))
    return None


@check("health.sh off Windows does not count its own awk as a live pull_worker",
       "the awk counting the `ps` snapshot ran beside ps, so its own program text (pull_worker) was in "
       "the snapshot: PULLW was never 0 and the 'dispatcher up, ZERO workers' alert could not fire")
def _health_no_self_count():
    import shutil
    import subprocess
    if os.name == "nt":
        return None
    real = shutil.which("ps")
    sp = tempfile.mkdtemp(prefix="hs_")
    d = tempfile.mkdtemp(prefix="hsbin_")
    try:
        os.makedirs(os.path.join(sp, "wlog"))
        with open(os.path.join(sp, "wlog", ".zero_workers_since"), "w") as fh:
            fh.write("0\n")
        with open(os.path.join(d, "ps"), "w", newline="\n") as fh:
            fh.write("#!/bin/sh\nsleep 0.2\n'%s' \"$@\" | grep -E '^ *[0-9]+ +[0-9]+ +([^ ]*/)?awk '\n" % real)
        os.chmod(fh.name, 0o755)
        sh, env = _kp.bash()
        env = dict(env, PATH=d + os.pathsep + env["PATH"], DQIX_STATE=sp, DQIX_NO_FRESHNESS="1")
        out = subprocess.run([sh, f"{KIT}/health.sh", "--once"], capture_output=True, text=True, env=env,
                             timeout=300).stdout
    except subprocess.TimeoutExpired:
        return "health.sh --once did not return"
    finally:
        shutil.rmtree(sp, ignore_errors=True)
        shutil.rmtree(d, ignore_errors=True)
    if "ALERT idle" not in out:
        return "no idle alert with no pull_worker alive: %r" % out[-300:]
    return None


@check("mechclean verify compiles each unchanged original once per process and builds the include graph once",
       "addrname and the header pass call verify in a loop, and every call recompiled every original and "
       "re-read every include")
def _mechclean_verify_cached():
    import shutil
    M = load("mechclean")
    compiled, scanned = [], []
    real_resolved = M.resolved

    def fake_signature(text, path, region, include=None, deps=None):
        compiled.append((include, region))
        return [(), (".text", text.strip().encode())]

    def counted(rel, text, headers):
        scanned.append(rel)
        return real_resolved(rel, text, headers)
    M.signature, M.resolved = fake_signature, counted
    original = {"include/a.h": "struct A { int x; };\n", "src/a.cpp": '#include "a.h"\nint a;\n',
                "src/b.cpp": "int b;\n"}
    new = {"include/a.h": "struct A { int x; };\n\n"}
    work = tempfile.mkdtemp(prefix="mcv_")
    try:
        runs = []
        for _ in range(2):
            compiled.clear()
            scanned.clear()
            bad, _seen = M.verify(original, new, {}, 2, work)
            runs.append((bad, sum(1 for inc, _r in compiled if inc == f"{M.REPO}/include"), len(scanned)))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if runs[0][0] or runs[1][0]:
        return "verify reported %s for an unchanged unit" % (runs[0][0] or runs[1][0])
    if runs[0][1] != 1 or runs[1][1] != 0:
        return "the original src/a.cpp was compiled %d then %d time(s)" % (runs[0][1], runs[1][1])
    if runs[1][2]:
        return "the second verify re-read %d include list(s)" % runs[1][2]
    return None


@check("mechclean verify recompiles a unit only when its text or a header it read changed",
       "the addrname and header-pass loops call verify again after dropping renames, and every call "
       "recompiled every affected unit although half of them read no header the drop changed")
def _mechclean_verify_reuses_units():
    import shutil
    M = load("mechclean")
    real, compiled = M.signature, []

    def counted(text, path, region, include=None, deps=None):
        if include != f"{M.REPO}/include":
            compiled.append(os.path.basename(path))
        return real(text, path, region, include, deps)
    M.signature = counted
    head = open(f"{M.REPO}/include/globaldefs.h", encoding="utf-8").read()
    original = {"include/globaldefs.h": head,
                "src/x.cpp": '#include <globaldefs.h>\nextern "C" int X(int a) { return a + 1; }\n',
                "src/y.cpp": '#include <globaldefs.h>\nextern "C" int Y(int a) { return a + 2; }\n'}
    edited = {"include/globaldefs.h": head + "\n"}
    calls = [edited, edited, {**edited, "src/y.cpp": original["src/y.cpp"] + "\n"},
             {"include/globaldefs.h": head + "\n\n"}]
    want = [["src_x.cpp", "src_y.cpp"], [], ["src_y.cpp"], ["src_x.cpp", "src_y.cpp"]]
    work = tempfile.mkdtemp(prefix="mcr_", dir=f"{SP}/handwork")
    try:
        got = []
        for new in calls:
            compiled.clear()
            bad, _seen = M.verify(original, new, {}, 2, work)
            if bad:
                return "verify reported %s for a blank line" % bad
            got.append(sorted(compiled))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if got != want:
        return "units compiled per call %s, want %s" % (got, want)
    return None


@check("mechclean verify answers yes/no at the first unit that differs",
       "addrname --remangle asks verify only whether one symbol's rename breaks anything, and verify "
       "compiled every unit the rename reached before answering")
def _mechclean_verify_first():
    import shutil
    M = load("mechclean")
    calls = []

    def fake_signature(text, path, region, include=None, deps=None):
        calls.append(include)
        return [(), (".text", (text + ("" if include == f"{M.REPO}/include" else "!")).encode())]
    M.signature = fake_signature
    original = {"src/u%d.cpp" % i: "int u%d;\n" % i for i in range(6)}
    new = {rel: text + "\n" for rel, text in original.items()}
    work = tempfile.mkdtemp(prefix="mcf_")
    try:
        every, _seen = M.verify(original, new, {}, 1, work)
        calls.clear()
        first, _seen = M.verify(original, new, {}, 1, work, True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if len(every) != 6:
        return "a full verify reported %d of 6 differing units" % len(every)
    if len(first) != 1 or first[0] not in every:
        return "a yes/no verify reported %r" % first
    if len(calls) > 2:
        return "a yes/no verify compiled %d time(s) after the first difference" % (len(calls) - 1)
    return None


@check("elfobj reads an mwcc object exactly as pyelftools does",
       "wgate, wdiff and mechclean.verify parse every object with elfobj, so a field it decoded "
       "differently from pyelftools would change a verdict with no compile changing")
def _elfobj_matches_pyelftools():
    import io
    import elfobj
    text = ('struct Vec3 { int x, y, z; ~Vec3() {} };\nextern "C" void Use(void*);\n'
            'extern char data_0201aaaa[];\nstatic int s_bss;\nint g_data = 3;\nconst char* g_str = "abc";\n'
            'extern "C" char* F(char* p) { Vec3 v = *(Vec3*)(p + 8); Use(p); s_bss++;\n'
            '    return data_0201aaaa + 5 + g_data + s_bss; }\n')
    full = _compile_elf(text, _kp.REPO)
    if isinstance(full, str):
        return full
    mini = elfobj.ELFFile(io.BytesIO(full.stream.getvalue()))
    if not isinstance(mini, elfobj._Elf):
        return "elfobj handed an mwcc object to pyelftools"

    def dump(elf):
        out = []
        for i, sec in enumerate(elf.iter_sections()):
            row = [i, sec.name, {k: sec.header[k] for k in elfobj.HEADER_KEYS}, sec.data(),
                   hasattr(sec, "iter_relocations")]
            if hasattr(sec, "iter_symbols"):
                row.append([(s.name, s["st_value"], s["st_size"], s["st_info"]["bind"], s["st_info"]["type"],
                             s["st_shndx"]) for s in sec.iter_symbols()])
            if hasattr(sec, "iter_relocations"):
                row.append([(r["r_offset"], r["r_info_sym"], r["r_info_type"], r.is_RELA(),
                             r["r_addend"] if r.is_RELA() else None) for r in sec.iter_relocations()])
            out.append(row)
        names = sorted({s.name for s in elf.iter_sections()})
        return out + [[(n, elf.get_section_by_name(n)["sh_offset"]) for n in names]]
    want, got = dump(full), dump(mini)
    for a, b in zip(want, got):
        if a != b:
            return "pyelftools %s, elfobj %s" % (str(a)[:160], str(b)[:160])
    if len(want) != len(got):
        return "pyelftools saw %d sections, elfobj %d" % (len(want), len(got))
    return None


@check("plausible caches game_types by header and symbols.txt stamps and recomputes when one changes",
       "every plausible.py and cleancheck.py process re-read and stripped every header to answer "
       "TYPE-REDEFINED, 90 ms each")
def _game_types_cache():
    import json as _json
    P = load("plausible")
    old = _kp.REPO, _kp.SP
    with tempfile.TemporaryDirectory() as d:
        repo, sp = os.path.join(d, "repo"), os.path.join(d, "sp")
        os.makedirs(os.path.join(repo, "include"))
        os.makedirs(os.path.join(repo, "config", "usa", "arm9"))
        with open(os.path.join(repo, "config", "usa", "arm9", "symbols.txt"), "w") as fh:
            fh.write("_ZN3Foo3GetEv kind:function(arm,size=0x4) addr:0x02000000\n"
                     "_ZN3Bar3GetEv kind:function(arm,size=0x4) addr:0x02000004\n")
        header = os.path.join(repo, "include", "a.h")
        with open(header, "w") as fh:
            fh.write("struct Foo { int x; };\n")
        _kp.REPO, _kp.SP = repo, sp
        try:
            P.GAME_TYPES = None
            first = set(P.game_types())
            cache = os.path.join(sp, "wlog", "game_types.json")
            saved = _json.load(open(cache, encoding="utf-8"))
            saved["types"] = ["Cached"]
            with open(cache, "w", encoding="utf-8") as fh:
                _json.dump(saved, fh)
            P.GAME_TYPES = None
            second = set(P.game_types())
            with open(header, "w") as fh:
                fh.write("struct Bar { int y; long z; };\n")
            P.GAME_TYPES = None
            third = set(P.game_types())
        finally:
            _kp.REPO, _kp.SP = old
            P.GAME_TYPES = None
    if first != {"Foo"}:
        return "computed %s, want {'Foo'}" % first
    if second != {"Cached"}:
        return "an unchanged tree recomputed instead of reading the cache (%s)" % second
    if third != {"Bar"}:
        return "a changed header still answered %s" % third
    return None


@check("gate history keeps every row when one process gates in parallel",
       "nearmiss, recipe_select and evo_score gate attempts on threads, and unlocked appends to one "
       "wlog/gates file lost 665 of 20000 rows")
def _gatelog_parallel_rows():
    from concurrent.futures import ThreadPoolExecutor
    G = load("gatelog")
    with tempfile.TemporaryDirectory() as d:
        G.SP = d
        with ThreadPoolExecutor(16) as pool:
            list(pool.map(lambda i: G.record("main", "02000000", "-", "SHAPE", i, "f%d.cpp" % i), range(20000)))
        rows = G.read("main", "02000000")
    if len(rows) != 20000 or sorted(int(r[3]) for r in rows) != list(range(20000)):
        return "%d of 20000 rows survived" % len(rows)
    return None


@check("wgate.gate in-process prints what the wgate.py command prints",
       "nearmiss, recipe_select, evo_score and mechclean gate in-process; a gate() that drifted from "
       "the command would rank, score and accept candidates on verdicts no worker sees")
def _wgate_inprocess_matches_cli():
    import subprocess
    W = load("wgate")
    landed, open_addr = _main_function(True), _main_function(False)
    if not landed or not open_addr:
        return "no landed and unlanded main function to gate"
    cases = [(landed, "int x;\n", {}), (open_addr, 'extern "C" ARM void func_%s() {}\n' % open_addr, {}),
             (open_addr, "this is not C\n", {}), ("02000001", "int x;\n", {"WGATE_ALLOW_COMMITTED": "1"})]
    with tempfile.TemporaryDirectory(dir=f"{SP}/handwork", ignore_cleanup_errors=True) as d:
        for addr, text, env in cases:
            src = os.path.join(d, "t_%s.cpp" % addr).replace("\\", "/")
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            r = subprocess.run([sys.executable, f"{KIT}/wgate.py", "main", addr, src], capture_output=True,
                               text=True, env=dict(os.environ, DQIX_NO_FRESHNESS="1", **env))
            out = []
            rc = W.gate("main", addr, src, out=out, env=dict(os.environ, **env))
            got = "".join(line + "\n" for line in out)
            if (rc, got) != (r.returncode, r.stdout):
                return "%s: command exit %d %r, gate() %d %r" % (addr, r.returncode, r.stdout[-120:], rc, got[-120:])
    return None


@check("library-range addresses and library paths are gated on their library build",
       "every function was compiled with the game's build, so NitroSDK and MSL code built at -O4,p "
       "could never match")
def _sdk_build_routing():
    B = load("buildcfg")
    if not {"sdk", "msl", "runtime"} <= set(B.LIBRARIES):
        return "the decomp's configure.py defines no sdk/msl/runtime LIBRARY_BUILDS"
    if B.REGION != "usa":
        return None
    cases = [(("main", "020d3160"), ["sdk"]), (("main", "02000c9c"), ["game"]),
             (("main", "020aeec8"), ["sdk", "game"]), (("main", "020d6bac"), ["sdk", "game"]),
             (("main", "020d6c0c"), ["game"]), (("main", "020d3160", "D:/r/src/Combat/Main/a.cpp"), ["sdk"]),
             (("main", "02000c9c", "D:/r/src/NitroSDK/Main/a.cpp"), ["sdk"]),
             (("main", "02000c9c", "src\\NitroSDK\\a.cpp"), ["sdk"]), (("031", "022192c0"), ["network"]),
             (("031", "02242c54"), ["network", "game"]), (("031", "0224599c"), ["game"]),
             (("main", "020d39dc"), ["game"]), (("main", "020d3d90"), ["game"]), (("main", "020d3dcc"), ["sdk"]),
             (("main", "020042a8"), ["msl"]), (("main", "0200df80"), ["runtime"]),
             (("main", "0200f398"), ["game"]), (("main", "02000c9c", "src/MSL/Main/a.cpp"), ["msl"])]
    for args, want in cases:
        if B.builds_for(*args) != want:
            return "builds_for%r = %r, want %r" % (args, B.builds_for(*args), want)
    if B.lib_dir("main", "sdk") != "src/NitroSDK/Main" or B.lib_dirs("031") != ["src/NetworkLib/Overlay_31"]:
        return "lib dirs: %r %r" % (B.lib_dir("main", "sdk"), B.lib_dirs("031"))
    for name, (_root, ver, flags) in B.LIBRARIES.items():
        if B.build_flags(name) != B.FLAGS + flags or not B.build_cc(name).endswith(ver + "/mwccarm.exe"):
            return "build %s: %r %r" % (name, B.build_cc(name), B.build_flags(name)[-3:])
    if B.build_flags("game") != B.FLAGS or B.build_cc("game") != B.CC:
        return "game build"


@check("ov_recover places an SDK-build match under src/NitroSDK and a game-build one in the module dir",
       "every match was written to the module's own directory, which the decomp compiles with the "
       "game build, so an SDK-build match failed the wave's ninja check")
def _recover_places_sdk():
    got = _run_place({})
    if got != ["game/func_02000c9c.cpp", "sdk/func_020d3160.cpp"]:
        return "placed %r" % got


def _run_place(cand_ext):
    import ast
    src = open(f"{KIT}/ov_recover.py", encoding="utf-8").read()
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "place")
    with tempfile.TemporaryDirectory() as root:
        game, sdk = (os.path.join(root, d).replace("\\", "/") for d in ("game", "sdk"))
        text = {a: '// USA: func_%s\nextern "C" ARM void func_%s() {}\n' % (a, a) for a in ("020d3160", "02000c9c")}
        from types import SimpleNamespace
        ns = {"re": re, "os": os, "cands": text, "_build": {"020d3160": "sdk", "02000c9c": "game"},
              "cand_ext": cand_ext,
              "buildcfg": SimpleNamespace(lib_dir=lambda mod, b: {"sdk": sdk}[b]), "MOD": "main",
              "SRCDIR": game, "TAG": "USA", "TAGPRE": "func_", "_FOREIGN_STEMS": set(),
              "tracked": lambda p: False, "sanitize": lambda t, a: ("func_" + a, t),
              "ASMPAT": re.compile("(?!)"), "ASM_ALLOW": set(), "carry_cc_override": lambda a, p: None}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "place", "exec"), ns)
        ns["place"](["020d3160", "02000c9c"])
        return sorted(os.path.relpath(os.path.join(d, f), root).replace("\\", "/")
                      for d, _s, fs in os.walk(root) for f in fs)


@check("a .c source compiles as C in the gate, the sweep and the classifier, and the wave places it as .c",
       "every gate tool compiled a source as C++ whatever its extension, so __minus_dec 02009edc, whose "
       "canonical MSL C block-copies a nested struct where C++ copies it member by member, gated OVERGEN "
       "and could only land behind an invented union")
def _c_sources_compile_as_c():
    import contextlib
    import io
    import subprocess
    addr = "02009edc"
    c_text = open(f"{KIT}/regress_fixtures/MinusDec_02009edc.c", encoding="utf-8").read()
    cpp_text = c_text.replace("ARM void func_", 'extern "C" ARM void func_')
    with tempfile.TemporaryDirectory(dir=f"{SP}/handwork", ignore_cleanup_errors=True) as d:
        verdicts = {}
        for ext, text in ((".c", c_text), (".cpp", cpp_text)):
            src = os.path.join(d, "t" + ext)
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            r = subprocess.run([sys.executable, f"{KIT}/wgate.py", "main", addr, src], capture_output=True,
                               text=True, cwd=_kp.REPO, env={**os.environ, "WGATE_ALLOW_COMMITTED": "1",
                                                             "WGATE_SESSION": "regress"})
            verdicts[ext] = (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]
        if verdicts[".c"] != ["MATCH"] or verdicts[".cpp"] == ["MATCH"]:
            return "wgate on 02009edc: .c %r, .cpp %r" % (verdicts[".c"], verdicts[".cpp"])
        C = load("colorsweep")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = {ext: C.sweep(None, 1, "main", addr, os.path.join(d, "t" + ext), 0, 1, False)
                  for ext in (".c", ".cpp")}
        C._drop_rundir()
        if rc[".c"] != 0 or rc[".cpp"] == 0:
            return "colorsweep base on 02009edc: .c exit %d, .cpp exit %d" % (rc[".c"], rc[".cpp"])
    cls = load("classify")
    got = {ext: cls.classify("main", {addr: text}, names={addr: "t" + ext}).get(addr)
           for ext, text in ((".c", c_text), (".cpp", cpp_text))}
    if got[".c"] != "TRUSTED" or got[".cpp"] == "TRUSTED":
        return "classify on 02009edc: %r" % got
    placed = _run_place({"02000c9c": ".c"})
    if placed != ["game/func_02000c9c.c", "sdk/func_020d3160.cpp"]:
        return "place() with a .c candidate wrote %r" % placed
    return None


@check("the gate and classify match OS_VSNPrintf on the SDK build only, and name that build",
       "main 020d3160 is byte-exact with NitroSDK's own os_printf.c only on mwcc 2.0/sp1p2 -O4,p; "
       "gated on the game build it overgenerates by 128 bytes")
def _sdk_build_matches():
    W = load("wgate")
    if "sdk" not in W.buildcfg.LIBRARIES or W.buildcfg.REGION != "usa":
        return None if "sdk" in W.buildcfg.LIBRARIES else "the decomp's configure.py defines no SDK build"
    src = f"{KIT}/regress_fixtures/OS_VSNPrintf_020d3160.cpp"
    env = dict(os.environ, WGATE_ALLOW_COMMITTED="1")
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    with tempfile.TemporaryDirectory(dir=f"{SP}/handwork", ignore_cleanup_errors=True) as d:
        saved = _kp.SP, W.gatelog.SP
        _kp.SP = W.gatelog.SP = d
        try:
            out = []
            if W.gate("main", "020d3160", src, out=out, env=env) != 0 or out != ["MATCH"]:
                return "SDK build did not match, or MATCH is not the gate's only line: %r" % out[-3:]
            out = []
            if W.gate("main", "020d3160", src, out=out, env=dict(env, WGATE_FLAGS="-O2")) == 0:
                return "the game build matched too, so the case proves nothing"
            bad = os.path.join(d, "edge_bad.cpp")
            with open(bad, "w", encoding="utf-8", newline="\n") as fh:
                fh.write('#include <globaldefs.h>\n\nextern "C" ARM void func_020aeec8() {}\n')
            out = []
            W.gate("main", "020aeec8", bad, out=out, env=env)
            if not (out and out[0].startswith("RESIDUE ") and out[1].startswith("BUILDS sdk=")
                    and not out[-1].startswith("BUILDS")):
                return "a two-build failure must read RESIDUE, BUILDS, then the message: %r" % out[:3]
            C = load("classify")
            C.SP = d
            builds = {}
            verdict = C.classify("main", {"020d3160": open(src, encoding="utf-8").read()}, builds=builds)
            if verdict.get("020d3160") not in ("TRUSTED", "RISKY") or builds.get("020d3160") != "sdk":
                return "classify: %r %r" % (verdict, builds)
        finally:
            _kp.SP, W.gatelog.SP = saved


@check("nearmiss gates a list of candidates in parallel and answers in their order",
       "recipe_select gated each earlier attempt one process at a time, 45-90 s for an address with a "
       "hundred attempts")
def _nearmiss_parallel_gaps():
    N = load("nearmiss")
    seen = []

    class FakeGate:
        @staticmethod
        def gate(mod, addr, src, sec=None, out=None, env=None):
            seen.append(src)
            n = int(open(src).read())
            out.append("MATCH" if n == 0 else "RESIDUE SHAPE %d x" % n)
            return 0 if n == 0 else 1
    real = sys.modules.get("wgate")
    sys.modules["wgate"] = FakeGate
    try:
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for i, n in enumerate([7, 0, 3, 12, 5, 9, 1, 4, 8, 2, 6, 11]):
                p = os.path.join(d, "a%02d.cpp" % i)
                with open(p, "w") as fh:
                    fh.write(str(n))
                paths.append(p)
            cache = {}
            got = N.verified_gaps("main", "02000000", paths, cache)
            again = N.verified_gaps("main", "02000000", paths, cache)
    finally:
        if real is None:
            sys.modules.pop("wgate", None)
        else:
            sys.modules["wgate"] = real
    if got != [7, 0, 3, 12, 5, 9, 1, 4, 8, 2, 6, 11] or again != got:
        return "gaps %s then %s" % (got, again)
    if len(seen) != 12:
        return "%d gates for 12 files, the second pass should hit the cache" % len(seen)
    return None


@check("mechclean reads committed texts and landed rows from git in batches, and an edited file from disk",
       "tree_texts opened 13.5k working-tree files (4.1 s) and each queue row cost two git processes")
def _mechclean_batched_reads():
    import builtins
    import shutil
    import subprocess
    M = load("mechclean")
    repo = tempfile.mkdtemp(prefix="mcr_")
    try:
        def git(*a):
            return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-q", "-b", "trunk")
        os.makedirs(os.path.join(repo, "src"))
        for name in ("a", "b", "c"):
            with open(os.path.join(repo, "src", name + ".cpp"), "w", newline="\n") as fh:
                fh.write("int %s;\n" % name)
        git("add", "-A")
        git("commit", "-q", "-m", "x")
        git("update-ref", "refs/remotes/origin/decomp-matching", "HEAD")
        with open(os.path.join(repo, "src", "c.cpp"), "w", newline="\n") as fh:
            fh.write("int edited;\n")
        M.REPO = repo.replace("\\", "/")
        opened, runs = [], []
        real_run = subprocess.run

        def guarded(path, *a, **kw):
            opened.append(os.path.basename(str(path)))
            return builtins.open(path, *a, **kw)

        def counted(*a, **kw):
            runs.append(a[0] if a else kw.get("args"))
            return real_run(*a, **kw)
        M.open = guarded
        subprocess.run = counted
        try:
            _blobs, texts = M.tree_texts(roots=("src",))
            runs.clear()
            M.fetch_landed(["src/a.cpp", "src/b.cpp", "src/c.cpp"])
            fetched, got = len(runs), {r: M.landed_blob(r) for r in ("src/a.cpp", "src/c.cpp")}
        finally:
            subprocess.run = real_run
        if texts != {"src/a.cpp": "int a;\n", "src/b.cpp": "int b;\n", "src/c.cpp": "int edited;\n"}:
            return "tree_texts read %r" % texts
        if opened != ["c.cpp"]:
            return "tree_texts opened %s from the working tree; only the edited c.cpp should be" % opened
        if fetched > 2:
            return "fetch_landed ran %d git processes for three rows" % fetched
        if got["src/a.cpp"] != (git("rev-parse", "origin/decomp-matching:src/a.cpp"), "int a;\n") or \
                got["src/c.cpp"][1] != "int c;\n":
            return "landed rows read %r" % got
        return None
    finally:
        shutil.rmtree(repo, ignore_errors=True)


@check("landpr, rename_symbols and relink_undefined read a revision's files in one git process",
       "each ran `git show` once per file per revision: 35 symbols.txt files twice per merge repair, and "
       "four per conflicted delinks.txt")
def _revision_reads_batched():
    import ast
    import shutil
    import subprocess
    root = tempfile.mkdtemp(prefix="rv_")
    try:
        def git(*args):
            return subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-q", "-b", "main")
        for i, cfg in enumerate(("config/usa/arm9", "config/usa/arm9/overlays/ov001", "config/usa/arm9/overlays/ov002")):
            os.makedirs(os.path.join(root, cfg))
            with open(os.path.join(root, cfg, "symbols.txt"), "w", newline="\n") as fh:
                fh.write("Name%d kind:function(arm,size=0x4) addr:0x0200000%d\n" % (i, i))
        with open(os.path.join(root, "delinks.txt"), "w", newline="\n") as fh:
            fh.write("src/A.cpp:\n    complete\n    .text start:0x0 end:0x4\n")
        git("add", "-A")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        git("checkout", "-qb", "pr")
        for name, branch in (("2", "pr"), ("1", "main")):
            git("checkout", "-q", branch)
            with open(os.path.join(root, "delinks.txt"), "a", newline="\n") as fh:
                fh.write("\nsrc/%s.cpp:\n    complete\n    .text start:0x%s end:0x%s4\n" % (name, name, name))
            git("commit", "-qam", name)
        pr = git("rev-parse", "pr")
        git("merge", "--no-ff", "-m", "Merge #5", pr)
        lp = load("landpr")
        calls, real = [], lp.git
        lp.git = lambda tree, *a: calls.append(a[0]) or real(tree, *a)
        if not lp.keep_both_delinks(root, pr) or "show" in calls:
            return "keep_both_delinks returned without merging, or ran git show (%s)" % calls
        spawned, real_run = [], subprocess.run
        subprocess.run = lambda *a, **kw: spawned.append(a[0] if a else kw.get("args")) or real_run(*a, **kw)
        cwd = os.getcwd()
        os.chdir(root)
        try:
            for script, fn, helpers in (("relink_undefined", "load_symbols", ["symbol_paths"]),
                                        ("rename_symbols", "table", ["symbol_files"])):
                tree = ast.parse(open(f"{KIT}/{script}.py", encoding="utf-8").read())
                nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in [fn] + helpers]
                ns = dict(os=os, re=re, subprocess=subprocess, REPO=root, ADDR=re.compile(r"addr:0x([0-9a-fA-F]+)"),
                          gitread=load("gitread"))
                exec(compile(ast.Module(body=nodes, type_ignores=[]), script, "exec"), ns)
                spawned.clear()
                got = ns[fn](base)
                shows = [c for c in spawned if "show" in c]
                if got != {0x02000000: "Name0", 0x02000001: "Name1", 0x02000002: "Name2"} or shows:
                    return "%s.%s read %r with %d git show call(s)" % (script, fn, got, len(shows))
        finally:
            os.chdir(cwd)
            subprocess.run = real_run
        return None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _script_defs(path, *names, **env):
    import hashlib
    src = open(path, encoding="utf-8").read()
    ns = dict(env, re=re, os=os, sys=sys, hashlib=hashlib)
    for name in names:
        m = re.search(r'(?ms)^def %s\(.*?(?=^\S|\Z)' % re.escape(name), src)
        if not m:
            return None
        exec(m.group(0), ns)
    return ns


@check("repairsweep routes on every line of wgate's verdict, not on its first",
       "wgate prints `RESIDUE <CLASS> ...` before the BYTEDIFF or UNDEF-SYM line, and repairsweep "
       "tested verdict.startswith(...): the UNDEF-SYM repairs never ran and no BYTEDIFF residue was "
       "colour-swept. The 557-copy pass of 10-14 swept SIZE verdicts only; its 7 REGPERM and 71 "
       "SCHED copies were never offered to colorsweep")
def _repairsweep_routes_on_lines():
    src = open(f"{KIT}/repairsweep.py", encoding="utf-8").read()
    if 'verdict.startswith("UNDEF-SYM")' in src:
        return "an UNDEF-SYM repair still keys on the verdict's first line, the RESIDUE line"
    ns = _script_defs(f"{KIT}/repairsweep.py", "_says", "sweep_budget", COLORSWEEP_MAX_BYTES=24,
                      COLORSWEEP_BUDGET=150, COLORSWEEP_BUDGET_MAX=400)
    if not ns:
        return "repairsweep.py has no sweep_budget() deciding which verdicts are colour-swept"
    regperm = ("RESIDUE REGPERM 3 r0->r1\nHINT: scratch only\n"
               "BYTEDIFF: 3 bytes differ at ['0x2d', '0x31', '0x35'] (NOT byte-exact)")
    if ns["sweep_budget"](regperm, 0x100) != 150 + 0x100 // 8:
        return "a REGPERM 3 verdict on a 256-byte function is not swept with the size-scaled budget"
    big = ("RESIDUE LOOP-SHAPE 1292 1 branch target(s) differ, first at 0x358\n"
           "BYTEDIFF: 1292 bytes differ at ['0x0'] (NOT byte-exact)")
    if ns["sweep_budget"](big, 0x800) is not None:
        return "a 1292-byte LOOP-SHAPE residue on a 2KB function is swept"
    size = ("RESIDUE UNDERGEN 4 0x11c vs slot 0x120\n"
            "SIZE/OVERGEN: 1 .text total=0x11c slot=0x120 (define ONLY this func)")
    if ns["sweep_budget"](size, 0) != 150 + 0x120 // 8:
        return "a near-size UNDERGEN 4 verdict is not swept"
    if not ns["_says"]("RESIDUE UNDEF-SYM 1 f\nUNDEF-SYM: ['f'] -- these callee symbols", "UNDEF-SYM"):
        return "_says() misses the UNDEF-SYM line behind the RESIDUE line"
    return None


@check("repairsweep colour-sweeps one copy per address and never re-sweeps an unchanged source",
       "every parked copy got its own colorsweep of up to 400 compiles and four flag-set gates, and "
       "every pass redid both on the same unchanged files: 557 copies of 63 addresses, 4h38m per "
       "pass, 0 hits")
def _repairsweep_sweeps_once():
    import shutil
    src = open(f"{KIT}/repairsweep.py", encoding="utf-8").read()
    ns = _script_defs(f"{KIT}/repairsweep.py", "rank", "sweep_picks", "cache_key", "cached_sweep",
                      "cached_lead")
    if not ns:
        return "repairsweep.py has no sweep_picks()/cache_key()/cached_sweep()/cached_lead()"
    if ("if picks.get(addr) == k:" not in src or "cached_sweep(SWEEPCACHE" not in src
            or "cached_lead(SWEEPCACHE" not in src):
        return "the pass does not route its colour and flag sweeps through the per-source cache"
    near = "RESIDUE UNDERGEN 4 0x11c vs slot 0x120\nSIZE/OVERGEN: 1 .text total=0x11c slot=0x120"
    regperm = "RESIDUE REGPERM 3 r0->r1\nBYTEDIFF: 3 bytes differ at ['0x2d']"
    sched = "RESIDUE SCHED 9 x\nBYTEDIFF: 9 bytes differ at ['0x10']"
    picks = ns["sweep_picks"]([("a", sched, 150), ("a", regperm, 150), ("a", near, 150),
                               ("b", regperm, None), ("c", sched, 150), ("c", sched, 150)])
    if picks != {"a": 1, "c": 4}:
        return "sweep_picks chose %r, want the best sweepable copy per address {'a': 1, 'c': 4}" % picks
    key = ns["cache_key"]
    base = key("fp", b"int f;", "main", "02000000", 150, 3, regperm)
    for other in (key("fp2", b"int f;", "main", "02000000", 150, 3, regperm),
                  key("fp", b"int f;", "main", "02000000", 151, 3, regperm),
                  key("fp", b"int f;", "main", "02000000", 150, 3, sched),
                  key("fp", b"int g;", "main", "02000000", 150, 3, regperm)):
        if other == base:
            return "cache_key ignores the kit, the budget, the verdict or the source"
    d = tempfile.mkdtemp(prefix="sweepcache_")
    try:
        work, cache = os.path.join(d, "w.cpp"), os.path.join(d, "cache")
        before, after = b"// USA: func_02000000\nint f;\n", b"// USA: func_02000000\nint g;\n"
        calls = []

        def sweep():
            calls.append(1)
            open(work, "wb").write(after)
            return True

        open(work, "wb").write(before)
        if ns["cached_sweep"](cache, base, work, sweep) is not False:
            return "a first sweep did not run colorsweep"
        open(work, "wb").write(before)
        if ns["cached_sweep"](cache, base, work, sweep) is not True or len(calls) != 1:
            return "an unchanged source was swept again instead of replaying the cached result"
        if open(work, "rb").read() != after:
            return "a cache hit did not restore the swept source"
        for name in os.listdir(cache):
            if name.endswith(".cpp") or b"// USA: func_" in open(os.path.join(cache, name), "rb").read():
                return "the cache holds a taggable source ov_recover.gather() could pick up: %s" % name
        if ns["cached_sweep"](cache, "other", work, lambda: False) is not None or len(os.listdir(cache)) != 1:
            return "a colorsweep run that printed no RESULT was cached as finished"
        probes = []
        for _ in range(2):
            lead = ns["cached_lead"](cache, base, lambda: probes.append(1) or "-O4")
            if lead != "-O4":
                return "cached_lead returned %r, want the probed flag set" % lead
        if len(probes) != 1:
            return "the flag sets were re-gated on an unchanged source"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return None


if __name__ == "__main__":
    if "--shard" in sys.argv:
        run_shard([int(i) for i in sys.argv[sys.argv.index("--shard") + 1].split(",") if i])
        sys.exit(0)
    run_checks()
    slow = "--slow" in sys.argv
    nbad = run_functional() if slow else 0
    if slow and not nbad and not FAILED:
        # Record WHAT was proven, so selfcheck can refuse to go green when colorsweep, the differ
        # or the gate has changed since the last end-to-end run.
        with open(STAMP, "w", encoding="utf-8") as fh:
            fh.write(sweep_fingerprint())
    if not slow:
        print("(skipped %d end-to-end crack test(s); run with --slow after ANY colorsweep change)"
              % len(FUNCTIONAL))
    print(record(nbad))
    sys.exit(1 if (FAILED or nbad) else 0)
