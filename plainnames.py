"""Plain names for AI-written decomp source; upstream code keeps its names.

    python plainnames.py check FILE...   NOT A PLAIN NAME per declaration that is not plain; exit 1
    python plainnames.py fix FILE...     rename them in place
    python plainnames.py tree            rename the whole tree

Functions func_[ovNNN_]<addr> (no symbol: inline_<lowest caller addr>[_N]); globals data_; types
Struct_<addr> (lowest global instance, else lowest-address user; more at one address _2, _3); enums
Enum_<addr>[_B] with constants Enum_<addr>_<value> (m for minus); other typedefs Type_<addr>;
members unknown_<hexoff>_ (bitfields unknown_<off>_<bit>_, more at one offset unknown1_<off>_);
parameters arg<i>; locals var<i>. FILE is relative to the decomp tree ($DQIX_REPO, or --tree DIR).
"""
import bisect
import collections
import ctypes
import glob
import io
import json
import multiprocessing
import os
import re
import subprocess
import sys
import tarfile

import clang.cindex as ci

import kitpaths

K = ci.CursorKind
RECORDS = {K.STRUCT_DECL, K.UNION_DECL, K.CLASS_DECL, K.CLASS_TEMPLATE}
FUNCS = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.CONVERSION_FUNCTION, K.FUNCTION_TEMPLATE}
REFS = {K.TYPE_REF, K.MEMBER_REF_EXPR, K.MEMBER_REF, K.DECL_REF_EXPR}
ARRAYS = {ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY, ci.TypeKind.VARIABLEARRAY,
          ci.TypeKind.DEPENDENTSIZEDARRAY}
MANGLED = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.CONVERSION_FUNCTION, K.VAR_DECL}
REGIONS = ("usa", "jpn", "eur")
IDENT = re.compile(r"~?[A-Za-z_][A-Za-z_0-9]*")
NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
ADDR = re.compile(r"^(?:func|data)_(?:ov(\d{3})_)?([0-9a-f]{8})$")
STEM = re.compile(r"(?:func|data)_(?:ov(\d{3})_)?([0-9a-f]{8})")
BARE = re.compile(r"(?:ov(\d{3})_)?([0-9a-f]{8})")
OVDIR = re.compile(r"/Overlay_(\d+)/")
SIZE_CHECK = re.compile(r"^(?:const\s+)?(?:signed\s+|unsigned\s+)?char\s*\[\s*-?1\s*\]$")
SPECIAL = ("operator", "~")
PLAIN = re.compile(r"(?:Struct|Enum|Type)_(?:ov\d{3}_)?[0-9a-f]{8}(?:_[A-Z]+)?(?:_m?\d+)*|unknown\d*_[0-9a-f]+_(?:\d+_)?"
                   r"|(?:inline|func)_(?:ov\d{3}_)?[0-9a-f]{8}(?:_\d+)?|arg\d+|var\d+")
LOCAL = re.compile(r"var\d+")
WORD = re.compile(rb"[A-Za-z_0-9]")
BNAME = re.compile(rb"[A-Za-z_][A-Za-z_0-9]*")
BIDENT = re.compile(rb"(?<![A-Za-z_0-9])[A-Za-z_][A-Za-z_0-9]*")
DEFINE = re.compile(rb"^[ \t]*#[ \t]*define[ \t]+([A-Za-z_][A-Za-z_0-9]*)", re.M)
ASM_OPEN = re.compile(rb"\basm\b[^;{}]*?\{")
TYPE_BEFORE = re.compile(rb"\b(?:struct|class|union|enum)\s+$")
NEW_BEFORE = re.compile(rb"\bnew\s*(?:\((?:[^()]|\([^()]*\))*\))?\s*$")
MEMBER_BEFORE = re.compile(rb"(?:\.|->|::)\s*$")

_lib = ci.conf.lib
_lib.clang_Cursor_isAnonymousRecordDecl.argtypes = [ci.Cursor]
_lib.clang_Cursor_isAnonymousRecordDecl.restype = ctypes.c_uint
_lib.clang_getSpellingLocation.argtypes = [ci.SourceLocation, ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
                                           ctypes.POINTER(ctypes.c_uint)]
_lib.clang_getSpellingLocation.restype = None
_lib.clang_getFileName.argtypes = [ctypes.c_void_p]
_lib.clang_getFileName.restype = ci._CXString
_lib.clang_getFileName.errcheck = ci._CXString.from_result
_lib.clang_getOverriddenCursors.argtypes = [ci.Cursor, ctypes.POINTER(ctypes.POINTER(ci.Cursor)),
                                            ctypes.POINTER(ctypes.c_uint)]
_lib.clang_getOverriddenCursors.restype = None
_lib.clang_disposeOverriddenCursors.argtypes = [ctypes.POINTER(ci.Cursor)]
_lib.clang_disposeOverriddenCursors.restype = None


def norm(path):
    return os.path.normpath(path).replace("\\", "/")


def args_for(root, path, region):
    lang = ["-x", "c"] if path.endswith(".c") else ["-x", "c++", "-std=gnu++11"]
    defines = ["-Dusa=1", "-Deur=1"] if region == "eur" else [f"-D{region}=1"]
    return lang + ["--target=armv5te-none-eabi", "-fsigned-char", "-I", f"{root}/include", *defines,
                   "-ferror-limit=0", "-Wno-everything", "-fms-extensions", "-fms-compatibility"]


def anon_member(cur):
    return bool(_lib.clang_Cursor_isAnonymousRecordDecl(cur))


def spelling(loc):
    f, line, col, off = ctypes.c_void_p(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    _lib.clang_getSpellingLocation(loc, ctypes.byref(f), ctypes.byref(line), ctypes.byref(col), ctypes.byref(off))
    if not f.value:
        return None, None
    return _lib.clang_getFileName(f), off.value


def overridden(cur):
    out, n = ctypes.POINTER(ci.Cursor)(), ctypes.c_uint()
    _lib.clang_getOverriddenCursors(cur, ctypes.byref(out), ctypes.byref(n))
    if not n.value:
        return []
    found = [out[i] for i in range(n.value)]
    for c in found:
        c._tu = cur._tu
    _lib.clang_disposeOverriddenCursors(out)
    return found


class Scan:
    def __init__(self, root, seen):
        self.root = norm(root) + "/"
        self.seen = seen
        self.decls = {}
        self.refs = set()
        self.links = set()
        self.uses = {}

    def key(self, cur):
        loc = cur.location
        if loc.file is None:
            return None
        name = norm(loc.file.name)
        if not name.startswith(self.root):
            return None
        return f"{name[len(self.root):]}:{loc.offset}"

    def spell_key(self, cur):
        name, off = spelling(cur.location)
        if name is None:
            return None
        name = norm(name)
        if not name.startswith(self.root):
            return None
        return f"{name[len(self.root):]}:{off}"

    def add_ref(self, cur, target, text):
        k = self.key(cur)
        s = self.spell_key(cur)
        if k and s and target and text and IDENT.fullmatch(text):
            self.refs.add((s, target, text, int(s != k)))

    def ident(self, cur):
        if cur is None:
            return None
        return self.key(cur.get_definition() or cur.canonical or cur)

    def type_decl_key(self, typ):
        typ = typ.get_canonical()
        while typ.kind in ARRAYS:
            typ = typ.element_type.get_canonical()
        if typ.kind != ci.TypeKind.RECORD:
            return None
        return self.ident(typ.get_declaration())

    def link(self, a, b):
        if a and b and a != b:
            self.links.add((a, b))

    def named_ancestor(self, rec):
        while rec is not None and rec.kind in RECORDS and anon_member(rec):
            rec = rec.semantic_parent
        return rec if rec is not None and rec.kind in RECORDS else None

    def record(self, cur, k):
        ident = self.ident(cur)
        self.link(k, ident)
        self.link(k, self.key(cur.canonical))
        if not cur.is_anonymous():
            self.add_ref(cur, ident, cur.spelling)
        if not cur.is_definition():
            if ident and not cur.is_anonymous():
                self.decls.setdefault(ident, {"k": "O", "n": cur.spelling})
            return
        if ident != k:
            return
        parent = cur.semantic_parent
        self.decls[k] = {"k": "R", "n": "" if cur.is_anonymous() else cur.spelling, "anon": cur.is_anonymous(),
                         "parent": self.ident(parent) if parent is not None and parent.kind in RECORDS else None}

    def field(self, cur, k):
        rec = cur.semantic_parent
        off = cur.get_field_offsetof()
        owner = rec
        if rec is not None and anon_member(rec):
            owner = self.named_ancestor(rec)
            if owner is not None:
                off = owner.type.get_offset(cur.spelling)
        self.decls[k] = {"k": "F", "n": cur.spelling, "owner": self.ident(owner), "off": off,
                         "bw": cur.get_bitfield_width() if cur.is_bitfield() else None}
        self.add_ref(cur, k, cur.spelling)

    def qualified(self, cur):
        parts = []
        node = cur
        while node is not None and node.kind != K.TRANSLATION_UNIT:
            if node.spelling:
                parts.append(node.spelling)
            node = node.semantic_parent
        return "::".join(reversed(parts))

    def function(self, cur, k):
        ident = self.ident(cur)
        self.link(k, ident)
        parent = cur.semantic_parent
        entry = self.decls.setdefault(ident, {"k": "D", "n": cur.spelling, "q": self.qualified(cur),
                                              "m": cur.mangled_name, "def": False, "cls": None, "sites": []})
        if cur.is_definition():
            entry["def"] = True
            ext = [k.rsplit(":", 1)[0], cur.extent.start.offset, cur.extent.end.offset]
            if ext not in entry.setdefault("exts", []):
                entry["exts"].append(ext)
        if parent is not None and parent.kind in RECORDS:
            entry["cls"] = self.ident(parent)
        if cur.kind == K.CXX_METHOD:
            for base in overridden(cur):
                self.link(ident, self.ident(base))
        entry["sites"].append(k)
        if cur.kind in (K.CONSTRUCTOR, K.DESTRUCTOR) and parent is not None:
            self.add_ref(cur, self.ident(parent), cur.spelling)
        else:
            self.add_ref(cur, ident, cur.spelling)
        index = 0
        for child in cur.get_children():
            if child.kind == K.PARM_DECL:
                pk = self.key(child)
                if pk:
                    self.decls[pk] = {"k": "P", "n": child.spelling, "fn": ident, "i": index}
                    if child.spelling:
                        self.add_ref(child, pk, child.spelling)
                index += 1

    def walk(self, cur, fn, top):
        for child in cur.get_children():
            k = self.key(child)
            if k is None:
                continue
            if top and (k.rsplit(":", 1)[0], top) in self.seen:
                continue
            kind = child.kind
            inner = fn
            if kind in RECORDS:
                self.record(child, k)
            elif kind == K.FIELD_DECL:
                self.field(child, k)
            elif kind == K.TYPEDEF_DECL:
                under = self.type_decl_key(child.underlying_typedef_type)
                ut = child.underlying_typedef_type.get_canonical()
                if ut.kind == ci.TypeKind.ENUM:
                    under = self.ident(ut.get_declaration())
                self.decls[k] = {"k": "T", "n": child.spelling, "under": under,
                                 "utext": child.underlying_typedef_type.spelling,
                                 "ext": [child.extent.start.offset, child.extent.end.offset]}
                self.link(k, self.key(child.canonical))
                self.add_ref(child, self.ident(child), child.spelling)
            elif kind == K.ENUM_DECL:
                ident = self.ident(child)
                self.link(k, ident)
                if child.is_definition() and ident == k:
                    self.decls[k] = {"k": "E", "n": "" if child.is_anonymous() else child.spelling}
                if not child.is_anonymous():
                    self.add_ref(child, ident, child.spelling)
            elif kind == K.ENUM_CONSTANT_DECL:
                self.decls[k] = {"k": "C", "n": child.spelling, "enum": self.ident(child.semantic_parent),
                                 "val": child.enum_value}
                self.add_ref(child, k, child.spelling)
            elif kind in FUNCS:
                self.function(child, k)
                if child.is_definition():
                    inner = self.ident(child)
            elif kind == K.VAR_DECL:
                storage = child.storage_class
                self.decls[k] = {"k": "V", "n": child.spelling, "fn": fn,
                                 "static": storage == ci.StorageClass.STATIC,
                                 "rtype": self.type_decl_key(child.type),
                                 "ptr": child.type.get_canonical().kind == ci.TypeKind.POINTER}
                self.add_ref(child, k, child.spelling)
            elif kind in REFS:
                target = child.referenced
                if target is not None:
                    if target.kind in RECORDS | FUNCS | {K.ENUM_DECL, K.TYPEDEF_DECL}:
                        tk = self.ident(target)
                    else:
                        tk = self.key(target)
                    if tk:
                        self.add_ref(child, tk, target.spelling)
                    if fn and tk and target.kind in RECORDS | FUNCS | {K.TYPEDEF_DECL, K.FIELD_DECL, K.ENUM_DECL,
                                                                       K.ENUM_CONSTANT_DECL}:
                        self.uses.setdefault(fn, set()).add(tk)
                        if target.kind == K.TYPEDEF_DECL:
                            under = self.type_decl_key(target.underlying_typedef_type)
                            if under:
                                self.uses[fn].add(under)
            self.walk(child, inner, False)


def scan_chunk(job):
    root, region, files = job
    index = ci.Index.create()
    seen = set()
    out = []
    for path in files:
        tu = index.parse(f"{root}/{path}", args=args_for(root, path, region))
        scan = Scan(root, seen)
        scan.walk(tu.cursor, None, region)
        for inc in tu.get_includes():
            name = norm(inc.include.name)
            if name.startswith(norm(root) + "/"):
                seen.add((name[len(norm(root)) + 1:], region))
        out.append({"region": region, "decls": scan.decls, "refs": sorted(scan.refs), "links": sorted(scan.links),
                    "uses": {k: sorted(v) for k, v in scan.uses.items()}})
    return out


def mangle_chunk(job):
    root, region, files = job
    index = ci.Index.create()
    prefix = norm(root) + "/"
    found = {}
    for path in files:
        tu = index.parse(f"{root}/{path}", args=args_for(root, path, region))
        for cur in tu.cursor.walk_preorder():
            if cur.kind not in MANGLED or cur.location.file is None:
                continue
            name = norm(cur.location.file.name)
            if name.startswith(prefix) and cur.mangled_name.startswith("_Z"):
                found[(name[len(prefix):], cur.location.offset)] = cur.mangled_name
    return found


def jobs(root, files, regions):
    workers = max(1, min(len(files), (os.cpu_count() or 2) - 2))
    return [(root, region, files[i::workers]) for region in regions for i in range(workers) if files[i::workers]]


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        parent = self.parent
        root = x
        while parent.get(root, root) != root:
            root = parent[root]
        while parent.get(x, x) != root:
            parent[x], x = root, parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if rb < ra:
                ra, rb = rb, ra
            self.parent[rb] = ra


class Model:
    def __init__(self):
        self.decls, self.refs, self.uses = {}, set(), {}
        self.uf = UnionFind()
        self.regions = {}

    def add(self, rec):
        for k, d in rec["decls"].items():
            self.regions.setdefault(k, set()).add(rec["region"])
            old = self.decls.get(k)
            if old is None:
                self.decls[k] = d
            elif d["k"] in ("P", "V") and d["fn"] != old["fn"]:
                old.setdefault("fns", [old["fn"]])
                if d["fn"] not in old["fns"]:
                    old["fns"].append(d["fn"])
            elif d["k"] == "D":
                old["def"] = old["def"] or d["def"]
                old["sites"] = sorted(set(old["sites"]) | set(d["sites"]))
                old["cls"] = old["cls"] or d["cls"]
                for ext in d.get("exts", []):
                    if ext not in old.setdefault("exts", []):
                        old["exts"].append(ext)
        for ref in rec["refs"]:
            self.refs.add(tuple(ref))
        for a, b in rec["links"]:
            self.uf.union(a, b)
        for fn, used in rec["uses"].items():
            self.uses.setdefault(fn, set()).update(used)


def parallel(fn, work):
    if len(work) <= 3:
        yield from map(fn, work)
        return
    with multiprocessing.Pool(min(len(work), max(1, (os.cpu_count() or 2) - 2))) as pool:
        yield from pool.imap_unordered(fn, work)


def scan_tree(root, files, regions):
    model = Model()
    for part in parallel(scan_chunk, jobs(root, files, regions)):
        for rec in part:
            model.add(rec)
    return model


def mangles(root, files, regions):
    found = {}
    for part in parallel(mangle_chunk, jobs(root, files, regions)):
        for (f, off), m in part.items():
            found.setdefault(f, {})[off] = m
    return {f: [m for _, m in sorted(rows.items())] for f, rows in found.items()}


def sources(root):
    return sorted(norm(os.path.relpath(os.path.join(d, f), root)) for d, _, names in os.walk(f"{root}/src")
                  for f in names if f.endswith((".c", ".cpp")))


def addr_tuple(ov, hexa):
    return (int(ov) + 1 if ov else 0, int(hexa, 16), (f"ov{ov}_" if ov else "") + hexa)


def addr_from(text):
    m = ADDR.match(text) if text else None
    return addr_tuple(m.group(1), m.group(2)) if m else None


def addr_in_path(path):
    m = STEM.search(os.path.basename(path)) or BARE.search(os.path.basename(path))
    if not m:
        return None
    ov = m.group(1)
    if ov is None:
        d = OVDIR.search(path)
        ov = f"{int(d.group(1)):03d}" if d else None
    return addr_tuple(ov, m.group(2))


def symbol_tables(root):
    addrs, names = {}, set()
    for path in glob.glob(f"{root}/config/*/arm9/**/symbols.txt", recursive=True):
        path = norm(path)
        usa = "/config/usa/" in path
        m = re.search(r"overlays/ov(\d{3})/", path)
        for line in open(path, encoding="utf-8"):
            parts = line.split()
            if not parts:
                continue
            names.add(parts[0])
            a = re.search(r"addr:0x([0-9a-fA-F]{8})", line)
            if usa and a and len(parts) > 1 and parts[1].startswith("kind:function"):
                addrs[parts[0]] = addr_tuple(m.group(1) if m else None, a.group(1).lower())
    return addrs, names


def upstream_tree(repo):
    url, branch = kitpaths.UPSTREAM_URL, kitpaths.UPSTREAM_BRANCH
    if subprocess.run(["git", "-C", repo, "fetch", "-q", url, branch], capture_output=True).returncode:
        cached = sorted(glob.glob(f"{kitpaths.SP}/plainnames/upstream-*/src"), key=os.path.getmtime)
        if not cached:
            sys.exit(f"FETCH FAILED {url} {branch}")
        return norm(os.path.dirname(cached[-1]))
    rev = subprocess.run(["git", "-C", repo, "rev-parse", "FETCH_HEAD"], capture_output=True, text=True).stdout.strip()
    dest = f"{kitpaths.SP}/plainnames/upstream-{rev[:12]}"
    if not os.path.isdir(f"{dest}/src"):
        tops = subprocess.run(["git", "-C", repo, "ls-tree", "--name-only", rev], capture_output=True,
                              text=True).stdout.split()
        data = subprocess.run(["git", "-C", repo, "archive", rev, *[t for t in ("src", "include", "config") if t in tops]],
                              capture_output=True, check=True).stdout
        os.makedirs(f"{dest}/src", exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest)
    return dest


class Upstream:
    def __init__(self, root):
        model = scan_tree(root, sources(root), ("usa",))
        self.recs, self.typedefs, self.enums, self.consts = set(), set(), set(), set()
        self.funcs, self.defs, self.declsites = set(), set(), set()
        self.fields = collections.defaultdict(set)
        for k, d in model.decls.items():
            kind, n = d["k"], d["n"]
            if kind in ("R", "O") and n:
                self.recs.add(n)
            elif kind == "T":
                self.typedefs.add(n)
            elif kind == "E" and n:
                self.enums.add(n)
            elif kind == "C":
                self.consts.add(n)
            elif kind == "D":
                self.funcs.add(d["q"])
                if d["m"]:
                    self.funcs.add(d["m"])
                if d["def"]:
                    self.defs.add(d["q"])
                for site in d["sites"]:
                    self.declsites.add((site.rsplit(":", 1)[0], d["q"]))
        for d in model.decls.values():
            if d["k"] == "F":
                self.fields[(model.decls.get(d["owner"]) or {}).get("n", "")].add(d["n"])
        self.symbols = symbol_tables(root)[1]


def asm_ranges(data):
    ranges = []
    for m in ASM_OPEN.finditer(data):
        depth, i = 0, m.end() - 1
        while i < len(data):
            c = data[i:i + 1]
            if c == b"{":
                depth += 1
            elif c == b"}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        ranges.append((m.end() - 1, i + 1))
    return ranges


class Planner:
    def __init__(self, tree, model, up, only=None):
        self.tree = tree
        self.up = up
        self.only = only
        self.decls, self.refs, self.uf = model.decls, model.refs, model.uf
        self.decl_regions = model.regions
        self.syms, self.symnames = symbol_tables(tree)
        self.symnames |= up.symbols
        self.find = self.uf.find
        self.file_cache = {}
        self.asm_cache = {}
        by_site = collections.defaultdict(set)
        for site, target, text, macro in self.refs:
            if not macro:
                by_site[site].add((target, text))
        for site, pairs in by_site.items():
            if len(pairs) < 2 or len({text for _, text in pairs}) > 1:
                continue
            by_kind = collections.defaultdict(list)
            for t, _ in pairs:
                d = self.decls.get(t)
                if d:
                    by_kind[{"O": "R", "P": "L", "V": "L"}.get(d["k"], d["k"])].append(t)
            for targets in by_kind.values():
                targets.sort()
                for t in targets[1:]:
                    self.uf.union(targets[0], t)
        self.unify_by_name()
        self.unify_variant_functions()
        self.uses = collections.defaultdict(set)
        for fn, used in model.uses.items():
            self.uses[self.find(fn)].update(used)
        self.group_names, self.key_names, self.deletions = {}, {}, []
        self.taken = set(up.recs) | set(up.typedefs) | set(up.enums)
        self.taken |= {d["n"] for d in self.decls.values()
                       if d["k"] in ("R", "O", "E", "T", "C") and d["n"] and PLAIN.fullmatch(d["n"])}
        self.site_files = collections.defaultdict(set)
        for site, target, _, _ in self.refs:
            self.site_files[self.find(target)].add(site.rsplit(":", 1)[0])

    def unify_by_name(self):
        named = collections.defaultdict(list)
        rec_name = {k: d["n"] for k, d in self.decls.items() if d["k"] == "R" and d["n"]}
        for k, d in self.decls.items():
            kind = d["k"]
            if kind == "R" and d["n"]:
                named[("R", f"{rec_name.get(d['parent'], '') if d['parent'] else ''}::{d['n']}")].append(k)
            elif kind == "O" and d["n"]:
                named[("R", f"::{d['n']}")].append(k)
            elif kind in ("E", "T") and d["n"]:
                named[(kind, d["n"])].append(k)
            elif kind == "D":
                named[("D", d["q"])].append(k)
        for keys in named.values():
            for k in keys[1:]:
                self.uf.union(keys[0], k)

    def unify_variant_functions(self):
        fns = collections.defaultdict(set)
        for k, d in self.decls.items():
            if d["k"] in ("P", "V") and d["fn"]:
                fns[self.find(k)].update(d.get("fns", [d["fn"]]))
        for group in fns.values():
            group = sorted(group)
            for fn in group[1:]:
                self.uf.union(group[0], fn)

    def text(self, file):
        data = self.file_cache.get(file)
        if data is None:
            data = self.file_cache[file] = open(f"{self.tree}/{file}", "rb").read()
        return data

    def primary(self, items):
        return min(items, key=lambda kd: ("usa" not in self.decl_regions.get(kd[0], ()), kd[0]))

    def by_root(self, kind):
        groups = collections.defaultdict(list)
        for k, d in self.decls.items():
            if d["k"] == kind:
                groups[self.find(k)].append((k, d))
        return groups

    def functions(self):
        self.funcs = self.by_root("D")
        self.fn_addr, self.fn_upstream, self.fn_updef, self.fn_sym = {}, set(), set(), set()
        for root, items in self.funcs.items():
            names = {x["q"] for _, x in items} | {x["m"] for _, x in items if x["m"]}
            if names & self.symnames:
                self.fn_sym.add(root)
            addr = None
            for n in sorted(names):
                addr = addr or addr_from(n) or self.syms.get(n)
            self.fn_addr[root] = addr
            if names & self.up.funcs:
                self.fn_upstream.add(root)
            if any(x["q"] in self.up.defs for _, x in items):
                self.fn_updef.add(root)

    def indexes(self):
        users = collections.defaultdict(set)
        for fn, used in self.uses.items():
            a = self.fn_addr.get(fn)
            if not a:
                continue
            for t in used:
                users[self.find(t)].add(a)
                d = self.decls.get(t)
                if d and d["k"] == "F":
                    users[self.find(d["owner"])].add(a)
                elif d and d["k"] == "C" and d.get("enum"):
                    users[self.find(d["enum"])].add(a)
        self.user_addr = {k: min(v) for k, v in users.items()}
        found = collections.defaultdict(list)
        for d in self.decls.values():
            if d["k"] == "V" and d["fn"] is None and d["rtype"] and not d["ptr"]:
                a = addr_from(d["n"])
                if a:
                    found[self.find(d["rtype"])].append(a)
        self.instance_addr = {k: min(v) for k, v in found.items()}
        files = collections.defaultdict(set)
        for root, a in self.fn_addr.items():
            if a:
                for _, d in self.funcs[root]:
                    for site in d["sites"]:
                        files[site.rsplit(":", 1)[0]].add(a)
        for root, a in list(self.user_addr.items()) + list(self.instance_addr.items()):
            for f in self.site_files.get(root, ()):
                files[f].add(a)
        self.file_addr = {f: min(v) for f, v in files.items()}

    def fallback(self, root):
        best = None
        for f in self.site_files.get(root, ()):
            for a in (addr_in_path(f), self.file_addr.get(f)):
                if a and (best is None or a < best):
                    best = a
        return best

    def address_for(self, root, instance=True):
        if instance and root in self.instance_addr:
            return self.instance_addr[root]
        return self.user_addr.get(root) or self.fallback(root)

    def unique(self, base, pool):
        name, n = base, 1
        while name in pool:
            n += 1
            name = f"{base}_{n}"
        pool.add(name)
        return name

    def unique_letter(self, base, pool):
        name, n = base, 0
        while name in pool:
            n += 1
            letters, v = "", n
            while v:
                v, r = divmod(v, 26)
                letters = chr(ord("A") + r) + letters
            name = f"{base}_{letters}"
        pool.add(name)
        return name

    def upstream_type(self, name):
        return name in self.up.recs or name in self.up.enums or name in self.up.typedefs

    def assign_types(self):
        recs, enums, opaque, typedefs = self.by_root("R"), self.by_root("E"), self.by_root("O"), self.by_root("T")
        kinds = {root: "R" for root in recs}
        kinds.update({root: "E" for root in enums})
        for root in opaque:
            kinds.setdefault(root, "O")
        for root in sorted(kinds, key=lambda r: (self.address_for(r) or (99, 0, ""), r)):
            source = {"R": recs, "E": enums}.get(kinds[root], opaque)
            names = [d["n"] for _, d in source.get(root, []) if d["n"]]
            old = names[0] if names else ""
            if not old or self.upstream_type(old) or PLAIN.fullmatch(old):
                continue
            addr = self.address_for(root)
            if not addr:
                continue
            if kinds[root] == "E":
                self.group_names[root] = (old, self.unique_letter("Enum_" + addr[2], self.taken))
            else:
                self.group_names[root] = (old, self.unique("Struct_" + addr[2], self.taken))
        for root, items in typedefs.items():
            d = items[0][1]
            old = d["n"]
            if self.upstream_type(old) or PLAIN.fullmatch(old):
                continue
            if SIZE_CHECK.match(d["utext"].strip()) and root not in self.used_roots:
                self.deletions.extend((k, x["ext"]) for k, x in items)
                continue
            under = self.find(d["under"]) if d["under"] else None
            if under and under in self.group_names:
                self.group_names[root] = (old, self.group_names[under][1])
                continue
            addr = self.address_for(root, instance=False)
            if addr:
                self.group_names[root] = (old, self.unique("Type_" + addr[2], self.taken))

    def assign_functions(self):
        resolved = {}
        callers = collections.defaultdict(set)
        for fn, used in self.uses.items():
            for t in used:
                r = self.find(t)
                if r in self.funcs and r != fn:
                    callers[r].add(fn)
        inline = set()

        def resolve(root, stack=()):
            if root in resolved:
                return resolved[root]
            best = None
            for fn in callers.get(root, ()):
                a = self.fn_addr.get(fn)
                if not a and fn not in stack and fn in inline:
                    a = resolve(fn, stack + (root,))
                if a and (best is None or a < best):
                    best = a
            resolved[root] = best
            return best

        recs = self.by_root("R")
        for root, items in self.funcs.items():
            d = items[0][1]
            n = d["n"]
            if root in self.fn_upstream or n.startswith(SPECIAL) or n.startswith("__") or PLAIN.fullmatch(n):
                continue
            cls = self.find(d["cls"]) if d["cls"] else None
            if cls and n == next((x["n"] for _, x in recs.get(cls, []) if x["n"]), None):
                continue
            if not cls and not any(x["def"] for _, x in items):
                continue
            inline.add(root)
        pool = {d["n"] for d in self.decls.values() if d["k"] == "D" and PLAIN.fullmatch(d["n"])}
        for root in sorted(inline):
            d = self.funcs[root][0][1]
            addr = self.fn_addr.get(root)
            if addr or root in self.fn_sym:
                cls = self.find(d["cls"]) if d["cls"] else None
                if cls in self.group_names and addr:
                    self.group_names[root] = (d["n"], f"func_{addr[2]}")
                continue
            a = resolve(root)
            if not a and not any(x["def"] for _, x in self.funcs[root]) and d["cls"]:
                a = self.address_for(self.find(d["cls"]))
            a = a or self.fallback(root)
            if a:
                self.group_names[root] = (d["n"], self.unique(f"inline_{a[2]}", pool))

    def assign_fields(self):
        groups = collections.defaultdict(list)
        for k, d in self.decls.items():
            if d["k"] == "F" and d["n"] and d["owner"]:
                groups[self.find(k)].append((k, d))
        pools = collections.defaultdict(set)
        kept = set()
        for root, variants in groups.items():
            for _, d in variants:
                oname = (self.decls.get(d["owner"]) or {}).get("n", "")
                if (oname in self.up.recs and d["n"] in self.up.fields.get(oname, ())) or PLAIN.fullmatch(d["n"]):
                    kept.add(root)
                    pools[d["owner"]].add(d["n"])
        order = []
        for root, variants in groups.items():
            if root not in kept:
                k, d = self.primary(variants)
                order.append((d["owner"], d["off"] if d["off"] is not None else -1, k, root))
        for _, _, _, root in sorted(order):
            _, d = self.primary(groups[root])
            off = d["off"]
            if off is None or off < 0:
                continue
            owners = {x["owner"] for _, x in groups[root]}
            byte, bit = divmod(off, 8)
            tail = f"{byte:x}_{bit}_" if d["bw"] is not None else f"{byte:x}_"
            name, n = f"unknown_{tail}", 0
            while any(name in pools[o] for o in owners):
                n += 1
                name = f"unknown{n}_{tail}"
            for o in owners:
                pools[o].add(name)
            self.key_names[root] = name

    def assign_enumerators(self):
        by_enum = collections.defaultdict(list)
        for k, d in self.decls.items():
            if d["k"] == "C" and d["enum"]:
                by_enum[self.find(d["enum"])].append((k, d))
        bases = {}
        for root, items in by_enum.items():
            if all(d["n"] in self.up.consts for _, d in items):
                continue
            if root in self.group_names:
                bases[root] = self.group_names[root][1]
                continue
            addr = self.address_for(root)
            for k, _ in items:
                f = k.rsplit(":", 1)[0]
                addr = addr or addr_in_path(f) or self.file_addr.get(f)
            if addr:
                bases[root] = "Enum_" + addr[2]
        groups = collections.defaultdict(list)
        for k, d in self.decls.items():
            if d["k"] == "C" and d["enum"]:
                groups[self.find(k)].append((k, d))
        for croot, members in sorted(groups.items(), key=lambda x: self.primary(x[1])[0]):
            _, d = self.primary(members)
            base = bases.get(self.find(d["enum"]))
            if base and d["n"] not in self.up.consts and not PLAIN.fullmatch(d["n"]):
                v = d["val"]
                self.key_names[croot] = self.unique(f"{base}_{'m' if v < 0 else ''}{abs(v)}", self.taken)

    def spelled_here(self, key, name):
        file, off = key.rsplit(":", 1)
        off = int(off)
        return self.text(file)[off:off + len(name)] == name.encode()

    def in_asm(self, key):
        file, off = key.rsplit(":", 1)
        if file not in self.asm_cache:
            self.asm_cache[file] = asm_ranges(self.text(file))
        off = int(off)
        return any(a <= off < b for a, b in self.asm_cache[file])

    def is_asm(self, root):
        for _, d in self.funcs.get(root, []):
            for site in d["sites"]:
                file, off = site.rsplit(":", 1)
                data, off = self.text(file), int(off)
                start = max(data.rfind(b";", 0, off), data.rfind(b"}", 0, off), data.rfind(b"\n#", 0, off))
                if re.search(rb"\basm\b", data[start + 1:off]):
                    return True
        return False

    def assign_locals(self):
        members = collections.defaultdict(list)
        for k, d in self.decls.items():
            if d["k"] in ("P", "V") and d["fn"] and d["n"]:
                members[self.find(d["fn"])].append((k, d))
        for root, items in members.items():
            if root in self.fn_updef or self.is_asm(root):
                continue
            quals = {x["q"] for _, x in self.funcs.get(root, [])}
            slots = collections.defaultdict(list)
            for k, d in items:
                file = k.rsplit(":", 1)[0]
                if d["k"] == "P" and any((file, q) in self.up.declsites for q in quals):
                    continue
                if self.in_asm(k) or not self.spelled_here(k, d["n"]) or (d["k"] == "V" and d["static"]):
                    continue
                slots[self.find(k)].append((k, d))
            copies = collections.defaultdict(list)
            for sroot, variants in slots.items():
                head = self.primary(variants)
                copies[head[0].rsplit(":", 1)[0]].append((head, sroot))
            for heads in copies.values():
                heads.sort(key=lambda x: int(x[0][0].rsplit(":", 1)[1]))
                used = {d["n"] for (_, d), _ in heads if d["k"] == "V" and LOCAL.fullmatch(d["n"])}
                n = 0
                for (k, d), sroot in heads:
                    if d["k"] == "P":
                        self.key_names[sroot] = f"arg{d['i']}"
                        continue
                    if d["n"] in used:
                        continue
                    while f"var{n}" in used:
                        n += 1
                    self.key_names[sroot] = f"var{n}"
                    used.add(f"var{n}")

    def bodies(self):
        by_file = collections.defaultdict(list)
        for k, d in self.decls.items():
            if d["k"] in ("P", "V") and d["fn"] and d["n"]:
                file, off = k.rsplit(":", 1)
                by_file[file].append((int(off), k))
        for rows in by_file.values():
            rows.sort()
        members = collections.defaultdict(set)
        for d in self.decls.values():
            if d["k"] == "F" and d["owner"]:
                members[self.find(d["owner"])].add(d["n"])
            elif d["k"] == "D" and d["cls"]:
                members[self.find(d["cls"])].add(d["n"])
        out, seen = [], set()
        for root, items in self.funcs.items():
            for _, d in items:
                hidden = members.get(self.find(d["cls"]), set()) if d["cls"] else set()
                for file, start, end in d.get("exts", []):
                    if (file, start) in seen or not self.allowed_file(file):
                        continue
                    seen.add((file, start))
                    rows = by_file.get(file, [])
                    i = bisect.bisect_left(rows, (start, ""))
                    mapping, clash = {}, set()
                    while i < len(rows) and rows[i][0] < end:
                        k = rows[i][1]
                        i += 1
                        x = self.decls[k]
                        new = self.key_names.get(self.find(k))
                        if not new or new == x["n"] or not self.allowed(self.find(k)):
                            continue
                        if mapping.get(x["n"], new) != new:
                            clash.add(x["n"])
                        mapping[x["n"]] = new
                    for name in clash | hidden:
                        mapping.pop(name, None)
                    if mapping:
                        out.append([file, start, end, mapping])
        return out

    def allowed_file(self, file):
        return self.only is None or file in self.only

    def allowed(self, root):
        if self.only is None:
            return True
        return all(f in self.only for f in self.decl_files.get(root, ()))

    def run(self):
        self.functions()
        self.used_roots = {self.find(t) for site, t, _, _ in self.refs if site != t}
        self.indexes()
        self.assign_types()
        self.assign_functions()
        self.assign_fields()
        self.assign_enumerators()
        self.assign_locals()
        self.decl_files = collections.defaultdict(set)
        for k in self.decls:
            self.decl_files[self.find(k)].add(k.rsplit(":", 1)[0])
        wanted = collections.defaultdict(set)
        renamed = {}
        for site, target, text, _ in self.refs:
            root = self.find(target)
            new = self.key_names.get(root) or (self.group_names[root][1] if root in self.group_names else None)
            if new and not self.allowed(root):
                new = None
            if text.startswith("~") and new:
                new = "~" + new
            wanted[site].add((text, new or text))
            if new and new.lstrip("~") != text.lstrip("~"):
                renamed[root] = (text.lstrip("~"), new.lstrip("~"))
        edits = collections.defaultdict(list)
        for site, pairs in wanted.items():
            file, off = site.rsplit(":", 1)
            if not self.allowed_file(file):
                continue
            changes = sorted((old, new) for old, new in pairs if old != new)
            olds = [old for old, _ in pairs]
            if not changes or len(set(olds)) != len(olds):
                continue
            for old, new in changes:
                edits[file].append([int(off), old, new, len(pairs)])
        deletions = [(k, ext) for k, ext in self.deletions if self.allowed_file(k.rsplit(":", 1)[0])]
        olds = collections.defaultdict(set)
        for root, (old, new) in self.group_names.items():
            if old and new.startswith(("Struct_", "Enum_")) and self.allowed(root):
                olds[old].add(new)
        return {"edits": dict(edits), "deletions": deletions, "bodies": self.bodies(),
                "types": {old: next(iter(news)) for old, news in olds.items() if len(news) == 1},
                "renamed": renamed}


def whole_word(data, off, word):
    if data[off:off + len(word)] != word:
        return False
    before = data[off - 1:off] if off else b""
    after = data[off + len(word):off + len(word) + 1]
    return not (before and WORD.match(before)) and not (after and WORD.match(after))


def locate(data, off, old):
    if whole_word(data, off, old):
        return off
    window = data[off:off + 48]
    m = re.search(rb"(?<![A-Za-z_0-9])" + re.escape(old) + rb"(?![A-Za-z_0-9])", window)
    if m and not re.search(rb"[;{}()\[\]=,]", window[:m.start()]):
        return off + m.start()
    return None


def deletion_span(data, start, end):
    if not data[start:end].startswith(b"typedef"):
        return None
    stop = end
    while stop < len(data) and data[stop:stop + 1] in b" \t":
        stop += 1
    if data[stop:stop + 1] != b";":
        return None
    stop += 1
    line_start = data.rfind(b"\n", 0, start) + 1
    if data[line_start:start].strip() == b"":
        while stop < len(data) and data[stop:stop + 1] in b" \t":
            stop += 1
        stop += 2 if data[stop:stop + 2] == b"\r\n" else 1 if data[stop:stop + 1] == b"\n" else 0
        start = line_start
    return start, stop


def code_mask(data):
    mask = bytearray(b"\x01") * len(data)
    i, n = 0, len(data)
    while i < n:
        c = data[i:i + 1]
        if c == b"/" and data[i + 1:i + 2] == b"/":
            j = data.find(b"\n", i)
            j = n if j < 0 else j
        elif c == b"/" and data[i + 1:i + 2] == b"*":
            j = data.find(b"*/", i + 2)
            j = n if j < 0 else j + 2
        elif c in (b'"', b"'"):
            j = i + 1
            while j < n and data[j:j + 1] != c:
                j += 2 if data[j:j + 1] == b"\\" else 1
            j = min(n, j + 1)
        else:
            i += 1
            continue
        mask[i:j] = b"\x00" * (j - i)
        i = j
    return mask


def type_context(data, start, end):
    after = data[end:end + 6].lstrip(b" \t")
    if after.startswith((b"::", b"*", b"&")):
        return True
    before = data[max(0, start - 80):start]
    return bool(TYPE_BEFORE.search(before[-12:]) or NEW_BEFORE.search(before))


def macro_body(data, start):
    nl = start
    while True:
        end = data.find(b"\n", nl)
        if end < 0:
            end = len(data)
            break
        if not data[nl:end].rstrip(b"\r").endswith(b"\\"):
            break
        nl = end + 1
    m = re.match(rb"[ \t]*#[ \t]*define[ \t]+[A-Za-z_][A-Za-z_0-9]*(\(([^)]*)\))?", data[start:end])
    params = {p.strip() for p in m.group(2).split(b",") if p.strip()} if m.group(1) else set()
    return start + m.end(), end, params


class Applier:
    def __init__(self, tree, plan, skip=None):
        self.tree, self.plan, self.skip = tree, plan, skip or {}
        self.data = {}
        self.spans = collections.defaultdict(list)
        self.asm_ok = collections.defaultdict(set)
        self.wants = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(set)))
        self.conflicts = collections.defaultdict(set)
        self.defines = collections.defaultdict(list)
        self.misses = []

    def read(self, rel):
        if rel not in self.data:
            self.data[rel] = open(f"{self.tree}/{rel}", "rb").read()
        return self.data[rel]

    def index_defines(self):
        for top in ("include", "src"):
            for root, _, names in os.walk(f"{self.tree}/{top}"):
                for name in names:
                    if name.endswith((".h", ".hpp", ".c", ".cpp", ".inc")):
                        rel = norm(os.path.relpath(os.path.join(root, name), self.tree))
                        for m in DEFINE.finditer(self.read(rel)):
                            self.defines[m.group(1)].append((rel, m.start()))

    def macro_for(self, rel, name):
        sites = self.defines.get(name, [])
        if any(s[0] == rel for s in sites):
            return rel, name
        headers = {s[0] for s in sites if s[0].startswith("include/")}
        return (headers.pop(), name) if len(headers) == 1 else None

    def run(self):
        deletions = collections.defaultdict(list)
        for key, (start, end) in self.plan["deletions"]:
            deletions[key.rsplit(":", 1)[0]].append((start, end))
        for rel in sorted(set(self.plan["edits"]) | set(deletions)):
            data = self.read(rel)
            for start, end in deletions.get(rel, []):
                span = deletion_span(data, start, end)
                if span:
                    self.spans[rel].append((span[0], span[1], b""))
            for off, old, new, width in self.plan["edits"].get(rel, []):
                if (old, new) in self.skip.get(rel, ()):
                    continue
                old_b, new_b = old.encode(), new.encode()
                if old_b.startswith(b"~"):
                    old_b, new_b = old_b[1:], new_b.lstrip(b"~")
                at = locate(data, off, old_b) if width == 1 else None
                if at is not None:
                    self.spans[rel].append((at, at + len(old_b), new_b))
                    continue
                m = BNAME.match(data, off)
                macro = self.macro_for(rel, m.group(0)) if m else None
                if macro:
                    self.wants[macro][old_b][new_b].add(rel)
                else:
                    self.misses.append(f"{rel}:{off} {old} -> {new}")
        for (rel, name), wants in self.wants.items():
            data = self.read(rel)
            bodies = [macro_body(data, start) for f, start in self.defines[name] if f == rel]
            for old_b, news in wants.items():
                if len(news) > 1:
                    for new_b, sources in news.items():
                        for src in sources:
                            self.conflicts[src].add((old_b.decode(), new_b.decode()))
                    self.misses.append(f"{rel} macro {name.decode()} uses {old_b.decode()} as "
                                       f"{b', '.join(news).decode()}")
                    continue
                new_b = next(iter(news))
                for body_start, body_end, params in bodies:
                    if old_b in params:
                        continue
                    for m in re.finditer(rb"(?<![A-Za-z_0-9])" + re.escape(old_b) + rb"(?![A-Za-z_0-9])",
                                         data[body_start:body_end]):
                        self.spans[rel].append((body_start + m.start(), body_start + m.end(), new_b))

    def leftovers(self):
        types = {k.encode(): v.encode() for k, v in self.plan["types"].items()}
        for rel in list(self.spans):
            data = self.data[rel]
            starts = {s[0] for s in self.spans[rel]}
            mask = None
            for m in BIDENT.finditer(data):
                new = types.get(m.group(0))
                if not new or m.start() in starts or not type_context(data, m.start(), m.end()):
                    continue
                mask = mask or code_mask(data)
                if mask[m.start()]:
                    self.spans[rel].append((m.start(), m.end(), new))
        for rel, start, end, mapping in self.plan["bodies"]:
            data = self.read(rel)
            starts = {s[0] for s in self.spans[rel]}
            skipped = self.skip.get(rel, set())
            words = {k.encode(): v.encode() for k, v in mapping.items() if (k, v) not in skipped}
            mask = None
            for m in BIDENT.finditer(data, start, end):
                new = words.get(m.group(0))
                if not new or m.start() in starts or MEMBER_BEFORE.search(data[max(0, m.start() - 4):m.start()]):
                    continue
                mask = mask or code_mask(data)
                if mask[m.start()]:
                    self.spans[rel].append((m.start(), m.end(), new))
                    self.asm_ok[rel].add(m.start())
                    starts.add(m.start())

    def results(self):
        out = {}
        for rel, spans in self.spans.items():
            data = self.data[rel]
            blocked = asm_ranges(data)
            ok = self.asm_ok.get(rel, set())
            spans = sorted(s for s in spans if s[0] in ok or not any(a <= s[0] < b for a, b in blocked))
            kept, last = [], -1
            for s in spans:
                if s[0] < last:
                    if not (kept and (kept[-1] == s or (kept[-1][2] == b"" and s[1] <= kept[-1][1]))):
                        self.misses.append(f"{rel}:{s[0]} overlaps {s[2].decode()}")
                    continue
                kept.append(s)
                last = s[1]
            parts, pos = [], 0
            for start, stop, text in kept:
                parts += [data[pos:start], text]
                pos = stop
            parts.append(data[pos:])
            result = b"".join(parts)
            if result != data:
                out[rel] = result
        return out


def apply_plan(tree, plan):
    probe = Applier(tree, plan)
    probe.index_defines()
    probe.run()
    applier = Applier(tree, plan, probe.conflicts)
    applier.index_defines()
    applier.run()
    applier.leftovers()
    return applier.results(), applier.misses


def fix_symbols(tree, before, after, files):
    mapping = collections.defaultdict(set)
    for f in files:
        old, new = before.get(f, []), after.get(f, [])
        if len(old) == len(new):
            for a, b in zip(old, new):
                if a != b:
                    mapping[a].add(b)
    flat = {k: next(iter(v)) for k, v in mapping.items() if len(v) == 1}
    used = set()
    for path in glob.glob(f"{tree}/config/*/arm9/**/symbols.txt", recursive=True):
        lines = open(path, encoding="utf-8", newline="").read().split("\n")
        changed = False
        for i, line in enumerate(lines):
            name, sep, rest = line.partition(" ")
            if name in flat:
                lines[i] = flat[name] + sep + rest
                used.add(name)
                changed = True
        if changed:
            open(path, "w", encoding="utf-8", newline="").write("\n".join(lines))
    if not used:
        return 0
    pattern = re.compile(rb"(?<![A-Za-z_0-9])(" + b"|".join(re.escape(o.encode()) for o in sorted(used, key=len, reverse=True))
                         + rb")(?![A-Za-z_0-9])")
    for top in ("src", "include"):
        for path in glob.glob(f"{tree}/{top}/**/*", recursive=True):
            if path.endswith((".c", ".cpp", ".h", ".hpp", ".inc", ".s")):
                data = open(path, "rb").read()
                new, n = pattern.subn(lambda m: flat[m.group(1).decode()].encode(), data)
                if n:
                    open(path, "wb").write(new)
    return len(used)


def line_of(tree, key):
    file, off = key.rsplit(":", 1)
    data = open(f"{tree}/{file}", "rb").read()
    return file, data.count(b"\n", 0, int(off)) + 1


def plan_for(tree, files, only):
    up = Upstream(upstream_tree(tree))
    model = scan_tree(tree, files, REGIONS)
    planner = Planner(tree, model, up, only)
    return planner, planner.run()


def check(tree, files):
    only = set(files)
    planner, plan = plan_for(tree, files, only)
    problems = []
    for root, (old, new) in sorted(plan["renamed"].items()):
        sites = sorted(k for k in planner.decls if planner.find(k) == root and k.rsplit(":", 1)[0] in only)
        if sites:
            file, line = line_of(tree, sites[0])
            problems.append(f"NOT A PLAIN NAME {file}:{line} {old}: write {new}")
    return problems


def fix(tree, files, whole=False):
    only = None if whole else set(files)
    targets = files if not whole else sources(tree)
    before = mangles(tree, targets, REGIONS)
    planner, plan = plan_for(tree, targets, only)
    results, misses = apply_plan(tree, plan)
    for rel, data in results.items():
        open(f"{tree}/{rel}", "wb").write(data)
    after = mangles(tree, targets, REGIONS)
    symbols = fix_symbols(tree, before, after, targets)
    return sorted(results), misses, symbols


def main():
    args = sys.argv[1:]
    tree = kitpaths.REPO
    if "--tree" in args:
        i = args.index("--tree")
        tree, args = norm(args[i + 1]), args[:i] + args[i + 2:]
    if not args or args[0] not in ("check", "fix", "tree") or (args[0] != "tree" and len(args) < 2):
        sys.exit(__doc__)
    files = [norm(f) for f in args[1:]]
    if args[0] == "check":
        problems = check(tree, files)
        print("\n".join(problems) if problems else "PLAIN")
        sys.exit(1 if problems else 0)
    changed, misses, symbols = fix(tree, files, whole=args[0] == "tree")
    for line in misses:
        print(f"UNRESOLVED {line}")
    print(f"plain names: {len(changed)} file(s) changed, {symbols} symbol(s) renamed")


if __name__ == "__main__":
    main()
