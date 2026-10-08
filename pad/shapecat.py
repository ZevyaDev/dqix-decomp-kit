"""Do laboratories exist for 02061c04's other two residues?

findshape.py answered that question for case 0xd3: the pairing it needs occurs five times in ARM9
and never in a committed source, so there is nothing to read. Cases 0xe4 and 0xe7 have never been
asked. A SMALL function carrying the same micro-shape is worth more than another thousand guesses --
if it is already matched, its C is the answer; if it is unmatched and small, it is a cheap
laboratory and a free function.

    e4   ldr rP,[pc,#imm] ; ldrb rB,[rP,#imm]      with rP < rB  (ours is rP > rB)
    e7   mov rA,r0 ; ... ; add rB,rA,#imm          with rB < rA, both callee-saved
                                                   (a derived pointer BELOW its source)

Usage: python shapecat.py e4|e7
"""
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import os
import re
import sys

REPO = _kp.REPO
blob = open(f"{REPO}/{buildcfg.extract_root()}/arm9/arm9.bin", "rb").read()
cfg = open(f"{REPO}/{buildcfg.config_root()}/delinks.txt").read()
base = min(int(x, 16) for x in re.findall(r"start:0x([0-9a-fA-F]+)", cfg))
ranges = sorted((int(a, 16), int(b, 16)) for a, b in
                re.findall(r"\.text start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)", cfg))

# Keying by the address in the FILENAME misses every semantically-named file (PeekInputLogB.cpp is
# func_020a1fa8), which is how an earlier run reported "0 committed" for a shape the corpus holds.
srcs = {}
for root, _, files in os.walk(f"{REPO}/src"):
    for f in files:
        if not f.endswith(".cpp"):
            continue
        addrs = set()
        m = re.search(r"_?([0-9a-f]{8})\.cpp$", f)
        if m and m.group(1).startswith("02"):
            addrs.add(int(m.group(1), 16))
        body = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
        for a in re.findall(r"//\s*USA:\s*\S*?_?([0-9a-f]{8})\b", body):
            addrs.add(int(a, 16))
        for a in re.findall(r"\b(02[0-9a-f]{6})\b", f):
            addrs.add(int(a, 16))
        for a in addrs:
            srcs[a] = f

sizes = {a: b - a for a, b in ranges}


def owner(addr):
    return next((a for a, b in ranges if a <= addr < b), None)


def w(off):
    return int.from_bytes(blob[off:off + 4], "little")


which = sys.argv[1]
hits = []
for off in range(0, len(blob) - 32, 4):
    if which == "e4":
        w0, w1 = w(off), w(off + 4)
        if (w0 >> 28) != 0xE or (w0 & 0x0FFF0000) != 0x059F0000:      # ldr rD,[pc,#imm]
            continue
        if (w1 >> 28) != 0xE or (w1 & 0x0FF00000) != 0x05D00000:      # ldrb rD,[rN,#imm]
            continue
        rp, rb, rn = (w0 >> 12) & 0xF, (w1 >> 12) & 0xF, (w1 >> 16) & 0xF
        if rn != rp or rp >= rb or rb > 3 or (w1 & 0xFFF) == 0:
            continue
        hits.append((base + off, rp, rb))
    else:
        w0 = w(off)
        if (w0 >> 28) != 0xE or (w0 & 0x0FFFFFF0) != 0x01A00000:      # mov rA, r0
            continue
        ra = (w0 >> 12) & 0xF
        if not 4 <= ra <= 9:
            continue
        for k in range(1, 6):
            w1 = w(off + 4 * k)
            if (w1 >> 28) != 0xE or (w1 & 0x0FF00000) != 0x02800000:  # add rB, rN, #imm
                continue
            rb, rn = (w1 >> 12) & 0xF, (w1 >> 16) & 0xF
            if rn == ra and 4 <= rb <= 9 and rb < ra:
                hits.append((base + off, ra, rb))
                break

print("%d site(s) with the %s shape" % (len(hits), which))
matched = [h for h in hits if owner(h[0]) in srcs]
print("  %d inside a COMMITTED source (their C is the answer):" % len(matched))
for addr, a, b in matched[:10]:
    print("    %08x  r%d/r%d  %s" % (addr, a, b, srcs[owner(addr)]))
lab = sorted((sizes.get(owner(h[0]), 1 << 30), owner(h[0]) or 0, h[0], h[1], h[2])
             for h in hits if owner(h[0]) not in srcs and owner(h[0]))
seen, shown = set(), 0
print("  smallest UNMATCHED functions carrying it (laboratories):")
for sz, fn, addr, a, b in lab:
    if fn in seen:
        continue
    seen.add(fn)
    print("    %08x  %5d B  hit at %08x  r%d/r%d" % (fn, sz, addr, a, b))
    shown += 1
    if shown >= 10:
        break
