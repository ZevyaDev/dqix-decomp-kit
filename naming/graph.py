"""Symbols, relocations and source locations of one region's decomp config, for the naming pass."""
import bisect
import collections
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kitpaths

CALLS = {"arm_call", "arm_call_thumb", "thumb_call", "thumb_call_arm"}
SYMBOL = re.compile(r"^(\S+) kind:(function|data|bss)(?:\(([^)]*)\))? addr:0x([0-9a-fA-F]+)", re.M)
SIZE = re.compile(r"size=0x([0-9a-fA-F]+)|\[(\d+)\]")
RELOC = re.compile(r"^from:0x([0-9a-fA-F]+) kind:(\w+) to:0x([0-9a-fA-F]+) module:(\S+)", re.M)
OVERLAY = re.compile(r"overlay\((\d+)\)")
BLOCK = re.compile(r"^(\S[^\n]*?):\s*$((?:\n[ \t]+\S[^\n]*)*)", re.M)
RANGE = re.compile(r"\.(?:text|init|data|rodata|bss|ctor)\s+start:0x([0-9a-fA-F]+)\s+end:0x([0-9a-fA-F]+)")
ASCII = re.compile(rb"[\x20-\x7e]{4,}\x00")


class Symbol:
    __slots__ = ("name", "kind", "module", "addr", "size")

    def __init__(self, name, kind, module, addr, size):
        self.name, self.kind, self.module, self.addr, self.size = name, kind, module, addr, size

    @property
    def key(self):
        return (self.module, self.addr)


class Graph:
    def __init__(self, region="usa", repo=None):
        self.repo = repo or kitpaths.REPO
        self.region = region
        base = f"{self.repo}/config/{region}/arm9"
        dirs = {"main": base, "itcm": f"{base}/itcm", "dtcm": f"{base}/dtcm"}
        for d in sorted(glob.glob(f"{base}/overlays/ov*")):
            dirs[os.path.basename(d)] = d.replace("\\", "/")
        self.dirs = {m: d for m, d in dirs.items() if os.path.isfile(f"{d}/symbols.txt")}
        self.tables, self.by_key, self.by_name = {}, {}, {}
        for m, d in self.dirs.items():
            with open(f"{d}/symbols.txt", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            rows = []
            for name, kind, spec, addr in SYMBOL.findall(text):
                s = SIZE.search(spec)
                size = int(s.group(1), 16) if s and s.group(1) else int(s.group(2)) if s else 0
                sym = Symbol(name, "func" if kind == "function" else "data", m, int(addr, 16), max(size, 1))
                rows.append(sym)
                self.by_key[sym.key] = sym
                self.by_name.setdefault(name, sym)
            rows.sort(key=lambda s: s.addr)
            self.tables[m] = (rows, [s.addr for s in rows])
        self.callers = collections.defaultdict(set)
        self.callees = collections.defaultdict(set)
        self.refs = collections.defaultdict(set)
        self.loads = collections.defaultdict(set)
        for m, d in self.dirs.items():
            path = f"{d}/relocs.txt"
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for frm, kind, to, field in RELOC.findall(text):
                src = self.owner(m, int(frm, 16))
                target = self.by_key.get((self.target_module(field, m), int(to, 16)))
                if not src or not target:
                    continue
                if kind in CALLS:
                    self.callers[target.key].add(src.key)
                    self.callees[src.key].add(target.key)
                else:
                    self.refs[target.key].add(src.key)
                    self.loads[src.key].add(target.key)
        self._files = None
        self._binaries = {}

    @staticmethod
    def target_module(field, src_module):
        m = OVERLAY.fullmatch(field)
        if m:
            return f"ov{int(m.group(1)):03d}"
        return field if field in ("main", "itcm", "dtcm") else src_module

    def owner(self, module, addr):
        rows, starts = self.tables[module]
        i = bisect.bisect_right(starts, addr) - 1
        if i >= 0 and rows[i].kind == "func" and rows[i].addr <= addr < rows[i].addr + rows[i].size:
            return rows[i]
        return None

    def lookup(self, text):
        if text in self.by_name:
            return self.by_name[text]
        m = re.fullmatch(r"(?:\w+_)?(?:ov(\d{3})_)?([0-9a-fA-F]{8})", text)
        if m:
            module = f"ov{m.group(1)}" if m.group(1) else None
            addr = int(m.group(2), 16)
            for (mod, a), sym in self.by_key.items():
                if a == addr and (module is None or mod == module):
                    return sym
        return None

    def source_file(self, sym):
        if self._files is None:
            self._files = collections.defaultdict(list)
            for m, d in self.dirs.items():
                path = f"{d}/delinks.txt"
                if not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                for file, body in BLOCK.findall(text):
                    for lo, hi in RANGE.findall(body):
                        self._files[m].append((int(lo, 16), int(hi, 16), file.strip()))
        for lo, hi, file in self._files.get(sym.module, ()):
            if lo <= sym.addr < hi:
                return file
        return None

    def binary(self, module):
        if module not in self._binaries:
            ext = f"{self.repo}/extract/{self.region}"
            if module == "main":
                path, yaml, pattern = f"{ext}/arm9/arm9.bin", f"{ext}/arm9/arm9.yaml", r"^base_address: (\d+)"
            else:
                path, yaml = f"{ext}/arm9_overlays/{module}.bin", f"{ext}/arm9_overlays/overlays.yaml"
                pattern = rf"^- id: {int(module[2:])}\s+base_address: (\d+)" if module.startswith("ov") else "$^"
            base, data = None, b""
            if os.path.isfile(path) and os.path.isfile(yaml):
                with open(yaml, encoding="utf-8") as fh:
                    m = re.search(pattern, fh.read(), re.M)
                if m:
                    base = int(m.group(1))
                    with open(path, "rb") as fh:
                        data = fh.read()
            self._binaries[module] = (base, data)
        return self._binaries[module]

    def string_at(self, sym):
        base, data = self.binary(sym.module)
        if base is None:
            return None
        off = sym.addr - base
        if not 0 <= off < len(data):
            return None
        m = ASCII.match(data, off)
        return m.group(0)[:-1].decode("ascii") if m else None
