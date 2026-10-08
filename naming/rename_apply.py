import json, os, re, sys

from namingpaths import LABEL as REPO
import buildcfg

CFG = REPO + "/" + buildcfg.config_root()
APPLY = "--apply" in sys.argv

SYMF = re.compile(r"^(\S+)\s+kind:(\w+)[\(\s]")
IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
LITERAL = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'"
                     + r"|//[^\n]*" + r"|/\*.*?\*/", re.S)

KEYWORDS = set("""
alignas alignof and and_eq asm auto bitand bitor bool break case catch char class compl
const const_cast continue default delete do double dynamic_cast else enum explicit export
extern false float for friend goto if inline int long mutable namespace new not not_eq
operator or or_eq private protected public register reinterpret_cast return short signed
sizeof static static_cast struct switch template this throw true try typedef typeid
typename union unsigned using virtual void volatile wchar_t while xor xor_eq
NULL ARM THUMB TRUE FALSE size_t va_list
""".split())


def symbols_paths():
    yield CFG + "/symbols.txt"
    for sub in ("itcm", "dtcm"):
        yield CFG + "/" + sub + "/symbols.txt"
    ovd = CFG + "/overlays"
    if os.path.isdir(ovd):
        for n in sorted(os.listdir(ovd)):
            yield ovd + "/" + n + "/symbols.txt"


def global_symbols():
    out = set()
    for p in symbols_paths():
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8", errors="replace"):
            m = SYMF.match(line)
            if m:
                out.add(m.group(1))
    return out


def header_idents():
    out = set()
    for root, _, files in os.walk(REPO + "/include"):
        for f in files:
            if f.endswith((".h", ".hpp")):
                text = open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
                out.update(IDENT.findall(text))
    return out


def mask(text):
    held = []

    def take(m):
        s = m.group(0)
        held.append(s)
        return "\x00%d\x00" % (len(held) - 1) + "\n" * s.count("\n")

    return LITERAL.sub(take, text), held


def unmask(text, held):
    def put(m):
        s = held[int(m.group(1))]
        return s + m.group(2)[s.count("\n"):]

    return re.sub(r"\x00(\d+)\x00(\n*)", put, text)


def sub_span(body, mapping, hits):
    keys = sorted(mapping, key=len, reverse=True)
    if not keys:
        return body
    pat = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(k) for k in keys))

    def rep(m):
        hits[m.group(0)] = hits.get(m.group(0), 0) + 1
        return mapping[m.group(0)]

    return pat.sub(rep, body)


def brace_span(body, at):
    open_at = body.find("{", at)
    if open_at < 0:
        return None
    depth = 0
    for i in range(open_at, len(body)):
        if body[i] == "{":
            depth += 1
        elif body[i] == "}":
            depth -= 1
            if depth == 0:
                return open_at, i
    return None


def resolve_scope(body, text, scope, function):
    if scope.startswith("struct:"):
        tag = scope.split(":", 1)[1].strip()
        m = re.search(r"\b(?:struct|class|union)\s+%s\b" % re.escape(tag), body)
        return brace_span(body, m.end()) if m else None
    if scope in ("func", "function", "body"):
        spans = [m for m in re.finditer(r"\b%s\s*\(" % re.escape(function or ""), body)]
        for m in reversed(spans):
            sp = brace_span(body, m.end())
            if sp and body[m.end():sp[0]].count(";") == 0:
                return body.rfind("\n", 0, m.start()) + 1, sp[1] + 1
        return None
    if scope.startswith("line:"):
        needle = scope.split(":", 1)[1].strip()
        idx = text.find(needle)
        if idx < 0:
            return None
        li = text.count("\n", 0, idx)
        lines = body.split("\n")
        if li >= len(lines):
            return None
        start = sum(len(l) + 1 for l in lines[:li])
        return start, start + len(lines[li])
    return None


def substitute(text, mapping, scoped, function):
    body, held = mask(text)
    hits = {k: 0 for k in mapping}
    body = sub_span(body, mapping, hits)
    problems = []
    spans = []
    for scope, smap in scoped.items():
        span = resolve_scope(body, text, scope, function)
        if span is None:
            problems.append("scope not found: %s" % scope)
            continue
        spans.append((span, smap, scope))
    for (start, end), smap, scope in sorted(spans, key=lambda s: -s[0][0]):
        shits = {k: 0 for k in smap}
        body = body[:start] + sub_span(body[start:end], smap, shits) + body[end:]
        for k, n in shits.items():
            if n == 0:
                problems.append("no occurrence of %s in %s" % (k, scope))
    return unmask(body, held), hits, problems


def code_only(text):
    return mask(text)[0]


def decl_count(code, ident):
    pat = re.compile(r"(?<![.>\-])\b[A-Za-z_]\w*[\s*&]+%s\s*(?=[,;)\[=])" % re.escape(ident))
    return len(pat.findall(code))


def comment_block(lines, defname):
    pat = re.compile(r"\b%s\s*\(" % re.escape(defname))
    di = None
    for i, ln in enumerate(lines):
        if pat.search(ln) and not ln.lstrip().startswith("//") and "{" in "".join(lines[i:i + 3]):
            di = i
    if di is None:
        return None, None
    j = di
    while j > 0 and lines[j - 1].lstrip().startswith("//"):
        j -= 1
    return j, di


def main():
    plan = json.load(open(sys.argv[1], encoding="utf-8"))
    globs = global_symbols()
    hdrs = header_idents()
    ok, bad = [], []
    for it in plan:
        rel = it["file"].replace("\\", "/")
        path = REPO + "/" + rel
        problems = []
        if not rel.startswith("src/") or not os.path.exists(path):
            bad.append((rel, "no such source file"))
            continue
        text = open(path, encoding="utf-8", newline="").read()
        code = code_only(text)
        function = it.get("function") or os.path.splitext(os.path.basename(rel))[0]
        mapping, scoped = {}, {}
        for r in it.get("renames", []):
            old, new = r["old"], r["new"]
            scope = (r.get("scope") or "").strip()
            if old == new:
                continue
            if old in globs:
                problems.append("global symbol %s" % old)
                continue
            if old in KEYWORDS:
                problems.append("keyword %s" % old)
                continue
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", new) or new in KEYWORDS or new in globs:
                problems.append("bad target %s" % new)
                continue
            if old in hdrs:
                problems.append("header ident %s (allowed, gate decides)" % old)
            if scope:
                scoped.setdefault(scope, {})[old] = new
                continue
            if re.search(r"\b%s\b" % re.escape(new), code) and new not in mapping.values():
                problems.append("target %s already present" % new)
                continue
            n = decl_count(code, old)
            if n > 1:
                problems.append("NEEDS SCOPE: %s declared %d times, unscoped rename dropped"
                                % (old, n))
                continue
            mapping[old] = new

        while True:
            newtext, hits, sprob = substitute(text, mapping, scoped, function)
            after = code_only(newtext)
            halved = None
            for old, new in list(mapping.items()) + [(o, n) for m in scoped.values()
                                                     for o, n in m.items()]:
                if decl_count(code, old) > 0 and decl_count(after, new) == 0 \
                        and re.search(r"[.>]\s*\b%s\b" % re.escape(new), after):
                    halved = (old, new)
                    break
            if halved is None:
                break
            old, new = halved
            problems.append("HALF-APPLIED: %s -> %s renames uses but not the declaration, dropped"
                            % (old, new))
            mapping.pop(old, None)
            for m in scoped.values():
                if m.get(old) == new:
                    m.pop(old, None)
        problems.extend(sprob)
        for k, n in hits.items():
            if n == 0:
                problems.append("no occurrence of %s" % k)

        for e in it.get("edits", []):
            if newtext.count(e["old"]) == 1:
                newtext = newtext.replace(e["old"], e["new"])
            else:
                problems.append("edit matched %d times: %r"
                                % (newtext.count(e["old"]), e["old"][:60]))

        cm = it.get("comment")
        if cm:
            lines = newtext.split("\n")
            defname = function
            j, di = comment_block(lines, defname)
            if j is None:
                problems.append("definition of %s not found" % defname)
            else:
                block = cm.rstrip().split("\n")
                newtext = "\n".join(lines[:j] + block + lines[di:])

        ok.append((rel, path, newtext,
                   len(mapping) + sum(len(v) for v in scoped.values()), problems))

    changed = 0
    for rel, path, newtext, nren, problems in ok:
        for p in problems:
            print("   note %-52s %s" % (rel.split("/")[-1], p))
        if APPLY:
            old = open(path, encoding="utf-8", newline="").read()
            if newtext != old:
                open(path, "w", encoding="utf-8", newline="").write(newtext)
                changed += 1
    for rel, why in bad:
        print("   SKIP %-52s %s" % (rel.split("/")[-1], why))
    print("files:", len(ok), " renames:", sum(o[3] for o in ok),
          " written:", changed if APPLY else 0, " skipped:", len(bad))


main()
