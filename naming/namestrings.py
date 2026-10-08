import os, re, sys, json

from namingpaths import GAME, LABEL
import buildcfg

REPO = sys.argv[1] if len(sys.argv) > 1 else LABEL
EXT = GAME + "/" + buildcfg.extract_root()
CFG = REPO + "/" + buildcfg.config_root()
APPLY = "--apply" in sys.argv

SYM = re.compile(r"^(\S+)\s+kind:data\(([^)]*)\)\s+addr:0x([0-9a-fA-F]+)(.*)$")
DATAREF = re.compile(r"\bdata_(?:ov\d{3}_)?0[0-9a-fA-F]{7}\b")


def text_base(delinks):
    for line in open(delinks, encoding="utf-8", errors="replace"):
        m = re.search(r"\.text\s+start:0x([0-9a-fA-F]+)", line)
        if m:
            return int(m.group(1), 16)
    return None


def modules():
    yield ("main", EXT + "/arm9/arm9.bin", CFG + "/delinks.txt", CFG + "/symbols.txt")
    for sub in ("itcm", "dtcm"):
        b = EXT + "/arm9/" + sub + ".bin"
        if os.path.exists(b):
            yield (sub, b, CFG + "/" + sub + "/delinks.txt", CFG + "/" + sub + "/symbols.txt")
    ovdir = CFG + "/overlays"
    for name in sorted(os.listdir(ovdir)):
        b = EXT + "/arm9_overlays/" + name + ".bin"
        if os.path.exists(b):
            yield (name, b, ovdir + "/" + name + "/delinks.txt", ovdir + "/" + name + "/symbols.txt")


PRINTABLE = set(range(0x20, 0x7F))

WORDS = {
    "%s": "Str", "%d": "Num", "%c": "Chr", "%x": "Hex", "%u": "Num", "%f": "Flt",
}


def readable(raw):
    """Return the ASCII string at raw[0:] if it is a plausible C string literal."""
    end = raw.find(b"\x00")
    if end < 4:
        return None
    s = raw[:end]
    if any(c not in PRINTABLE for c in s):
        return None
    letters = sum(1 for c in s if chr(c).isalpha())
    if letters < 3:
        return None
    return s.decode("ascii")


def identifier(s):
    t = s
    for k, v in WORDS.items():
        t = t.replace(k, " " + v + " ")
    t = re.sub(r"%[0-9.\-+ #]*[a-zA-Z]", " Num ", t)
    t = re.sub(r"[^0-9A-Za-z]+", " ", t)
    parts = [p for p in t.split() if p]
    if not parts:
        return None
    out = []
    for p in parts:
        if p.isupper() and len(p) > 1:
            out.append(p[0] + p[1:].lower())
        else:
            out.append(p[0].upper() + p[1:])
    name = "".join(out)
    if len(name) > 44:
        name = name[:44]
    if not name or not name[0].isalpha():
        return None
    return "str" + name


def main():
    renames = {}
    used = set()
    skipped = 0
    for mod, binp, dl, sy in modules():
        data = open(binp, "rb").read()
        base = text_base(dl)
        if base is None:
            continue
        for line in open(sy, encoding="utf-8", errors="replace"):
            m = SYM.match(line)
            if not m:
                continue
            name, spec, addr = m.group(1), m.group(2), int(m.group(3), 16)
            if not re.match(r"^data_(?:ov\d{3}_)?0[0-9a-fA-F]{7}$", name):
                continue
            off = addr - base
            if off < 0 or off + 4 > len(data):
                continue
            cap = None
            sm = re.match(r"^byte\[(\d+)\]$", spec)
            if sm:
                cap = int(sm.group(1))
            s = readable(data[off : off + (cap if cap else 256)])
            if s is None:
                continue
            if cap is not None and len(s) + 1 > cap:
                skipped += 1
                continue
            ident = identifier(s)
            if ident is None:
                skipped += 1
                continue
            cand = ident
            n = 2
            while cand in used:
                cand = "%s_%08x" % (ident, addr)
                if cand in used:
                    cand = "%s_%d_%08x" % (ident, n, addr)
                    n += 1
            used.add(cand)
            renames.setdefault(mod, {})[name] = (cand, s)

    total = sum(len(v) for v in renames.values())
    print("renameable string symbols:", total, "  skipped:", skipped)
    json.dump({m: {k: v[0] for k, v in d.items()} for m, d in renames.items()}, open("renames.json", "w"), indent=1)
    for mod in list(renames)[:1]:
        for k, v in list(renames[mod].items())[:12]:
            print("   %-16s -> %-46s %r" % (k, v[0], v[1]))
    if not APPLY:
        return

    # source file -> module, from each module's delinks.txt
    filemod = {}
    for mod, binp, dl, sy in modules():
        for line in open(dl, encoding="utf-8", errors="replace"):
            m = re.match(r"^(src/\S+\.(?:cpp|c|s)):\s*$", line.strip())
            if m:
                filemod[m.group(1)] = mod

    for mod, binp, dl, sy in modules():
        table = renames.get(mod)
        if not table:
            continue
        txt = open(sy, encoding="utf-8", newline="").read()
        for old, (new, s) in table.items():
            txt = re.sub(r"(?m)^%s(?= kind:)" % re.escape(old), new, txt)
        open(sy, "w", encoding="utf-8", newline="").write(txt)

    # a source in any module may reference a symbol from main/itcm/dtcm, which carry no ov prefix
    shared = {}
    for m in ("main", "itcm", "dtcm"):
        shared.update(renames.get(m, {}))

    changed = 0
    unresolved = set()
    roots = [REPO + "/src", REPO + "/include"]
    for base_dir in roots:
        for root, dirs, files in os.walk(base_dir):
            for f in files:
                if not f.endswith((".cpp", ".c", ".h", ".hpp")):
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, REPO).replace("\\", "/")
                table = renames.get(filemod.get(rel), {})
                txt = open(p, encoding="utf-8", newline="").read()
                if "data_" not in txt:
                    continue

                def sub(m):
                    r = table.get(m.group(0)) or shared.get(m.group(0))
                    if r:
                        return r[0]
                    unresolved.add(m.group(0))
                    return m.group(0)

                new = DATAREF.sub(sub, txt)
                if new != txt:
                    open(p, "w", encoding="utf-8", newline="").write(new)
                    changed += 1
    print("source files rewritten:", changed, " refs left as data_*:", len(unresolved))


main()
