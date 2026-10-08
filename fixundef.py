"""Rewrite callee declarations that name a symbol the link cannot resolve.

wgate reports UNDEF-SYM when a candidate declares a callee under a name that is
not the one actually committed. The undefined symbol is what the compiler
emitted, so a C++ declaration arrives mangled (_Z38Name...) while the file
contains the plain identifier -- renaming the mangled string alone changes
nothing and loops forever. So: demangle to the source identifier, rename it to
the committed symbol, and declare it extern "C" so the exact symbol survives.

Usage: python fixundef.py <module> <addr> <file.cpp>
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import buildcfg
import os, re, subprocess, sys, glob

SP = _kp.SP
KIT = _kp.KIT
REPO = _kp.REPO
mod, addr, src = sys.argv[1], sys.argv[2], sys.argv[3]

names = {}
_symfiles = [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + \
            sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt"))
_texts = [open(p, encoding="utf-8", errors="ignore").read() for p in _symfiles]
# FUNCTIONS FIRST, so an address carrying both kinds resolves to the function.
for _kind in ("function", "data"):
    for txt_ in _texts:
        for m in re.finditer(r'^(\S+) kind:%s\([^)]*\) addr:0x([0-9a-fA-F]{8})' % _kind, txt_, re.M):
            names.setdefault(m.group(2).lower(), m.group(1))
# DATA COUNTS. Scanning only kind:function meant an undefined DATA name -- a worker writing
# `data_ov031_02249b54_arg` for the object committed as `data_ov031_02249b54` -- resolved to
# nothing, and the whole file parked as STUCK on a name whose address was right there in it.


def source_identifier(sym):
    """The identifier as written in C++ source: _Z<len><name>... -> <name>."""
    m = re.match(r'_Z(\d+)(.+)$', sym)
    return m.group(2)[:int(m.group(1))] if m else sym


def ensure_extern_c(txt, name):
    """Prefix the DECLARATION of `name` with extern "C".

    A prototype has a return type before the name; a call statement does not.
    Prefixing a call yields `extern "C" f(x);` -- a syntax error -- so the return
    type has to be matched explicitly rather than keying on a trailing semicolon.
    """
    decl = re.compile(r'^(\s*)([A-Za-z_][\w:*&]*(?:[\w:*&\s]*?)\s+\**)'
                      + re.escape(name) + r'(\s*\([^;]*\)\s*;\s*)$')
    out = []
    for line in txt.split("\n"):
        m = decl.match(line)
        if m and 'extern "C"' not in line and m.group(2).split()[0] not in ('return', 'else'):
            line = f'{m.group(1)}extern "C" {m.group(2)}{name}{m.group(3)}'
        out.append(line)
    return "\n".join(out)


for rnd in range(8):
    r = subprocess.run([sys.executable, f"{KIT}/wgate.py", mod, addr, src],
                       capture_output=True, text=True, cwd=REPO, stdin=subprocess.DEVNULL)
    out = (r.stdout or "") + (r.stderr or "")
    if not out.startswith("UNDEF-SYM"):
        print(out.splitlines()[0] if out else "(no output)")
        break
    before = open(src, encoding="utf-8").read()
    txt = before
    done = []
    for u in re.findall(r"'([^']+)'", out):
        a = re.search(r'([0-9a-fA-F]{8})', u)
        if not a:
            continue
        real = names.get(a.group(1).lower())
        if not real:
            continue
        for cand in {u, source_identifier(u)}:
            if cand and cand != real and re.search(r'\b' + re.escape(cand) + r'\b', txt):
                txt = re.sub(r'\b' + re.escape(cand) + r'\b', real, txt)
                done.append((cand, real))
        txt = ensure_extern_c(txt, real)
    if txt == before:
        print("STUCK:", re.findall(r"'([^']+)'", out)[:3])
        break
    open(src, "w", encoding="utf-8", newline="\n").write(txt)
    print(f"  round {rnd}: {len(done)} rename(s), e.g. {done[0][0]} -> {done[0][1]}" if done
          else f"  round {rnd}: declaration fixes only")
