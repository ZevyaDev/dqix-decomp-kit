#!/usr/bin/env python3
"""BEHAVIOUR tests for the gate. Reading a script proves nothing; this runs it.

    python pipetest.py [n]      n = how many committed functions to sample (default 6)

WHY THIS EXISTS. Every bug that reached a wave was invisible to a line-by-line review:

  * `wgate` never checked the symbol its object exports. There was no wrong line -- the check was
    absent, and you cannot read code that is not there.
  * `translate.py` names its output `Trans_<addr>`, which is correct in isolation and only wrong as
    a contract with symbols.txt, i.e. in a second file.
  * `ov_recover.sanitize` stripped `0x`-looking runs from identifiers, exactly as its comment said
    it would. The comment was wrong. Reading confirmed the code matched its intent, not that the
    intent was right.

The common factor is that reading verifies a file against itself. So this tests the pipeline the
only way that can fail honestly: feed it inputs whose correct verdict is known.

TWO DIRECTIONS, AND THE SECOND IS THE POINT. Known-good sources must gate MATCH -- that catches a
gate that rejects real work. Deliberately broken ones must gate with the SPECIFIC failure they
earn -- that catches a gate incapable of failing, which is how a silent hole survives for months.
A mutation that still passes is reported as a HOLE, because that is what it is.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
SRC = f"{REPO}/src/Combat/Main"


def gate_run(addr, path, state):
    return subprocess.run([sys.executable, f"{KIT}/wgate.py", "main", addr, path],
                          env={**os.environ, "DQIX_STATE": state, "WGATE_ALLOW_COMMITTED": "1"},
                          capture_output=True, text=True, cwd=REPO)


def gate(addr, path, state):
    """Last line of wgate for one candidate."""
    r = gate_run(addr, path, state)
    out = (r.stdout or r.stderr).strip().splitlines()
    return out[-1] if out else "(no output)"


def committed_samples(n):
    """Committed sources, which are matched by definition and must gate MATCH."""
    found = []
    for dirpath, _d, files in os.walk(SRC):
        for fn in sorted(files):
            if not fn.endswith(".cpp"):
                continue
            p = os.path.join(dirpath, fn)
            txt = open(p, encoding="utf-8", errors="ignore").read()
            m = re.search(r"// USA: func_([0-9a-fA-F]{8})", txt)
            if m and "asm" not in txt:
                found.append((m.group(1), p, txt))
            if len(found) >= n:
                return found
    return found


# Each mutation returns modified source, plus the failure token the gate MUST report. The point of
# a mutation is that it is genuinely wrong -- if the gate still says MATCH, the gate has a hole.
def mut_rename(txt):
    m = re.search(r"(\b(?:ARM|THUMB)\b[^\n;{]*?\b)(\w+)(\s*\()", txt)
    if not m:
        return None
    name = re.compile(rf"\b{re.escape(m.group(2))}\b")
    lines = [ln if ln.lstrip().startswith("//") else name.sub("RenamedByPipetest", ln) for ln in txt.split("\n")]
    return "\n".join(lines), "WRONG-SYMBOL"


def mut_body(txt):
    """Change real work, not a declaration: a returned constant alters the emitted bytes."""
    m = re.search(r"(?m)^(\s*return\s+)(\d+)(\s*;)", txt)
    if not m:
        return None
    v = str(int(m.group(2)) + 7)
    return txt[:m.start(2)] + v + txt[m.end(2):], "BYTEDIFF"


def mut_callee(txt, own_addr):
    """Point a CALL at a symbol that does not exist.

    It must be a genuine callee, never the function's own name: renaming the definition emits no
    undefined symbol at all, so the gate rightly says MATCH and the test would report a hole that
    is not there. That false positive is exactly the kind of claim this harness exists to prevent.
    """
    import buildcfg
    from elftools.elf.elffile import ELFFile
    with tempfile.TemporaryDirectory(prefix="callee_", dir=f"{SP}/handwork") as work:
        src, obj = os.path.join(work, "sample.cpp"), os.path.join(work, "sample.o")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(txt)
        r = subprocess.run(buildcfg.tool_command(buildcfg.cc_path(os.environ.get("MWCC")))
                           + list(buildcfg.FLAGS) + os.environ.get("WGATE_FLAGS", "").split()
                           + ["-c", src, "-o", obj], cwd=REPO, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"callee mutation fixture did not compile: {r.stdout}{r.stderr}")
        with open(obj, "rb") as fh:
            elf = ELFFile(fh)
            symtab = elf.get_section_by_name(".symtab")
            referenced = {symtab.get_symbol(rr["r_info_sym"]).name
                          for sec in elf.iter_sections() if hasattr(sec, "iter_relocations")
                          and elf.get_section(sec["sh_info"])["sh_flags"] & 4
                          for rr in sec.iter_relocations()
                          if symtab.get_symbol(rr["r_info_sym"])["st_shndx"] == "SHN_UNDEF"}
    for m in re.finditer(r"\b(func_[0-9a-fA-F]{8})\s*\(", txt):
        if m.group(1) != f"func_{own_addr.lower()}" and m.group(1) in referenced:
            return f"#define {m.group(1)} func_deadbeef\n" + txt, "UNDEF"
    return None


MUTATIONS = [("renamed definition", mut_rename),
             ("altered body", mut_body),
             ("nonexistent callee", mut_callee)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    samples = committed_samples(n)
    if not samples:
        sys.exit("no committed non-asm sources found to test against")
    passed = failed = holes = 0
    os.makedirs(f"{SP}/handwork", exist_ok=True)
    state = tempfile.mkdtemp(prefix="pipetest_", dir=f"{SP}/handwork")

    for addr, path, txt in samples:
        verdict = gate(addr, path, state)
        if verdict == "MATCH":
            passed += 1
            saved = os.path.join(state, "gated", "main", addr + ".cpp")
            if not os.path.isfile(saved) or open(saved, "rb").read() != open(path, "rb").read():
                failed += 1
                print(f"REGRESSION  {addr} exact external snapshot missing")
            else:
                passed += 1
        else:
            failed += 1
            print(f"REGRESSION  {addr} committed source no longer gates: {verdict[:80]}")

        for label, fn in MUTATIONS:
            made = fn(txt, addr) if fn is mut_callee else fn(txt)
            if not made:
                continue
            broken, want = made
            tmp = os.path.join(state, f"pipetest_{addr}.cpp")
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(broken)
            got = gate(addr, tmp, state)
            os.remove(tmp)
            if got == "MATCH":
                holes += 1
                print(f"HOLE        {addr} {label}: gate said MATCH for a source that is WRONG")
            elif want not in got:
                failed += 1
                print(f"MISDIAGNOSED {addr} {label}: wanted {want}, got {got[:70]}")
            else:
                passed += 1

    addr, path, _txt = samples[0]
    blocked = tempfile.mkdtemp(prefix="blocked_", dir=f"{SP}/handwork")
    os.makedirs(os.path.join(blocked, "gated", "main", addr + ".cpp"))
    r = gate_run(addr, path, blocked)
    if r.returncode == 0 or "PRESERVATION-FAILED" not in r.stdout or r.stdout.strip().endswith("MATCH"):
        failed += 1
        print(f"REGRESSION  snapshot failure was not rejected: {r.stdout[-160:]} {r.stderr[-160:]}")
    else:
        passed += 1
    parallel = tempfile.mkdtemp(prefix="parallel_", dir=f"{SP}/handwork")
    def concurrent_probe(job):
        kind, probe = job
        probe_addr, probe_path, _ = probe
        if kind == "gate":
            return gate_run(probe_addr, probe_path, parallel)
        return subprocess.run([sys.executable, f"{KIT}/wdiff.py", "main", probe_addr, probe_path],
                              env={**os.environ, "DQIX_STATE": parallel},
                              capture_output=True, text=True, cwd=REPO)
    probes = samples[:2]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(concurrent_probe, [(kind, probe) for kind in ("gate", "diff") for probe in probes]))
    for r in results:
        if r.returncode != 0 or not r.stdout.strip().endswith("MATCH"):
            failed += 1
            print(f"REGRESSION  concurrent gate/diff: {r.stdout[-160:]} {r.stderr[-160:]}")
        else:
            passed += 1
    for probe_addr, probe_path, _ in probes:
        saved = os.path.join(parallel, "gated", "main", probe_addr + ".cpp")
        if not os.path.isfile(saved) or open(saved, "rb").read() != open(probe_path, "rb").read():
            failed += 1
            print(f"REGRESSION  {probe_addr} concurrent snapshot differs")
        else:
            passed += 1
    scratch = os.path.join(parallel, "handwork", "compile")
    if any(name.endswith(".o") for name in os.listdir(scratch)):
        failed += 1
        print("REGRESSION  concurrent gate/diff left compiler objects behind")
    else:
        passed += 1
    print(f"\n{passed} correct, {failed} wrong verdicts, {holes} gate holes "
          f"({len(samples)} committed functions x {len(MUTATIONS)} mutations)")
    return 1 if (failed or holes) else 0


if __name__ == "__main__":
    sys.exit(main())
