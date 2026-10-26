import re
import sys

KEEP = re.compile(r"^\s*//\s*(?:(?:USA|JPN|EUR):\s*(?=\S*[0-9_])|KEEP-NAME)")


def scan(src):
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            yield False, i, min(j + 1, n)
            i = j + 1
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            yield True, i, j
            i = j
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            yield True, i, j
            i = j
        else:
            yield False, i, i + 1
            i += 1


def comments(src):
    return {src[a:b].rstrip() for is_comment, a, b in scan(src) if is_comment}


def strip(src, keep=frozenset()):
    out = []
    for is_comment, a, b in scan(src):
        text = src[a:b]
        if not is_comment or text.rstrip() in keep:
            out.append(text)
        elif text.startswith("//") and KEEP.match(src[src.rfind("\n", 0, a) + 1:b]):
            out.append(text)
    lines, prev_blank = [], True
    orig = src.split("\n")
    for k, ln in enumerate("".join(out).split("\n")):
        ln = ln.rstrip()
        blank = not ln.strip()
        if blank and (prev_blank or (k < len(orig) and orig[k].strip())):
            continue
        lines.append(ln)
        prev_blank = blank
    return "\n".join(lines).rstrip("\n") + "\n"


if __name__ == "__main__":
    text = open(sys.argv[1], encoding="utf-8").read()
    open(sys.argv[2], "w", encoding="utf-8", newline="\n").write(strip(text))
