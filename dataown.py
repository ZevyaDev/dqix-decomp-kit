import glob
import os
import re
import subprocess

SHF_ALLOC = 0x2
SHF_EXECINSTR = 0x4
LINE = re.compile(r"^(\S+) kind:(\S+) addr:0x([0-9a-fA-F]+)(.*)$")
RELOC = re.compile(r"^from:0x([0-9a-fA-F]+) kind:(\S+) to:0x([0-9a-fA-F]+)(?: add:(\S+))? module:(\S+)$")


def addend(rr, target_data):
    if rr.is_RELA():
        return rr["r_addend"]
    o = rr["r_offset"]
    return int.from_bytes(target_data[o:o + 4], "little")


def read_keep_nl(path):
    raw = open(path, "rb").read()
    return raw.decode("utf-8", "replace").replace("\r\n", "\n"), ("\r\n" if b"\r\n" in raw else "\n")


def load_relocs(repo):
    import buildcfg
    return {os.path.normcase(os.path.abspath(p)): read_keep_nl(p)
            for p in sorted(glob.glob(repo + "/" + buildcfg.config_root() + "/**/relocs.txt", recursive=True))}


def module_tag(module):
    return "main" if module == "main" else "overlay(%d)" % int(module)


def file_ranges(delinks):
    return [(int(m.group(2), 16), int(m.group(3), 16)) for m in
            re.finditer(r"(?m)^\s*\.(\w+)\s+start:0x([0-9a-fA-F]+)\s+end:0x([0-9a-fA-F]+)(.*)$", delinks)
            if "kind:" not in m.group(4)]


def module_sections(delinks):
    return [(m.group(1), int(m.group(2), 16), int(m.group(3), 16)) for m in
            re.finditer(r"\.(\w+)\s+start:0x([0-9a-fA-F]+)\s+end:0x([0-9a-fA-F]+)\s+kind:(\w+)", delinks)]


def _place_sections(elf, sections, owned, rels, symtab, texts, pristine, base):
    candidates = {}

    def note(index, value, where):
        candidates.setdefault(index, []).append((value, where))

    for text_index, slot, func_addr in texts:
        text = sections[text_index].data()
        for rr in (rels[text_index].iter_relocations() if text_index in rels else []):
            o = rr["r_offset"]
            if rr["r_info_type"] != 2 or o + 4 > slot:
                continue
            sym = symtab.get_symbol(rr["r_info_sym"])
            if sym["st_shndx"] in owned:
                rom = int.from_bytes(pristine[func_addr - base + o:func_addr - base + o + 4], "little")
                note(sym["st_shndx"], rom - addend(rr, text) - sym["st_value"], "0x%08x" % (func_addr + o))

    bases = {}
    while True:
        for index, found in candidates.items():
            values = {v for v, _w in found}
            if len(values) != 1:
                return "DATA-INCONSISTENT %s at %s" % (
                    sections[index].name, ", ".join("0x%08x (%s)" % (v, w) for v, w in found))
        fresh = {index: found[0][0] for index, found in candidates.items() if index not in bases}
        if not fresh:
            return bases
        bases.update(fresh)
        for index in fresh:
            sec = owned[index]
            if index not in rels or sec["sh_type"] == "SHT_NOBITS":
                continue
            data = sec.data()
            for rr in rels[index].iter_relocations():
                sym = symtab.get_symbol(rr["r_info_sym"])
                if rr["r_info_type"] == 2 and sym["st_shndx"] in owned and sym["st_shndx"] not in bases:
                    at = bases[index] + rr["r_offset"] - base
                    rom = int.from_bytes(pristine[at:at + 4], "little")
                    note(sym["st_shndx"], rom - addend(rr, data) - sym["st_value"],
                         "%s+0x%x" % (sec.name, rr["r_offset"]))


def plan(elf, text_index, slot, func_addr, pristine, base, module, cfg_dir, repo, src_path, symaddr,
         delinks, symtxt, relocs, extra_texts=()):
    texts = [(text_index, slot, func_addr)] + list(extra_texts)
    sections = list(elf.iter_sections())
    owned = {i: s for i, s in enumerate(sections)
             if s["sh_flags"] & SHF_ALLOC and not s["sh_flags"] & SHF_EXECINSTR and s["sh_size"]}
    if not owned:
        return None
    symtab = elf.get_section_by_name(".symtab")
    rels = {s["sh_info"]: s for s in sections
            if hasattr(s, "iter_relocations") and (s["sh_info"] in owned or s["sh_info"] in [t[0] for t in texts])}

    bases = _place_sections(elf, sections, owned, rels, symtab, texts, pristine, base)
    if isinstance(bases, str):
        return bases
    for index, sec in owned.items():
        if index not in bases:
            return "DATA-UNPLACED %s (0x%x bytes): nothing references it" % (sec.name, sec["sh_size"])

    homes = module_sections(delinks)
    taken = file_ranges(delinks)
    ranges = []
    for index, sec in sorted(owned.items(), key=lambda kv: bases[kv[0]]):
        name = sec.name.lstrip(".")
        start = bases[index]
        end = start + ((sec["sh_size"] + 3) & ~3)
        if start & 3 or not [h for h in homes if h[0] == name and h[1] <= start and end <= h[2]]:
            return "DATA-RANGE .%s 0x%08x..0x%08x is misaligned or outside the module's .%s" % (
                name, start, end, name)
        for s, e in taken:
            if s < end and start < e:
                return "DATA-RANGE .%s 0x%08x..0x%08x overlaps a delinked file at 0x%08x..0x%08x" % (
                    name, start, end, s, e)
        ranges.append((name, start, end, index))

    for name, start, _end, index in ranges:
        sec = owned[index]
        if sec["sh_type"] == "SHT_NOBITS":
            continue
        data = sec.data()
        masked, wrong = set(), []
        for rr in (rels[index].iter_relocations() if index in rels else []):
            o = rr["r_offset"]
            masked.update(range(o, o + 4))
            if rr["r_info_type"] != 2:
                continue
            sym = symtab.get_symbol(rr["r_info_sym"])
            if sym["st_shndx"] in owned:
                target = bases[sym["st_shndx"]] + sym["st_value"]
            elif sym.name in symaddr:
                target = symaddr[sym.name]
            else:
                continue
            want = target + addend(rr, data)
            rom = int.from_bytes(pristine[start - base + o:start - base + o + 4], "little")
            if rom not in (want & 0xFFFFFFFF, (want + 1) & 0xFFFFFFFF):
                wrong.append("%s+0x%x->%s" % (sec.name, o, sym.name))
        diffs = [k for k in range(len(data)) if k not in masked and data[k] != pristine[start - base + k]]
        if diffs:
            return "DATA-BYTEDIFF .%s at 0x%08x: %d bytes, first +0x%x" % (name, start, len(diffs), diffs[0])
        if wrong:
            return "DATA-RELOCWRONG " + ", ".join(wrong[:4])

    objects = []
    for sym in symtab.iter_symbols():
        if sym["st_shndx"] in owned and sym.name and not sym.name.startswith("$") and \
                sym["st_info"]["type"] in ("STT_OBJECT", "STT_NOTYPE"):
            objects.append((bases[sym["st_shndx"]] + sym["st_value"], max(sym["st_size"], 1), sym.name,
                            sym["st_info"]["bind"] == "STB_LOCAL",
                            owned[sym["st_shndx"]]["sh_type"] == "SHT_NOBITS"))
    objects.sort()

    def owner(target):
        for addr, size, oname, local, _bss in objects:
            if addr <= target < addr + size:
                return addr, oname, local
        return None

    inside = [(s, e) for _n, s, e, _i in ranges] + [(fa, fa + sl) for _t, sl, fa in texts]
    tag = module_tag(module)
    own_relocs = os.path.normcase(os.path.abspath(os.path.join(repo, cfg_dir, "relocs.txt")))
    reloc_edits = {}
    for path, (text_r, nl) in relocs.items():
        out, changed = [], False
        for line in text_r.split("\n"):
            m = RELOC.match(line)
            if not m or m.group(5) != tag:
                out.append(line)
                continue
            frm = int(m.group(1), 16)
            target = int(m.group(3), 16) + (int(m.group(4), 0) if m.group(4) else 0)
            hit = owner(target)
            if not hit:
                out.append(line)
                continue
            start, oname, local = hit
            if local and not (path == own_relocs and any(s <= frm < e for s, e in inside)):
                return "DATA-LOCALREF %s is STB_LOCAL but 0x%08x (%s) references it" % (
                    oname, frm, path.replace("\\", "/").split("config/")[-1])
            new = "from:0x%s kind:%s to:0x%08x%s module:%s" % (
                m.group(1), m.group(2), start, " add:0x%x" % (target - start) if target != start else "",
                m.group(5))
            changed |= new != line
            out.append(new)
        if changed:
            reloc_edits[path] = ("\n".join(out), nl)

    starts = {addr: (oname, local, bss) for addr, _size, oname, local, bss in objects}
    retired, kept, placed, renamed, src_edits = [], [], set(), {}, {}
    for line in symtxt.split("\n"):
        m = LINE.match(line)
        if not m or m.group(2).startswith("function") or \
                not any(s <= int(m.group(3), 16) < e for _n, s, e, _i in ranges):
            kept.append(line)
            continue
        addr = int(m.group(3), 16)
        if addr not in starts:
            retired.append(m.group(1))
            continue
        oname, local, _bss = starts[addr]
        if m.group(1) != oname:
            retired.append(m.group(1))
            renamed[m.group(1)] = oname
        flags = [f for f in m.group(4).split() if f != "local"] + (["local"] if local else [])
        kept.append("%s kind:%s addr:0x%s%s" % (oname, m.group(2), m.group(3), "".join(" " + f for f in flags)))
        placed.add(addr)
    for addr, (oname, local, bss) in sorted(starts.items()):
        if addr in placed:
            continue
        at = next((k for k, line in enumerate(kept) if LINE.match(line)
                   and not LINE.match(line).group(2).startswith("function")
                   and int(LINE.match(line).group(3), 16) > addr), None)
        if at is None:
            at = len(kept)
            while at and kept[at - 1] == "":
                at -= 1
        kept.insert(at, "%s kind:%s addr:0x%08x%s" % (oname, "bss" if bss else "data(any)", addr,
                                                      " local" if local else ""))

    if retired:
        r = subprocess.run(["git", "grep", "-l", "-w", "-F"] + sum((["-e", n] for n in retired), [])
                           + ["--", "src", "include"], cwd=repo, capture_output=True, text=True)
        mine = os.path.normcase(os.path.abspath(os.path.join(repo, src_path)))
        users = [f for f in r.stdout.split() if os.path.normcase(os.path.abspath(os.path.join(repo, f))) != mine]
        unmapped = [n for n in retired if n not in renamed]
        if users and unmapped:
            return "DATA-NAMEINUSE %s named by %s" % (", ".join(retired[:4]), ", ".join(users[:4]))
        for f in users:
            path = os.path.abspath(os.path.join(repo, f))
            text, nl = read_keep_nl(path)
            for old, new in renamed.items():
                text = re.sub(r"\b%s\b" % re.escape(old), new, text)
                text = re.sub(r'(?m)^(\s*)extern\s+(?!"C")([^;\n]*\b%s\b)' % re.escape(new),
                              r'\1extern "C" \2', text)
            src_edits[path] = (text, nl)

    return {
        "ranges": [(n, s, e) for n, s, e, _i in ranges],
        "delink_lines": "".join("    .%s start:0x%08x end:0x%08x\n" % (n, s, e) for n, s, e, _i in ranges),
        "symtxt": "\n".join(kept),
        "relocs": reloc_edits,
        "retired": retired,
        "src_edits": src_edits,
    }
