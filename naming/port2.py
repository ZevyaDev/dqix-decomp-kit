import os, re, sys, json, subprocess

from namingpaths import LABEL as REPO
import buildcfg

CFG = REPO + "/" + buildcfg.config_root()
SRC_BRANCH = "labeling-pass"
APPLY = "--apply" in sys.argv

SYMF = re.compile(r"^(\S+)\s+kind:(\w+)\(([^)]*)\)\s+addr:0x([0-9a-fA-F]+)")
SYMD = re.compile(r"^(\S+)\s+kind:(\w+)\s+addr:0x([0-9a-fA-F]+)")
IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def git(*a):
    return subprocess.check_output(["git", "-C", REPO] + list(a)).decode("utf-8", "replace")


def rel_for(mod):
    root = buildcfg.config_root()
    if mod == "main":
        return root + "/symbols.txt"
    if mod in ("itcm", "dtcm"):
        return root + "/%s/symbols.txt" % mod
    return root + "/overlays/%s/symbols.txt" % mod


def modules():
    yield "main"
    for s in ("itcm", "dtcm"):
        yield s
    for n in sorted(os.listdir(CFG + "/overlays")):
        yield n


def parse(text):
    out = []
    for line in text.splitlines():
        m = SYMF.match(line) or SYMD.match(line)
        if m:
            g = m.groups()
            out.append((g[0], int(g[-1], 16)))
    return out


def build_maps():
    o2a, a2n = {}, {}
    for mod in modules():
        rel = rel_for(mod)
        try:
            for n, a in parse(git("show", "%s:%s" % (SRC_BRANCH, rel))):
                o2a.setdefault(n, (mod, a, "exact"))
                b = base_of(n)
                if b != n and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", b):
                    o2a.setdefault(b, (mod, a, "base"))
        except subprocess.CalledProcessError:
            pass
        p = REPO + "/" + rel
        if os.path.exists(p):
            for n, a in parse(open(p, encoding="utf-8", errors="replace").read()):
                a2n[(mod, a)] = n
    return o2a, a2n


def old_symbol(mod, addr):
    for n, a in parse(git("show", "%s:%s" % (SRC_BRANCH, rel_for(mod)))):
        if a == addr:
            return n
    return None


def base_of(sym):
    m = re.match(r"^_Z(\d+)(.+)$", sym)
    if m:
        return m.group(2)[: int(m.group(1))]
    return sym


def func_size(mod, addr):
    for line in open(REPO + "/" + rel_for(mod), encoding="utf-8", errors="replace"):
        m = SYMF.match(line)
        if m and int(m.group(4), 16) == addr and m.group(2) == "function":
            s = re.search(r"size=0x([0-9a-fA-F]+)", m.group(3))
            return int(s.group(1), 16) if s else None
    return None


def delinks_path(mod):
    if mod == "main":
        return CFG + "/delinks.txt"
    if mod in ("itcm", "dtcm"):
        return CFG + "/" + mod + "/delinks.txt"
    return CFG + "/overlays/" + mod + "/delinks.txt"


def insert_delink(mod, srcpath, start, end):
    p = delinks_path(mod)
    t = open(p, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in t else "\n"
    if srcpath + ":" in t:
        return
    entry = "%s:%s\tcomplete%s\t.text start:0x%08x end:0x%08x" % (srcpath, nl, nl, start, end)
    blocks = t.split(nl + nl)
    out, done = [], False
    for b in blocks:
        m = re.search(r"\.text start:0x([0-9a-fA-F]+)", b)
        if not done and m and int(m.group(1), 16) > start:
            out.append(entry)
            done = True
        out.append(b)
    if not done:
        out.append(entry)
    open(p, "w", encoding="utf-8", newline="").write((nl + nl).join(out))


def rename_symbol(mod, addr, new):
    p = REPO + "/" + rel_for(mod)
    lines = open(p, encoding="utf-8", newline="").read().split("\n")
    for i, line in enumerate(lines):
        m = SYMF.match(line) or SYMD.match(line)
        if m and int(m.groups()[-1], 16) == addr:
            lines[i] = new + line[len(m.group(1)):]
            open(p, "w", encoding="utf-8", newline="").write("\n".join(lines))
            return m.group(1)
    return None


EXTRA_DECLS = {
    "GetCombatantWithFlag0x100":
        'extern "C" struct CombatantStruct* func_0200ff1c(struct BattleStruct* battleStruct, int combatantId);',
}


def inject_decl(body, decl):
    lines = body.split("\n")
    inc = [i for i, l in enumerate(lines) if l.startswith("#include")]
    at = (inc[-1] + 1) if inc else 0
    lines[at:at] = ["", decl]
    return "\n".join(lines)


def force_extern_c(body, plain):
    if not plain:
        return body
    lines = body.split("\n")
    for i, ln in enumerate(lines):
        s = ln.strip()
        # a declaration sits at column 0 with a return type; anything indented is a call
        if ln != s or not s.endswith(");") or "(" not in s or s.startswith("//"):
            continue
        if 'extern "C"' in s or s.startswith("return") or "=" in s.split("(")[0]:
            continue
        head = s.split("(")[0]
        if " " not in head.strip():
            continue
        if any(re.search(r"\b%s$" % re.escape(n), head) for n in plain):
            lines[i] = 'extern "C" ' + s
    return "\n".join(lines)


def rewrite(body, defname, newname, comment):
    lines = body.split("\n")
    di = None
    pat = re.compile(r"\b%s\s*\(" % re.escape(defname))
    for i, ln in enumerate(lines):
        if pat.search(ln) and "{" in "".join(lines[i : i + 2]):
            di = i
    if di is None:
        return None
    lines[di] = pat.sub(newname + "(", lines[di])
    if 'extern "C"' not in lines[di]:
        lines[di] = 'extern "C" ' + lines[di].lstrip()
    j = di
    while j > 0 and lines[j - 1].lstrip().startswith("//"):
        j -= 1
    block = [c for c in comment.rstrip().split("\n")]
    return "\n".join(lines[:j] + block + lines[di:])


def main():
    plan = json.load(open(sys.argv[1]))
    o2a, a2n = build_maps()
    ported, skipped = [], []
    for it in plan:
        mod = it["module"].split(" ")[0]
        addr = int(it["address"], 16)
        try:
            body = git("show", "%s:%s" % (SRC_BRANCH, it["labeling_source"]))
        except subprocess.CalledProcessError:
            skipped.append((it["address"], it["name"], "source missing"))
            continue
        miss = [h for h in re.findall(r'#include\s+"([^"]+)"', body)
                if not os.path.exists(REPO + "/include/" + h)]
        if miss:
            skipped.append((it["address"], it["name"], "header " + miss[0]))
            continue
        osym = old_symbol(mod, addr)
        if not osym:
            skipped.append((it["address"], it["name"], "no labeling symbol"))
            continue
        unresolved = set()

        def sub(m):
            nm = m.group(0)
            k = o2a.get(nm)
            if k is None:
                return nm
            v = a2n.get((k[0], k[1]))
            if v is None:
                unresolved.add(nm)
                return nm
            # a base-name match means the source spelled the C++ name, which the compiler
            # mangles for us; only rewrite it when the analysis symbol is a plain C name.
            if k[2] == "base" and v.startswith("_Z"):
                return nm
            return v

        plain = set()

        def sub_track(m):
            r = sub(m)
            if r != m.group(0) and not r.startswith("_Z"):
                plain.add(r)
            return r

        newbody = IDENT.sub(sub_track, body)
        newbody = force_extern_c(newbody, plain)
        for old_id, decl in EXTRA_DECLS.items():
            if re.search(r"\b%s\b" % old_id, body) and decl.split("(")[0].split()[-1] not in newbody.split("{")[0]:
                newbody = inject_decl(newbody, decl)
        if unresolved:
            skipped.append((it["address"], it["name"], "unmapped " + sorted(unresolved)[0]))
            continue
        defname = a2n.get((mod, addr)) or base_of(osym)
        comment = IDENT.sub(sub, it["comment"])
        out = rewrite(newbody, defname, it["name"], comment)
        if out is None:
            out = rewrite(newbody, base_of(osym), it["name"], comment)
        if out is None:
            skipped.append((it["address"], it["name"], "definition not found (%s)" % defname))
            continue
        size = func_size(mod, addr)
        if size is None:
            skipped.append((it["address"], it["name"], "no size"))
            continue
        ported.append((it, mod, addr, size, out))

    print("portable:", len(ported), " skipped:", len(skipped))
    for a, n, why in skipped:
        print("   skip %s %-32s %s" % (a, n, why))
    if not APPLY:
        return
    for it, mod, addr, size, out in ported:
        dest = os.path.dirname(it["labeling_source"]) + "/" + it["name"] + ".cpp"
        os.makedirs(os.path.dirname(REPO + "/" + dest), exist_ok=True)
        open(REPO + "/" + dest, "w", encoding="utf-8", newline="\n").write(out)
        old = rename_symbol(mod, addr, it["name"])
        insert_delink(mod, dest, addr, addr + size)
        if old and old != it["name"]:
            for d in (REPO + "/src", REPO + "/include"):
                for root, _, files in os.walk(d):
                    for f in files:
                        if not f.endswith((".cpp", ".c", ".h", ".hpp")):
                            continue
                        fp = os.path.join(root, f)
                        if os.path.abspath(fp) == os.path.abspath(REPO + "/" + dest):
                            continue
                        t = open(fp, encoding="utf-8", newline="").read()
                        if old not in t:
                            continue
                        t2 = re.sub(r"\b%s\b" % re.escape(old), it["name"], t)
                        if t2 != t:
                            open(fp, "w", encoding="utf-8", newline="").write(t2)
    print("ported", len(ported))


main()
