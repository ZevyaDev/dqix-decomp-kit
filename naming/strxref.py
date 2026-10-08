import os, re, struct, sys, bisect, json

from namingpaths import GAME as REPO
import buildcfg

CFG = REPO + "/" + buildcfg.config_root()
EXT = REPO + "/" + buildcfg.extract_root()

def text_base(delinks):
    for line in open(delinks, encoding="utf-8", errors="replace"):
        m = re.search(r"\.text\s+start:0x([0-9a-fA-F]+)", line)
        if m:
            return int(m.group(1), 16)
    return None

def funcs(symbols):
    out = []
    for line in open(symbols, encoding="utf-8", errors="replace"):
        m = re.match(r"^(\S+)\s+kind:function\((\w+),size=0x([0-9a-fA-F]+)\)\s+addr:0x([0-9a-fA-F]+)", line)
        if m:
            out.append((int(m.group(4), 16), int(m.group(3), 16), m.group(1), m.group(2)))
    out.sort()
    return out

STR = re.compile(rb"[\x20-\x7e]{5,}\x00")

def modules():
    yield ("main", EXT + "/arm9/arm9.bin", CFG + "/delinks.txt", CFG + "/symbols.txt")
    ovdir = CFG + "/overlays"
    for name in sorted(os.listdir(ovdir)):
        d = ovdir + "/" + name
        b = EXT + "/arm9_overlays/" + name + ".bin"
        if os.path.exists(b) and os.path.exists(d + "/delinks.txt"):
            yield (name, b, d + "/delinks.txt", d + "/symbols.txt")

def main():
    strings_by_addr = {}
    mods = []
    for name, binp, dl, sy in modules():
        data = open(binp, "rb").read()
        base = text_base(dl)
        if base is None:
            continue
        for m in STR.finditer(data):
            strings_by_addr[base + m.start()] = m.group(0)[:-1].decode("ascii")
        mods.append((name, data, base, funcs(sy)))

    result = {}
    for name, data, base, fl in mods:
        starts = [f[0] for f in fl]
        n = len(data) & ~3
        for off in range(0, n, 4):
            w = struct.unpack_from("<I", data, off)[0]
            s = strings_by_addr.get(w)
            if s is None:
                continue
            addr = base + off
            i = bisect.bisect_right(starts, addr) - 1
            if i < 0:
                continue
            fa, fs, fn, mode = fl[i]
            if addr >= fa + fs:
                continue
            key = name + " " + fn + " 0x%08x" % fa
            result.setdefault(key, [])
            if s not in result[key]:
                result[key].append(s)
    json.dump(result, open(sys.argv[1], "w"), indent=1)
    print(len(result), "functions with string references")

main()
