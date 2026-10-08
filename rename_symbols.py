#!/usr/bin/env python
"""Apply the human branch's RENAMES to our sources, before the build.

relink_undefined.py works from linker errors, so it only ever sees symbols that
reached the link. A rename the human branch makes to a function we call by its
plain C++ name fails earlier than that -- at compile time, as
"undefined identifier 'PopulateContext'" -- and the linker never runs, so the
repair loop spins at zero rewrites while the build stays broken.

This pass is the complement: diff the symbol tables of two revisions, and for
every address whose name changed, rewrite the old plain name to the new one
across src/. Both spellings are handled, plain and mangled.

Only same-address renames are applied, so this cannot invent a new binding; and
short names are skipped, because a two- or three-letter identifier is as likely
to be a local variable as a symbol.

Usage: python rename_symbols.py <old-rev> [<new-rev>]     new-rev defaults to the worktree
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import regionblocks
import os
import re
import subprocess
import sys

REPO = _kp.REPO
os.chdir(REPO)
OLD = sys.argv[1]
NEW = sys.argv[2] if len(sys.argv) > 2 else None
MIN_LEN = 6

ADDR = re.compile(r"addr:0x([0-9a-fA-F]+)")
MANGLED_PLAIN = re.compile(r"^_Z(\d+)(.+)$")
NESTED = re.compile(r"^_ZN(\d+)")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def symbol_files():
    r = subprocess.run(["git", "ls-files", "config"], capture_output=True, text=True)
    return [f for f in r.stdout.split() if f.startswith("config/") and f.endswith("symbols.txt")]


def table(rev):
    out = {}
    for p in symbol_files():
        if rev:
            r = subprocess.run(["git", "show", "%s:%s" % (rev, p)], capture_output=True, text=True)
            text = r.stdout if r.returncode == 0 else ""
        else:
            text = open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else ""
        for line in text.splitlines():
            m = ADDR.search(line)
            if m and line.split():
                out.setdefault(int(m.group(1), 16), line.split()[0])
    return out


def plain(sym):
    """The unqualified C++ name inside a mangled symbol, else None."""
    m = MANGLED_PLAIN.match(sym)
    if m and not NESTED.match(sym):
        return m.group(2)[:int(m.group(1))]
    return None


old, new = table(OLD), table(NEW)
renames = {}
for a, o in old.items():
    n = new.get(a)
    if not n or n == o:
        continue
    if not IDENT.match(n):  # ".p__sinit_X" and "__sinit_File.cpp" are not spellable in C
        continue
    po, pn = plain(o), plain(n)
    # Plain-name rename of a free function: safe to apply textually.
    if po and pn and po != pn and len(po) >= MIN_LEN:
        renames[po] = pn
    # The mangled spelling appears verbatim in extern "C" bridge declarations.
    if len(o) >= MIN_LEN:
        renames[o] = n

# A raw `func_<addr>` spelling only links while the config still names that address the same
# way. A human branch that brings its own header full of raw names is undefined against our
# curated symbols, and the linker never runs to report it -- the compile fails first.
raw_renames = 0
for a, n in new.items():
    raw = "func_%08x" % a
    if n != raw and re.match(r"^[A-Za-z_]\w*$", n) and raw not in renames:
        renames[raw] = n
        raw_renames += 1

if not renames:
    print("rename_symbols: no renames between %s and %s" % (OLD, NEW or "worktree"))
    raise SystemExit

pat = re.compile(r"\b(%s)\b" % "|".join(sorted(map(re.escape, renames), key=len, reverse=True)))
hits, files = 0, 0
for root, _, names in [rn for d in ("src", "include") for rn in os.walk(d)]:
    for f in names:
        # Same extension set as fix_includes.py. Missing .c/.hpp meant a rename inside one of those
        # was left un-applied and surfaced as the compile-time "undefined identifier" that this pass
        # exists to prevent -- and the repair loop cannot see it, because the linker never runs.
        if not f.endswith((".c", ".cpp", ".h", ".hpp")):
            continue
        p = os.path.join(root, f)
        text = open(p, encoding="utf-8", errors="replace").read()
        # Never rewrite the `// USA: func_...` marker: it is the file's identity, and every tool
        # maps file -> address through it.
        newtext, n = regionblocks.rewrite(text, pat, renames)
        if n:
            open(p, "w", encoding="utf-8", newline="\n").write(newtext)
            hits += n
            files += 1
print("rename_symbols: %d renames (%d raw-address) applied at %d sites in %d files"
      % (len(renames), raw_renames, hits, files))
for o in sorted(renames)[:12]:
    print("  %s -> %s" % (o, renames[o]))
if len(renames) > 12:
    print("  ... %d more" % (len(renames) - 12))
