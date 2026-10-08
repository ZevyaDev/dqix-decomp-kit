"""Find the 0xe7 ladder shape: a pointer DERIVED from a saved call result taking a LOWER register.

02061c04's case 0xe7 is
    mov r5, r0        <- battle, the call result
    add r1, r5, #0x104
    add r4, r1, #0x7400   <- rec, derived from battle, and it gets the LOWER callee-saved register

We always emit `mov r4, r0` / `add r5, ...` instead. An earlier scan for this shape was
mis-specified (it required the first `add` to target a callee-saved register, which even our own
target does not) and returned zero sites, including 02061c04 itself -- so 0xe7 has never actually
been searched. This is the corrected query, with the same committed-source cross-reference that
found six examples for case 0xe4.

Usage: python findladder.py [--all]
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
cfg = open(f"{REPO}/{buildcfg.config_root()}/delinks.txt").read()
base = min(int(x, 16) for x in re.findall(r"start:0x([0-9a-fA-F]+)", cfg))
ranges = sorted((int(a, 16), int(b, 16)) for a, b in
                re.findall(r"\.text start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)", cfg))
sizes = {a: b - a for a, b in ranges}

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
        for a in addrs:
            srcs[a] = f


def w(off):
    return int.from_bytes(blob[off:off + 4], "little")


def owner(addr):
    return next((a for a, b in ranges if a <= addr < b), None)


hits = []
for off in range(0, len(blob) - 24, 4):
    w0 = w(off)
    # mov rA, r0 -- mask out the destination field (bits 15..12), keep opcode and Rm=0
    if (w0 >> 28) != 0xE or (w0 & 0x0FFF0FFF) != 0x01A00000:
        continue
    ra = (w0 >> 12) & 0xF
    if not 4 <= ra <= 11:
        continue
    for k in range(1, 4):                                              # add rT, rA, #imm
        w1 = w(off + 4 * k)
        if (w1 >> 28) != 0xE or (w1 & 0x0FF00000) != 0x02800000 or ((w1 >> 16) & 0xF) != ra:
            continue
        rt = (w1 >> 12) & 0xF
        for j in range(k + 1, k + 4):                                  # add rB, rT, #imm
            w2 = w(off + 4 * j)
            if (w2 >> 28) != 0xE or (w2 & 0x0FF00000) != 0x02800000 or ((w2 >> 16) & 0xF) != rt:
                continue
            rb = (w2 >> 12) & 0xF
            if 4 <= rb <= 11 and rb < ra:
                hits.append((base + off, ra, rb))
            break
        break

print("%d site(s) with the 0xe7 ladder" % len(hits))
inside = [h for h in hits if owner(h[0]) in srcs]
print("  %d inside a COMMITTED source (their C is the answer):" % len(inside))
for addr, ra, rb in inside[:10]:
    print("    %08x  saved=r%d derived=r%d  %s" % (addr, ra, rb, srcs[owner(addr)]))
lab = sorted((sizes.get(owner(h[0]), 1 << 30), owner(h[0]) or 0, h[0], h[1], h[2])
             for h in hits if owner(h[0]) and owner(h[0]) not in srcs)
print("  smallest UNMATCHED functions carrying it:")
seen = 0
for sz, fn, addr, ra, rb in lab:
    print("    %08x  %5d B  hit at %08x  saved=r%d derived=r%d" % (fn, sz, addr, ra, rb))
    seen += 1
    if seen >= 10:
        break
if "--all" in sys.argv:
    for addr, ra, rb in hits:
        o = owner(addr)
        print("  %08x r%d/r%d %s" % (addr, ra, rb, ("%08x" % o) if o else "(unsplit)"))
