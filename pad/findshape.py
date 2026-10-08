"""Find an ALREADY-MATCHED function whose ROM code has the shape a stuck case needs.

The project has thousands of committed, byte-exact sources. If any of them compiles to
`add rLOW, rBASE, #imm` immediately followed by `ldr rHIGH, [rLOW, #imm]` -- the pairing 02061c04's
case 0xd3 needs and that no hand-written form reproduces -- then its C IS the answer, and reading it
is cheaper than another thousand guesses. Same discipline as reading a matched source before writing
an idiom off.

Scans the pristine ARM9 image for the pattern, then reports which delinked range each hit falls in
and whether that range has a committed source.

Usage: python findshape.py [--any]     (--any drops the r1<r2 requirement, listing every add/ldr pair)
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import os
import re
import sys

REPO = _kp.REPO
blob = open(f"{REPO}/{buildcfg.pristine('main')}", "rb").read()
cfg = f"{REPO}/{buildcfg.config_root()}/delinks.txt"
text = open(cfg).read()
base = min(int(x, 16) for x in re.findall(r"start:0x([0-9a-fA-F]+)", text))

ranges = []
for m in re.finditer(r"\.text start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)", text):
    ranges.append((int(m.group(1), 16), int(m.group(2), 16)))
ranges.sort()

# Keying committed sources by the address in their FILENAME misses every file with a semantic name
# -- PeekInputLogB.cpp is func_020a1fa8 and StoreByteAtCountTail020a1fd4 is committed too, so a
# filename-only map reported "0 inside a committed source" when the corpus holds the shape. Read the
# `// USA:` line and any 8-hex-digit address in the file as well.
srcs = {}
for root, _, files in os.walk(f"{REPO}/src"):
    for f in files:
        if not f.endswith(".cpp"):
            continue
        path = os.path.join(root, f)
        addrs = set()
        m = re.search(r"_([0-9a-f]{8})\.cpp$", f)
        if m:
            addrs.add(int(m.group(1), 16))
        try:
            body = open(path, encoding="utf-8", errors="ignore").read()
        except IOError:
            body = ""
        for a in re.findall(r"//\s*USA:\s*\S*?_?([0-9a-f]{8})\b", body):
            addrs.add(int(a, 16))
        for a in re.findall(r"\b(02[0-9a-f]{6})\b", f):
            addrs.add(int(a, 16))
        for a in addrs:
            srcs[a] = path

anyreg = "--any" in sys.argv
hits = []
for off in range(0, len(blob) - 8, 4):
    w0 = int.from_bytes(blob[off:off + 4], "little")
    w1 = int.from_bytes(blob[off + 4:off + 8], "little")
    # ADD rD, rN, #imm  (cond=AL, I=1, opcode=0100, S=0)
    if (w0 & 0x0FF00000) != 0x02800000 or (w0 >> 28) != 0xE:
        continue
    rd0 = (w0 >> 12) & 0xF
    # LDR rD, [rN, #imm]  (cond=AL, I=0, P=1, U=1, B=0, W=0, L=1)
    if (w1 & 0x0FF00000) != 0x05900000 or (w1 >> 28) != 0xE:
        continue
    rn1 = (w1 >> 16) & 0xF
    rd1 = (w1 >> 12) & 0xF
    if rn1 != rd0 or rd0 > 3 or rd1 > 3:
        continue
    if not anyreg and not (rd0 < rd1):
        continue
    # mwcc's ONE-node split is always `add = C & ~0xfff`, so an add whose DECODED immediate is a
    # multiple of 0x1000 is just the compiler splitting a single offset -- a shape we reproduce
    # fine (func_02098970 is one). Only a non-multiple is a genuine TWO-node address, the pairing
    # case 0xd3 needs and that no source form gives us.
    rot = ((w0 >> 8) & 0xF) * 2
    imm = ((w0 & 0xFF) >> rot) | ((w0 & 0xFF) << (32 - rot)) & 0xFFFFFFFF if rot else (w0 & 0xFF)
    if "--twonode" in sys.argv and imm % 0x1000 == 0:
        continue
    # and a real field access, not a linked-list advance: the load must carry a big offset too
    if "--twonode" in sys.argv and (w1 & 0xFFF) < 0x100:
        continue
    addr = base + off
    fn = next((a for a, b in ranges if a <= addr < b), None)
    hits.append((addr, fn, w0 & 0xFFF, w1 & 0xFFF, rd0, rd1))

if "--all" in sys.argv:
    print("every hit:")
    for addr, fn, i0, i1, rd0, rd1 in hits:
        print("  %08x  r%d/r%d  in %s" % (addr, rd0, rd1,
                                          ("%08x" % fn) if fn else "(no delink range)"))

named = [h for h in hits if h[1] in srcs]
print("%d pattern hit(s), %d inside a committed source" % (len(hits), len(named)))
for addr, fn, i0, i1, rd0, rd1 in named[:25]:
    print("  %08x  r%d/r%d  in %08x  %s" % (addr, rd0, rd1, fn, os.path.basename(srcs[fn])))

size = {a: b - a for a, b in ranges}
todo = sorted((size.get(h[1], 1 << 30), h[1] or 0, h[0], h[4], h[5])
              for h in hits if h[1] not in srcs)
print("\nsmallest UNMATCHED functions carrying the shape (a far better laboratory than a 10 KB switch):")
seen = set()
for sz, fn, addr, rd0, rd1 in todo:
    if fn in seen:
        continue
    seen.add(fn)
    print("  %08x  %5d B  hit at %08x  r%d/r%d" % (fn, sz, addr, rd0, rd1))
    if len(seen) >= 12:
        break
