import os, re, sys, json, bisect, collections

from namingpaths import LABEL as REPO, NAMING as SP
import buildcfg

FUNC = re.compile(r"^(\S+)\s+kind:function\((\w+),size=0x([0-9a-fA-F]+)\)\s+addr:0x([0-9a-fA-F]+)")
ADDR = re.compile(r"0[12][0-9a-f]{6}")
ASSET = re.compile(r"^[A-Za-z0-9_%<>./\-]+\.(nat|gp2|bin|spr|chr|pac|nsarc|stb|sdat|obg|mes|bact|ambl|amdj|mse|NCGR|bncg|cchr|mon)$")

OVERLAY_NAME = {
    0: "battle", 1: "event", 2: "topmenu", 3: "shisetsu", 4: "menucallback", 5: "equipmenu",
    6: "renkin", 7: "debug", 8: "jourecode", 9: "charamake2", 10: "pitfall", 11: "menusys",
    12: "prof", 13: "skillup", 14: "subjugation", 15: "charaview", 16: "movieview", 17: "gamemain",
    18: "mapjump", 19: "readerror", 20: "title", 21: "charamake", 22: "sub_debug", 23: "sub_menu",
    24: "sub_battle", 25: "sub_round", 26: "sub_command", 27: "sub_staffroll", 28: "sub_hoge",
    29: "sub_makescn", 30: "sub_libmb", 31: "wifi", 32: "sound", 33: "bgload1", 34: "bgload2",
}


def paths():
    for root in buildcfg.config_roots():
        cfg = REPO + "/" + root
        yield ("main", cfg + "/symbols.txt", cfg + "/delinks.txt")
        for sub in ("itcm", "dtcm"):
            p = cfg + "/" + sub
            if os.path.exists(p + "/symbols.txt"):
                yield (sub, p + "/symbols.txt", p + "/delinks.txt")
        ovdir = cfg + "/overlays"
        if not os.path.isdir(ovdir):
            continue
        for name in sorted(os.listdir(ovdir)):
            p = ovdir + "/" + name
            if os.path.exists(p + "/symbols.txt"):
                yield (name, p + "/symbols.txt", p + "/delinks.txt")


def module_label(mod):
    m = re.match(r"^ov(\d+)$", mod)
    if m:
        return "%s %s" % (mod, OVERLAY_NAME.get(int(m.group(1)), "?"))
    return mod


def load():
    funcs = {}
    srcof = {}
    for mod, sy, dl in paths():
        fl = []
        for line in open(sy, encoding="utf-8", errors="replace"):
            m = FUNC.match(line)
            if m:
                fl.append((int(m.group(4), 16), int(m.group(3), 16), m.group(1)))
        fl.sort()
        funcs[mod] = fl
        starts = [f[0] for f in fl]
        cur = None
        for line in open(dl, encoding="utf-8", errors="replace"):
            s = line.strip()
            m = re.match(r"^(src/\S+\.(?:cpp|c|s)):$", s)
            if m:
                cur = m.group(1)
                continue
            m = re.match(r"^\.text start:0x([0-9a-fA-F]+) end:0x([0-9a-fA-F]+)$", s)
            if m and cur:
                a, b = int(m.group(1), 16), int(m.group(2), 16)
                i = bisect.bisect_left(starts, a)
                while i < len(fl) and fl[i][0] < b:
                    srcof[(mod, fl[i][0])] = cur
                    i += 1
    return funcs, srcof


def main():
    funcs, srcof = load()
    cg = json.load(open(SP + "/cg.json"))
    sx = json.load(open(SP + "/strxref.json"))

    callers = collections.Counter()
    for k, v in cg["callers"].items():
        mod, addr, name = k.split("|")
        callers[(mod, int(addr, 16))] = len(v)

    evidence = {}
    for k, v in sx.items():
        mod, name, addr = k.split(" ")
        a = [s for s in v if ASSET.match(s) or s.startswith("data/") or s.startswith("/data/")]
        if a:
            evidence[(mod, int(addr, 16))] = a

    rows = []
    for mod, fl in funcs.items():
        for addr, size, name in fl:
            key = (mod, addr)
            ev = evidence.get(key)
            nc = callers.get(key, 0)
            generated = name.startswith("func_") or bool(ADDR.search(name))
            if ev and generated:
                tier = "evidence"
            elif generated and nc >= 50:
                tier = "hub"
            else:
                continue
            rows.append(
                (
                    tier,
                    nc,
                    module_label(mod),
                    "0x%08x" % addr,
                    size,
                    name,
                    srcof.get(key, "-"),
                    " | ".join(ev) if ev else "",
                )
            )

    rows.sort(key=lambda r: (r[0], -r[1]))
    out = ["tier\tcallers\tmodule\taddress\tsize\tcurrent_name\tsource\tasset_strings"]
    for r in rows:
        out.append("%s\t%d\t%s\t%s\t0x%x\t%s\t%s\t%s" % r)
    open(SP + "/REVIEW_QUEUE.tsv", "w", encoding="utf-8",
         newline="\n").write("\n".join(out) + "\n")
    print("queue rows:", len(rows), collections.Counter(r[0] for r in rows))


main()
