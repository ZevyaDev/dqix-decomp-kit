import os, re, subprocess

from namingpaths import LABEL as REPO
import buildcfg

SYMF = re.compile(r"^(\S+)\s+kind:(\w+)[\(\s]")
ADDR = re.compile(r"addr:0x([0-9a-fA-F]+)")


def load(text):
    out = {}
    for line in text.splitlines():
        m = SYMF.match(line)
        a = ADDR.search(line)
        if m and a:
            out[a.group(1)] = m.group(1)
    return out


def rels():
    for root in buildcfg.config_roots():
        yield root + "/symbols.txt"
        for sub in ("itcm", "dtcm"):
            yield root + "/%s/symbols.txt" % sub
        ov = os.path.join(REPO, root, "overlays")
        if not os.path.isdir(ov):
            continue
        for n in sorted(os.listdir(ov)):
            yield root + "/overlays/%s/symbols.txt" % n


renames = {}
for rel in rels():
    p = REPO + "/" + rel
    if not os.path.exists(p):
        continue
    try:
        old = load(subprocess.check_output(["git", "-C", REPO, "show", "HEAD:" + rel]).decode("utf-8", "replace"))
    except subprocess.CalledProcessError:
        continue
    new = load(open(p, encoding="utf-8", errors="replace").read())
    for addr, o in old.items():
        n = new.get(addr)
        if n and n != o:
            renames[o] = n

print("renamed symbols:", len(renames))

changed = 0
for d in (REPO + "/src", REPO + "/include"):
    for root, _, files in os.walk(d):
        for f in files:
            if not f.endswith((".cpp", ".c", ".h", ".hpp")):
                continue
            p = os.path.join(root, f)
            text = open(p, encoding="utf-8", newline="").read()
            out = text
            for o, n in renames.items():
                if o in out:
                    out = re.sub(r"\b%s\b" % re.escape(o), n, out)
            if out != text:
                open(p, "w", encoding="utf-8", newline="").write(out)
                changed += 1
print("files updated:", changed)
