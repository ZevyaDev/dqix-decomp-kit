"""Usage: python poolmap.py <main|NNN> <addr> <file.cpp>

Prints every literal-pool load with the VALUE it reads in the ROM and in our build.
VALUE = a different constant (a source bug); offset = same constant, different pool slot.
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import glob
import os
import re
import struct
import subprocess
import sys

from elftools.elf.elffile import ELFFile

SP = _kp.SP
KIT = _kp.KIT
sys.path.insert(0, KIT)
import buildcfg

REPO = _kp.REPO

if len(sys.argv) < 4:
    sys.exit(__doc__)
OV, ADDR, SRC = sys.argv[1], sys.argv[2].lower(), os.path.abspath(sys.argv[3])
CC = buildcfg.cc_path(os.environ.get("MWCC"))
FLAGS = list(buildcfg.FLAGS)
os.chdir(REPO)

if OV == "main":
    CFG = buildcfg.config_dir("main")
    ROM = open(buildcfg.pristine('main'), "rb").read()
    BASE = 0x02000000
else:
    CFG = f"{buildcfg.config_dir(OV)}"
    ROM = open(f"{buildcfg.pristine(OV)}", "rb").read()
    BASE = min(int(x, 16) for x in re.findall(r"start:0x([0-9a-fA-F]+)", open(f"{CFG}/delinks.txt").read()))

symtxt = open(f"{CFG}/symbols.txt", encoding="utf-8", errors="ignore").read()
m = re.search(r"\S+ kind:function\((arm|thumb),size=0x([0-9a-fA-F]+)\) addr:0x0*%s\b" % ADDR.lstrip("0"),
              symtxt, re.I)
if not m:
    sys.exit(f"NO-SLOT: nothing at {ADDR} in {CFG}/symbols.txt")
ISA, SLOT = m.group(1).lower(), int(m.group(2), 16)

head = open(f"{CFG}/delinks.txt", encoding="utf-8").read().split("\n\n")[0]
SEC = next(("." + h.group(1) for h in
            re.finditer(r"\.(\w+)\s+start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+) kind:code", head)
            if int(h.group(2), 16) <= int(ADDR, 16) < int(h.group(3), 16)), ".text")

addr_of = {}
for p in [f"{REPO}/{buildcfg.config_root()}/symbols.txt"] + glob.glob(f"{REPO}/{buildcfg.config_root()}/overlays/*/symbols.txt"):
    for s in re.finditer(r"^(\S+) kind:\S+ addr:0x([0-9a-fA-F]{8})", open(p, encoding="utf-8", errors="ignore").read(), re.M):
        addr_of.setdefault(s.group(1), int(s.group(2), 16))

obj = f"{KIT}/pad/poolmap_{os.getpid()}.o"
r = subprocess.run([CC] + FLAGS + ["-c", SRC, "-o", obj], capture_output=True, text=True)
if r.returncode != 0:
    sys.exit("COMPILE-FAIL: " + (r.stdout + r.stderr)[-600:])
try:
    elf = ELFFile(open(obj, "rb"))
    text = next((s for s in elf.iter_sections() if s.name == SEC), None)
    if text is None:
        sys.exit(f"no {SEC} emitted")
    mine = text.data()[:SLOT]
    symtab = elf.get_section_by_name(".symtab")
    reloc_sym = {}
    for sec in elf.iter_sections():
        if sec.name in (".rel" + SEC, ".rela" + SEC) and hasattr(sec, "iter_relocations"):
            for rr in sec.iter_relocations():
                reloc_sym[rr["r_offset"] & ~3] = symtab.get_symbol(rr["r_info_sym"]).name
finally:
    try:
        os.remove(obj)
    except OSError:
        pass

a = int(ADDR, 16)
orig = ROM[a - BASE:a - BASE + SLOT]


def literal_loads(code):
    out = {}
    if ISA == "arm":
        for off in range(0, len(code) - 3, 4):
            ins = struct.unpack_from("<I", code, off)[0]
            if (ins & 0x0F7F0000) == 0x051F0000:
                imm = ins & 0xFFF
                tgt = off + 8 + (imm if (ins >> 23) & 1 else -imm)
                out[off] = ((ins >> 12) & 0xF, tgt)
    else:
        for off in range(0, len(code) - 1, 2):
            h = struct.unpack_from("<H", code, off)[0]
            if (h & 0xF800) == 0x4800:
                out[off] = ((h >> 8) & 7, ((off + 4) & ~3) + ((h & 0xFF) << 2))
    return out


def word(code, tgt):
    return struct.unpack_from("<I", code, tgt)[0] if 0 <= tgt <= len(code) - 4 else None


def show(v):
    if v is None:
        return "?"
    f = struct.unpack("<f", struct.pack("<I", v))[0]
    exp = (v >> 23) & 0xFF
    fl = f"  ({f:g}f)" if 0x60 < exp < 0xA0 else ""
    return f"0x{v:08x}{fl}"


rom_ld, our_ld = literal_loads(orig), literal_loads(mine)
pairs = [(o, o) for o in sorted(set(rom_ld) & set(our_ld))]
left_r = sorted(set(rom_ld) - set(our_ld))
left_o = sorted(set(our_ld) - set(rom_ld))
pairs += list(zip(left_r, left_o))
for o in left_r[len(left_o):]:
    print(f"  +0x{o:04x}  ROM literal load with no counterpart in ours")
for o in left_o[len(left_r):]:
    print(f"  +0x{o:04x}  our literal load with no counterpart in the ROM")
bad = moved = same = 0
for roff, ooff in sorted(pairs):
    (rr, rt), (_mr, mt) = rom_ld[roff], our_ld[ooff]
    rv = word(orig, rt)
    sym = reloc_sym.get(mt & ~3)
    mv = addr_of.get(sym) if sym else word(mine, mt)
    ours = f"&{sym}" + (f" = 0x{mv:08x}" if mv is not None else " (unresolved)") if sym else show(mv)
    where = f"+0x{roff:04x}" if roff == ooff else f"+0x{roff:04x}/ours+0x{ooff:04x}"
    if rv == mv:
        if roff == ooff and rt == mt:
            same += 1
            continue
        moved += 1
        tag = "offset"
    else:
        bad += 1
        tag = "VALUE "
    print(f"  {tag} {where:22s} r{rr}  ROM {show(rv):26s} ours {ours}")
print(f"{bad} VALUE mismatch(es), {moved} offset-only, {same} identical  ({len(rom_ld)} ROM literal loads)")
