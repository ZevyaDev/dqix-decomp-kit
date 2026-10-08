"""Repair the mechanical faults that park correct work, statically.

Every fault handled here has cost the project batches of finished matches, and
each one used to be found by hand, one function at a time. None of them need a
compile to detect, so the wave applies them to every candidate before judging it.

  1. CALLEE NAMES. A worker declares `SomeName_02171d90(...)` but the committed
     symbol for 0x02171d90 is `func_ov000_02171d90` or a mangled `_Z...` name.
     The link then fails -- or worse, resolves elsewhere. Every such identifier
     carries the address, so it can be reconciled against symbols.txt. Names are
     declared extern "C" so a committed mangled name is not mangled a second time.
  2. .init SECTION. A function whose address lies in .init emits no .text; without
     `#pragma define_section initcode` the file looks empty and is rejected as
     size 0.
  3. KEEP-NAME. When the ROM symbol at this address is a mangled C++ name, the
     keep-raw rewrite would rename it to func_<addr> and break the match. Mark the
     file so the integrator leaves the symbol alone.

Usable as a library (`repair(path, module, addr) -> list[str]`) or on the command
line for one file. Returns the list of repairs applied; makes no other change.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import os, re, glob, sys

import buildcfg

REPO = _kp.REPO

_SYMS = {}


def _symbols(module=None):
    """addr -> committed symbol name; overlays share addresses, so `module` and main win."""
    if module not in _SYMS:
        own = [] if module in (None, "main") else \
              [f"{REPO}/{buildcfg.config_root()}/overlays/ov{module}/symbols.txt"]
        syms = {}
        for p in own + [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + \
                 sorted(glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt")):
            try:
                txt = open(p, encoding="utf-8", errors="ignore").read()
            except IOError:
                continue
            for m in re.finditer(r'^(\S+) kind:function\([^)]*\) addr:0x([0-9a-fA-F]{8})', txt, re.M):
                syms.setdefault(m.group(2).lower(), m.group(1))
        _SYMS[module] = syms
    return _SYMS[module]


def _all_symbol_names():
    names = set()
    for p in [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + \
             glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt"):
        try:
            names.update(re.findall(r'(?m)^(\S+) kind:function', open(p, encoding="utf-8",
                                                                      errors="ignore").read()))
        except IOError:
            continue
    return names


def _addresses_in(name):
    """Every 8-hex window in an identifier, most specific last.

    A plain search is not enough: "InitReturnSelf0202c794" contains the 9-hex run
    "f0202c794", whose first eight characters are not the address.
    """
    return [w.lower() for w in re.findall(r'(?=([0-9a-fA-F]{8}))', name)]


def _code_section_for(module, addr):
    """Name of the delinks code section containing addr, or None."""
    cfg = f"{REPO}/{buildcfg.config_root()}" if module == "main" else \
          f"{REPO}/{buildcfg.config_root()}/overlays/ov{module}"
    try:
        head = open(f"{cfg}/delinks.txt", encoding="utf-8").read().split("\n\n")[0]
    except IOError:
        return None
    a = int(addr, 16)
    for m in re.finditer(r'\.(\w+)\s+start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+) kind:code', head):
        if int(m.group(2), 16) <= a < int(m.group(3), 16):
            return m.group(1)
    return None


def _declaration_line(line, name):
    """True when `line` declares `name` (has a return type) rather than calling it."""
    return bool(re.match(r'^\s*(?:extern\s+"C"\s+)?[A-Za-z_][\w:*&]*[\w:*&\s]*?\s+\**'
                         + re.escape(name) + r'\s*\([^;]*\)\s*;\s*$', line))


def repair(path, module, addr, _no_rename=False):
    src = open(path, encoding="utf-8", errors="ignore").read()
    out = src
    applied = []
    syms = _symbols(module)
    own = syms.get(addr.lower())

    # 1. reconcile callee names ------------------------------------------------
    # ONLY identifiers used as callees. An address also shows up inside type names
    # (`struct Container0203a54c`), and renaming one of those rewrites a type to a
    # function symbol -- which produced the unreachable mangling
    # `_Z29InitSubObjectArraysReturnSelfP52_Z28ProcessAllSubObjects...`. A callee is
    # an identifier that appears immediately before `(` and is not introduced by a
    # struct/class/union/enum keyword.
    called = {m.group(1) for m in re.finditer(r'\b([A-Za-z_]\w*[0-9a-fA-F]{8}\w*)\s*\(', out)
              if not re.search(r'\b(?:struct|class|union|enum)\s+$', out[:m.start(1)])}
    renames = {}
    for ident in ([] if _no_rename else called):
        for a in _addresses_in(ident):
            if a == addr.lower():
                continue                      # never touch this file's own function
            real = syms.get(a)
            if real and real != ident:
                renames[ident] = real
                break
    for old, new in renames.items():
        out = re.sub(r'\b' + re.escape(old) + r'\b', new, out)
    if renames:
        applied.append(f"renamed {len(renames)} callee(s)")

    # every renamed callee must keep its exact symbol -> extern "C" on its prototype
    fixed_decls = 0
    lines = out.split("\n")
    for i, line in enumerate(lines):
        for new in set(renames.values()):
            if new in line and 'extern "C"' not in line and _declaration_line(line, new):
                lines[i] = re.sub(r'^(\s*)', r'\1extern "C" ', line, count=1)
                fixed_decls += 1
                break
    out = "\n".join(lines)
    if fixed_decls:
        applied.append(f'extern "C" on {fixed_decls} prototype(s)')

    # 2. .init section ---------------------------------------------------------
    sec = _code_section_for(module, addr)
    if sec == "init" and "initcode" not in out and "// USA:" in out:
        out = out.replace("#include <globaldefs.h>\n",
                          '#include <globaldefs.h>\n\n#pragma define_section initcode ".init" RX\n', 1)
        i = out.index("// USA:")
        head, tail = out[:i], out[i:]
        tail, n = re.subn(r'(?m)^(extern "C" )?(ARM|THUMB)\b',
                          lambda m: 'extern "C" __declspec(initcode) ' + m.group(2), tail, count=1)
        if n:
            out = head + tail
            applied.append("added initcode pragma")

    # 3. keep-name -------------------------------------------------------------
    # ANY curated name binds, not just a mangled one. Restricting this to `_Z...` meant a plain
    # curated symbol was never reconciled, so translate.py's `Trans_02001aac` sat at the address the
    # config binds to `memset` and link-failed the wave. A name is curated whenever it is not the
    # raw `func_<addr>` / `func_ov<NNN>_<addr>` tag.
    if (own and not re.fullmatch(r"func_(?:ov\d+_)?[0-9a-fA-F]{8}", own)
            and "KEEP-NAME" not in out and "// USA:" in out):
        out = out.replace("// USA:",
                          "// KEEP-NAME: the ROM symbol here is the mangled C++ name, not a func_ tag.\n// USA:", 1)
        applied.append("marked KEEP-NAME")
        # DO NOT RENAME A DEFINITION THAT IS ALREADY CORRECT. A well-written C++ source mangles to
        # the ROM symbol on its own -- `AppendListNode_x(ListHead_x*, void*)` IS
        # _Z23AppendListNode_xP17ListHead_xPv -- and rewriting it to that raw identifier both
        # destroys readability (the whole point of the project) and, without extern "C", mangles a
        # SECOND time into _Z49_Z23... : a symbol present nowhere in the ROM, which then lands in
        # symbols.txt and fails `dsd check symbols` for the entire build.
        #
        # So: compile what we have and ask what symbol it actually defines. Rename only if that is
        # not already the ROM symbol, and force extern "C" when renaming so the name is literal.
        m = re.search(r'(\b(?:ARM|THUMB)\b[^\n;{]*?\b)(\w+)(\s*\()', out)
        if m and m.group(2) != own and not _text_emits(out, own):
            line_start = out.rfind("\n", 0, m.start(1)) + 1
            already_ec = 'extern "C"' in out[line_start:m.start(3)]
            out = out[:m.start(2)] + own + out[m.end(2):]
            if not already_ec:
                out = out[:line_start] + 'extern "C" ' + out[line_start:]
            applied.append('renamed definition to the ROM symbol (extern "C")')

    # 3b. the ROM symbol IS the raw tag, and the source spells something else ----
    # Rule 3 fires only for a CURATED name, so a file defining `GetFieldOrComputeSum_020e523c` at an
    # address the config binds to plain `func_020e523c` matched no rule at all and autorepair
    # answered "no repairs needed" on a byte-exact candidate. A descriptive C++ name can never mangle
    # to a raw `func_` tag, so there is nothing to preserve here -- rename and force extern "C".
    # This fires on exactly the candidates a sweep is closing: r25 adds a parameter, which remangles.
    if (own and re.fullmatch(r"func_(?:ov\d+_)?[0-9a-fA-F]{8}", own)
            and not _text_emits(out, own)):
        m = re.search(r'(\b(?:ARM|THUMB)\b[^\n;{]*?\b)(\w+)(\s*\()', out)
        if m and m.group(2) != own:
            line_start = out.rfind("\n", 0, m.start(1)) + 1
            already_ec = 'extern "C"' in out[line_start:m.start(3)]
            out = out[:m.start(2)] + own + out[m.end(2):]
            if not already_ec:
                out = out[:line_start] + 'extern "C" ' + out[line_start:]
            applied.append("renamed definition to the raw ROM tag (extern \"C\")")

    # 4. right name, C++ linkage ------------------------------------------------
    # The definition already spells the ROM symbol, but without `extern "C"` the C++ front end
    # mangles it (`VectorizedMemset` -> `_Z16VectorizedMemsetPvhj`) and the gate reports
    # WRONG-SYMBOL on a function whose BYTES ALREADY MATCH. Nothing above catches it: the rename
    # block only looks at `ARM`/`THUMB` definitions and skips a name that is already correct.
    # 5 of 7 WRONG-SYMBOL candidates in the scratchpad pools were exactly this, and every one is a
    # finished function held back by a linkage keyword.
    if (own and "_Z" not in own and re.fullmatch(r"[A-Za-z_]\w*", own)
            and not _text_emits(out, own)):
        m = re.search(r'(?m)^([^\n=;{}]*?\b)(%s)(\s*\([^;{}]*\)\s*\{?)' % re.escape(own), out)
        if m and 'extern "C"' not in m.group(1):
            line_start = out.rfind("\n", 0, m.start(1)) + 1
            out = out[:line_start] + 'extern "C" ' + out[line_start:]
            applied.append('extern "C" on the definition (name was right, linkage was not)')

    # 5. C++ LINKAGE ON A CALLEE THAT IS MANGLED IN THE ROM ----------------------
    # The mirror image of 4, and it kills the file rather than the symbol: `extern "C" int
    # Vec3LengthRounded(int*);` links against the literal name, but the ROM's symbol is the mangled
    # `_Z17Vec3LengthRoundedPi`, so the gate reports UNDEF-SYM on a name that reads as perfectly
    # correct and the candidate parks. ov017:021ab280 was BYTE-EXACT behind exactly this.
    names = _all_symbol_names()
    unmangled = 0
    lines = out.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r'^(\s*)extern\s+"C"\s+(\S.*)$', line)
        if not m:
            continue
        mm = re.search(r'\b(\w+)\s*\([^;]*\)\s*;\s*$', m.group(2))
        if not mm or mm.group(1) in names:
            continue
        nm = mm.group(1)
        if any(n.startswith("_Z%d%s" % (len(nm), nm)) for n in names):
            lines[i] = m.group(1) + m.group(2)
            unmangled += 1
    if unmangled:
        out = "\n".join(lines)
        applied.append(f'dropped extern "C" on {unmangled} mangled callee(s)')

    # 6. block-local `const int X = 999;` emits an unreferenced `X$N` in .rodata (DATA-UNPLACED)
    consts = 0
    lines = out.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(\s+)(?:static\s+)?const\s+(?:unsigned\s+|signed\s+)?(?:int|short|char|long)\s+"
                     r"([A-Za-z_]\w*)\s*=\s*(-?(?:0x[0-9a-fA-F]+|\d+))\s*;\s*$", line)
        if m:
            lines[i] = "%senum { %s = %s };" % (m.group(1), m.group(2), m.group(3))
            consts += 1
    if consts:
        out = "\n".join(lines)
        applied.append(f"{consts} block-local const int(s) -> enum")

    if out == src:
        return applied

    # SELF-VERIFY. This runs on every candidate the wave sees, so a repair that
    # breaks a file would corrupt worker output at scale. Compile the result; if it
    # no longer builds, put the original back and report nothing was done. A repair
    # that cannot be proven harmless is not applied.
    open(path, "w", encoding="utf-8", newline="\n").write(out)
    # VERIFY THE SYMBOL, NOT JUST THE COMPILE. "it still compiles" is too weak a check: the
    # double-mangling bug above produced a file that built perfectly and emitted a symbol that
    # exists nowhere in the ROM. When we know the name the ROM demands, assert the object actually
    # defines it, and revert if it does not.
    ok, why = _emits_symbol(path, own)
    if not ok:
        open(path, "w", encoding="utf-8", newline="\n").write(src)
        return ["reverted: " + why]

    # VERIFY THE CALLEES TOO, NOT JUST THE EXPORTED SYMBOL. The callee rename above is keyed on the
    # 8 hex digits inside an identifier, and that address is not always the callee's own -- a name
    # like `SomeFunc0204c8f0` used for the function at 0x0207fd00 gets rewritten to the symbol for
    # 0x0204c8f0, turning a correct call into a wrong one. Measured 2026-08-25 on ov017:021aad8c and
    # 021b5dc4: both gated MATCH, autorepair renamed 8 and 6 callees, and both came out RELOC-WRONG
    # and deferred as `wired-0` for two whole waves. Only the gate can see this, so ask it: if the
    # verdict got WORSE, the repair is not a repair.
    RANK = {"MATCH": 0, "ALREADY-COMMITTED": 0, "BYTEDIFF": 1, "SIZE/OVERGEN": 1, "WRONG-SYMBOL": 2,
            "UNDEF-SYM": 3, "RELOC-WRONG": 4, "COMPILE-FAIL": 5}

    def _verdict(text):
        head = (text.strip().splitlines() or ["(none)"])[0]
        return RANK.get(head.split(":")[0].strip(), 2)

    try:
        import subprocess as _sp
        _gate = lambda p: _sp.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "wgate.py"),
             module, addr, os.path.abspath(p)],
            capture_output=True, text=True, cwd=REPO, stdin=_sp.DEVNULL)
        _before_p = path + ".pre"
        open(_before_p, "w", encoding="utf-8", newline="\n").write(src)
        _b = _verdict((_gate(_before_p).stdout or "") + (_gate(_before_p).stderr or ""))
        _r = _gate(path)
        _a = _verdict((_r.stdout or "") + (_r.stderr or ""))
        os.remove(_before_p)
        if _a > _b:
            open(path, "w", encoding="utf-8", newline="\n").write(src)
            # ALL-OR-NOTHING WAS TOO BLUNT. The rename block is the only one that can pick a wrong
            # callee, but the revert threw away every other repair with it -- so a file whose ONLY
            # real fault was a linkage keyword stayed parked because an unrelated rename in the same
            # pass was bad. Retry once with renaming suppressed and keep that if it holds up.
            if not _no_rename:
                again = repair(path, module, addr, _no_rename=True)
                if again and not any(r.startswith("reverted") for r in again):
                    return again + ["callee renames suppressed (they made the verdict worse)"]
            return ["reverted: the repair made the gate verdict worse (callee rename)"]
    except Exception:
        pass          # a gate that cannot run is not a reason to discard a repair
    return applied


_FLAGS = list(buildcfg.FLAGS)


def _emits_symbol(path, want):
    """Compile `path` and check it defines `want` (when we know what the ROM demands).

    Returns (ok, reason). Compiling is necessary but NOT sufficient: a repair can leave a file that
    builds cleanly while defining a symbol that exists nowhere in the ROM, which then gets written
    into symbols.txt and fails `dsd check symbols` for the entire build. Verifying the emitted
    symbol is what actually proves the repair harmless.

    Deliberately permissive on tooling failure -- a missing compiler or an unreadable object must
    never make a wave discard good source -- but NOT permissive about a wrong symbol, which is the
    thing this exists to catch.
    """
    import subprocess
    import tempfile
    cc = buildcfg.CC
    obj = os.path.join(tempfile.gettempdir(), f"autorepair_{os.getpid()}.o")
    try:
        r = subprocess.run([cc] + _FLAGS + ["-c", path, "-o", obj],
                           capture_output=True, text=True, cwd=REPO, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            return False, "repair did not compile"
        if not want:
            return True, ""                    # nothing asserted about the name
        try:
            from elftools.elf.elffile import ELFFile
            with open(obj, "rb") as fh:
                syms = [s.name for s in ELFFile(fh).get_section_by_name(".symtab").iter_symbols()
                        if s["st_info"]["type"] == "STT_FUNC" and s["st_info"]["bind"] == "STB_GLOBAL"]
        except Exception:
            return True, ""                    # cannot read the object: do not block the wave
        if syms and want not in syms:
            return False, f"repair emitted {syms} but the ROM symbol is {want}"
        return True, ""
    except Exception:
        return True, ""                        # never block a wave on a tooling hiccup
    finally:
        if os.path.exists(obj):
            os.remove(obj)


def _compiles(path):
    ok, _ = _emits_symbol(path, None)
    return ok


def _text_emits(text, want):
    """Does this source text already define `want`? Compiles a scratch copy to find out."""
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), f"autorepair_probe_{os.getpid()}.cpp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        ok, _why = _emits_symbol(tmp, want)
        return ok
    except OSError:
        return False
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    print(repair(sys.argv[3], sys.argv[1], sys.argv[2]) or "no repairs needed")
