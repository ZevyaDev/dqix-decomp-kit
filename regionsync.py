"""Port matched files between regions, keeping each port only if the receiving region builds.

    python regionsync.py [decomp tree]     default: the current directory
    python regionsync.py --gate [decomp tree]

First into usa: a file delinked in another region but not in config/usa, owning one `.text` range and
no data, whose `// USA:` tag names a usa function, gets a usa block at that function when the function
has the same size or wgate.py matches the file against it.
Then from usa to each region with a port tool that has --sync and an extracted ROM: run the sync
(after compiling the region's objects first when its tool reads them). The ported regions build
together with usa, and each port is committed when the receiving region's `ninja check` and
`ninja sha1` pass. Every build first reads the region's depfiles and objects in parallel; ninja and
mwld would otherwise read them one at a time.
When they do not, restore the config of each module whose check failed and build again; restore the
whole port when that is still red or no module is named. Every region but usa builds from its own
build/<region>/build.ninja, so regions build at the same time; build.ninja is left configured for usa.
Each file another region delinks that stays out of usa prints a `NOT IN USA <file>: <why>` line.
Exit 0: every region in sync, ported or skipped. 1: a port was red and was restored, in part or in
full, or a file is NOT IN USA.

--gate is the landing's build, before it commits: port the uncommitted usa wiring to every region with
an extracted ROM, then build usa and every region the port or the landing's changes to tracked src/ or
include/ files reach, all at once. It prints usa's build log, then a `GATE <region>:` line per region.
Exit 0 when usa is green and no region those changes reach is red. The ports stay uncommitted;
regionsync.py commits them after the landing, its builds already done. A port whose inputs are
unchanged since its last run (build/<region>/ported) is not run again.
"""
import concurrent.futures
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

import kitpaths

PORTS = {"eur": "tools/port_eur_config.py", "jpn": "tools/port_jpn_config.py"}
READS_OBJECTS = {"jpn"}
HOME = "usa"
FAILED_CHECK = re.compile(r"Check (ARM9 main|ITCM|DTCM|overlay (\d+)): (?!OK)")
ERROR_LINE = re.compile(r"(?m)^\s*(?:\[ERROR\]|Error:).*$")
FAILED_CONFIG = re.compile(r"config[\\/]\w+[\\/]arm9[\\/](?:overlays[\\/]ov(\d{3})[\\/])?\w+\.txt")
FAILED_MODULE = re.compile(r"Failed to delink '(?:ov(\d{3})|main)_\d+'|in overlay (\d+)\b|in (ARM9 main)\b")
FAILED_FILE = re.compile(r"file '(src/[^']+)'")
PORTED_FILE = re.compile(r"^\+[^+\s].*:\r?$", re.M)
BLOCK = re.compile(r"(?m)^(src/\S+):[ \t]*\r?\n((?:[ \t]+\S.*(?:\r?\n|$))*)")
TEXT = re.compile(r"\.text\s+start:0x([0-9a-fA-F]+)\s+end:0x([0-9a-fA-F]+)")
SECTION = re.compile(r"(?m)^[ \t]+(\.\w+)\s")
FUNCTION = re.compile(r"(?m)^(\S+) kind:function\([^)]*size=0x([0-9a-fA-F]+)[^)]*\)\s+addr:0x([0-9a-fA-F]+)")
USA_TAG = re.compile(r"(?m)^// USA: (\S+)")
TAG_ADDRESS = re.compile(r"func_(?:ov\d{3}_)?([0-9a-fA-F]{8})")


def run(*args):
    r = subprocess.run(list(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def configure(region):
    compiler = os.environ.get("DQIX_PREINSTALLED_COMPILER")
    wine = os.environ.get("DQIX_WINE")
    return run(sys.executable, "tools/configure.py", region, "--no-extract",
               *(["--compiler", compiler] if compiler else []), *(["-w", wine] if wine else []))


def ninja_file(region):
    return "build.ninja" if region == HOME else f"build/{region}/build.ninja"


def continued(line):
    body = line.rstrip(b"\r\n")
    return (len(body) - len(body.rstrip(b"$"))) % 2 == 1


def drop_rule(data, rule):
    kept, stmt = [], []
    for line in data.splitlines(keepends=True) + [b""]:
        if stmt and (not line or not continued(stmt[-1]) and line[:1] not in (b" ", b"\t")):
            head = []
            for part in stmt:
                head.append(part.rstrip(b"\r\n").rstrip(b"$").strip())
                if not continued(part):
                    break
            edge = re.match(rb"build (?:[^$:]|\$.)*:\s*(\S+)", b" ".join(head))
            if not edge or edge.group(1) != rule.encode():
                kept += stmt
            stmt = []
        stmt.append(line)
    return b"".join(kept)


def listed(path, *tool):
    r = subprocess.run(["ninja", "-f", path, "-t", *tool], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return [t.replace("\\", "/") for t in r.stdout.splitlines() if t.strip()]


def tools():
    needed = set(listed("build.ninja", "inputs", "check", "sha1"))
    targets = [t for t in listed("build.ninja", "targets", "rule", "download_tool") if t in needed]
    return run("ninja", *targets) if targets else (0, "")


def keep(region):
    code, out = configure(region)
    data = open("build.ninja", "rb").read() if os.path.isfile("build.ninja") else b""
    if code or os.path.join("build", region, "arm9.o").encode() not in data:
        return f"configure.py {region} failed: {out.strip()[-300:]}"
    if region == HOME:
        return None
    path = ninja_file(region)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = f"builddir = build/{region}\n".encode() + drop_rule(data, "download_tool")
    if not os.path.isfile(path) or open(path, "rb").read() != data:
        with open(path, "wb") as fh:
            fh.write(data)
    if not os.path.exists(f"build/{region}/.ninja_log") and os.path.isfile(".ninja_log"):
        shutil.copyfile(".ninja_log", f"build/{region}/.ninja_log")
    return None


def slurp(path):
    try:
        with open(path, "rb") as fh:
            fh.read()
    except OSError:
        pass


def prewarm(region):
    paths = [os.path.join(folder, name) for folder, _, names in os.walk(os.path.join("build", region))
             for name in names if name.endswith((".d", ".o"))]
    with concurrent.futures.ThreadPoolExecutor(32) as pool:
        list(pool.map(slurp, paths))


def build(region, sha1=True):
    prewarm(region)
    code, out = run("ninja", "-f", ninja_file(region), "check")
    if code or not sha1:
        return code == 0, out
    code, sha = run("ninja", "-f", ninja_file(region), "sha1")
    return code == 0 and "OK" in sha, out + sha


def green(regions, sha1=True):
    regions = sorted(set(regions), key=lambda region: region == HOME)
    results = {}
    for region in regions:
        bad = keep(region)
        if bad:
            results[region] = (False, bad)
    if HOME not in regions:
        configure(HOME)
    todo = [region for region in regions if region not in results]
    if todo:
        tools()
        with concurrent.futures.ThreadPoolExecutor(len(todo)) as pool:
            results.update(zip(todo, pool.map(lambda region: build(region, sha1), todo)))
    return results


def gate(regions):
    shared = bool(run("git", "status", "--porcelain", "--untracked-files=no", "--", "src", "include")[1].strip())
    for region in regions:
        run("git", "checkout", "HEAD", "--", f"config/{region}")
        port(region, PORTS[region])
    sha1 = os.path.isfile("arm7_bios.bin")
    touched = [region for region in regions if shared or changed(region)]
    results = green([HOME, *touched], sha1)
    redo = [region for region in touched
            if shared and results[HOME][0] and not results[region][0] and changed(region)]
    if redo:
        run("git", "checkout", "--", *(f"config/{region}" for region in redo))
        results.update(green(redo, sha1))
    return results, [region for region in touched if shared and not results[region][0]]


def compile_objects(region):
    if keep(region):
        return
    tools()
    targets = [t for rule in ("mwcc", "mwasm") for t in listed(ninja_file(region), "targets", "rule", rule)]
    escaped = " ".join(t.replace("$", "$$").replace(":", "$:").replace(" ", "$ ") for t in targets)
    path = f"build/{region}/objects.ninja"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"include {ninja_file(region)}\nbuild objects: phony {escaped}\n")
    prewarm(region)
    run("ninja", "-f", path, "-k", "0", "objects")


def ported(region):
    return len(PORTED_FILE.findall(run("git", "diff", "-U0", "--", f"config/{region}")[1]))


def failed_folders(log, region):
    root = f"config/{region}/arm9"
    folders = {root if m[1] == "ARM9 main" else f"{root}/overlays/ov{int(m[2]):03d}" if m[2] else f"{root}/{m[1].lower()}"
               for m in FAILED_CHECK.finditer(log)}
    errors = "\n".join(ERROR_LINE.findall(log))
    for m in FAILED_CONFIG.finditer(errors):
        folders.add(f"{root}/overlays/ov{m[1]}" if m[1] else root)
    for m in FAILED_MODULE.finditer(errors):
        overlay = m[1] or m[2]
        folders.add(f"{root}/overlays/ov{int(overlay):03d}" if overlay else root)
    sources = set(FAILED_FILE.findall(errors))
    for path in glob.glob(f"{root}/**/delinks.txt", recursive=True) if sources else ():
        text = read(path)
        if any(re.search(rf"(?m)^{re.escape(src)}:", text) for src in sources):
            folders.add(os.path.dirname(path).replace("\\", "/"))
    return folders


def failed_modules(log, region):
    folders = failed_folders(log, region)
    changed = run("git", "diff", "--name-only", "--", f"config/{region}/arm9")[1].split()
    return [path for path in changed if os.path.dirname(path) in folders]


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def usa_gate(module, start, src):
    r = subprocess.run([sys.executable, f"{kitpaths.KIT}/wgate.py", module, f"{start:08x}", os.path.abspath(src)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, DQIX_REPO=os.getcwd()))
    lines = (r.stdout + r.stderr).strip().splitlines()
    return next((l for l in lines if l.startswith(("MATCH", "RESIDUE"))), lines[-1] if lines else "no output")


def usa_block(src, body, functions, taken, module):
    text = TEXT.findall(body)
    if not os.path.isfile(src):
        return "the source file is missing"
    if len(text) != 1 or set(SECTION.findall(body)) != {".text"}:
        return f"owns {', '.join(SECTION.findall(body))}, not one .text range"
    tag = USA_TAG.search(read(src))
    if not tag:
        return "no `// USA:` tag"
    raw = TAG_ADDRESS.fullmatch(tag.group(1))
    by_address = {start: (start, size) for start, size in functions.values()}
    hit = by_address.get(int(raw.group(1), 16)) if raw else functions.get(tag.group(1))
    if not hit:
        return f"its tag {tag.group(1)} names no usa function in this module"
    start, size = hit
    if any(a < start + size and start < b for a, b in taken):
        return f"{tag.group(1)} overlaps a file usa already delinks"
    lo, hi = (int(v, 16) for v in text[0])
    if hi - lo != size:
        verdict = usa_gate(module, start, src)
        if verdict != "MATCH":
            return f"{hi - lo:#x} bytes here, {tag.group(1)} is {size:#x} in usa, and the usa gate says {verdict}"
    taken.append((start, start + size))
    lines = [TEXT.sub(f".text start:0x{start:08x} end:0x{start + size:08x}", l) for l in body.splitlines()]
    return [f"{src}:"] + lines


def into_usa():
    targets = {p.replace("\\", "/"): read(p) for p in glob.glob("config/usa/arm9/**/delinks.txt", recursive=True)}
    wired = {src for text in targets.values() for src, _ in BLOCK.findall(text)}
    skipped = {}
    for region in PORTS:
        for path in sorted(glob.glob(f"config/{region}/arm9/**/delinks.txt", recursive=True)):
            target = "config/usa/" + path.replace("\\", "/").split("/", 2)[2]
            symbols = target[:-len("delinks.txt")] + "symbols.txt"
            functions = ({n: (int(a, 16), int(s, 16)) for n, s, a in FUNCTION.findall(read(symbols))}
                         if os.path.isfile(symbols) else {})
            taken = [(int(a, 16), int(b, 16)) for _, body in BLOCK.findall(targets.get(target, ""))
                     for a, b in TEXT.findall(body)]
            overlay = re.search(r"/overlays/ov(\d{3})/", target)
            module = overlay.group(1) if overlay else "main"
            for src, body in BLOCK.findall(read(path)):
                if src in wired:
                    continue
                block = usa_block(src, body, functions, taken, module) if target in targets else f"no {target}"
                if isinstance(block, str):
                    skipped.setdefault(src, f"{region}: {block}")
                    continue
                nl = "\r\n" if "\r\n" in targets[target] else "\n"
                targets[target] = targets[target].rstrip("\r\n") + nl * 2 + nl.join(block) + nl
                wired.add(src)
                skipped.pop(src, None)
    for target, text in targets.items():
        if text != read(target):
            with open(target, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
    return skipped


def changed(region):
    return bool(run("git", "status", "--porcelain", "--", f"config/{region}")[1].strip())


def settle(outs):
    done = {region: (0, f"{region}: in sync") for region in outs if not changed(region)}
    todo = [region for region in outs if region not in done]
    files = {region: ported(region) for region in todo}
    first = green([*todo, HOME]) if todo else {}
    dropped = {region: failed_modules(first[region][1], region) for region in todo if not first[region][0]}
    for paths in dropped.values():
        if paths:
            run("git", "checkout", "--", *paths)
    retry = [region for region, paths in dropped.items() if paths]
    again = green(retry) if retry else {}
    for region in todo:
        ok, log = first[region]
        if region in again:
            ok = again[region][0] and changed(region)
            log += again[region][1]
        done[region] = finish(region, ok, dropped.get(region, []), files[region], outs[region] + log)
    return done


def finish(region, ok, dropped, files, log):
    if dropped or not ok:
        path = f"{kitpaths.SP}/wlog/regionsync_{region}_{time.strftime('%m%d_%H%M')}.log"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(log)
    if not ok:
        run("git", "checkout", "--", f"config/{region}")
        return 1, f"{region}: RED after porting {files} files, restored; log {path}"
    files = ported(region)
    run("git", "add", "--", f"config/{region}")
    message = f"Port {files} matched files to {region.upper()}" if files else f"Port USA names to {region.upper()}"
    code, out = run("git", "commit", "-q", "-m", message)
    if code:
        run("git", "reset", "-q", "--", f"config/{region}")
        run("git", "checkout", "--", f"config/{region}")
        return 1, f"{region}: commit failed, restored: {out.strip()[-200:]}"
    if dropped:
        return 1, f"{region}: {message}; restored red {', '.join(sorted({os.path.dirname(p) for p in dropped}))}; log {path}"
    return 0, f"{region}: {message}"


def port_inputs(region):
    digest = hashlib.sha1()
    for root in (f"config/{HOME}", f"config/{region}"):
        for folder, _, names in sorted(os.walk(root)):
            for name in sorted(names):
                path = os.path.join(folder, name)
                with open(path, "rb") as fh:
                    digest.update(path.replace("\\", "/").encode() + b"\0" + fh.read())
    def git(*args, feed=None):
        return subprocess.run(["git", *args], input=feed, capture_output=True, text=True, encoding="utf-8",
                              errors="replace").stdout
    blobs = {}
    for line in git("ls-files", "-s", "-z", "--", "src", "include", "tools").split("\0"):
        meta, _, path = line.partition("\t")
        if len(meta.split()) == 3:
            blobs[path] = meta.split()[1]
    entries = iter(git("status", "--porcelain", "-z", "-uall", "--", "src", "include", "tools").split("\0"))
    dirty = []
    for entry in entries:
        if len(entry) > 3:
            dirty.append(entry[3:])
            if entry[0] in "RC":
                dirty.append(next(entries, ""))
    present = [path for path in dirty if os.path.isfile(path)]
    for path in dirty:
        blobs.pop(path, None)
    if present:
        blobs.update(zip(present, git("hash-object", "--stdin-paths", feed="\n".join(present) + "\n").split()))
    digest.update("\n".join(f"{path} {sha}" for path, sha in sorted(blobs.items())).encode())
    return digest.hexdigest()


def port(region, tool):
    if not os.path.isfile(tool) or "--sync" not in run(sys.executable, tool, "--help")[1]:
        return (0, f"{region}: {tool} has no --sync, not ported"), ""
    if not os.path.isdir(f"extract/{region}"):
        return (0, f"{region}: no extracted {region} ROM, not ported"), ""
    stamp = f"build/{region}/ported"
    if os.path.isfile(stamp) and read(stamp) == port_inputs(region):
        return None, ""
    if region in READS_OBJECTS:
        compile_objects(region)
    before = {}
    for folder, _, names in os.walk(f"config/{region}"):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, "rb") as fh:
                before[path] = (os.stat(path), fh.read())
    code, out = run(sys.executable, tool, "--sync")
    if code:
        run("git", "checkout", "--", f"config/{region}")
        return (1, f"{region}: {tool} --sync failed: {out.strip().splitlines()[-1:]}"), ""
    for path, (st, data) in before.items():
        if os.path.isfile(path) and os.stat(path).st_mtime_ns != st.st_mtime_ns:
            with open(path, "rb") as fh:
                if fh.read() == data:
                    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    os.makedirs(os.path.dirname(stamp), exist_ok=True)
    with open(stamp, "w", encoding="utf-8", newline="") as fh:
        fh.write(port_inputs(region))
    return None, out


def sync(pairs):
    lines, outs, skipped = {}, {}, {}
    for region, tool in pairs:
        if region == "usa":
            skipped, outs[region] = into_usa(), ""
            continue
        done, out = port(region, tool)
        if done:
            lines[region] = done
        else:
            outs[region] = out
    lines.update(settle(outs))
    if "usa" in lines:
        code, line = lines["usa"]
        if skipped:
            line = (line.replace("usa: in sync", "usa: nothing ported") + f"; {len(skipped)} file(s) NOT IN USA:\n"
                    + "\n".join(f"  NOT IN USA {src}: {why}" for src, why in sorted(skipped.items())))
        lines["usa"] = (code | bool(skipped), line)
    return [lines[region] for region, _ in pairs]


def gate_main():
    regions = [region for region in PORTS if os.path.isdir(f"extract/{region}")]
    results, blocking = gate(regions)
    ok, log = results[HOME]
    sys.stdout.buffer.write((log if log.endswith("\n") else log + "\n").encode("utf-8", "replace"))
    for region in regions:
        good, text = results.get(region, (True, ""))
        verdict = ("not built: the landing does not reach it" if region not in results else "green" if good
                   else "RED" if region in blocking else "red at its own config, not this landing's")
        print(f"GATE {region}: {verdict}", flush=True)
        if not good:
            os.makedirs(f"{kitpaths.SP}/wlog", exist_ok=True)
            with open(f"{kitpaths.SP}/wlog/gate_{region}.txt", "w", encoding="utf-8") as fh:
                fh.write(text)
    sys.exit(0 if ok and not blocking else 1)


def main():
    args = [a for a in sys.argv[1:] if a != "--gate"]
    if len(args) > 1 or args[:1] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    if args:
        os.chdir(args[0])
    if "--gate" in sys.argv:
        gate_main()
    status = 0
    try:
        for pairs in ([("usa", None)], list(PORTS.items())):
            for code, line in sync(pairs):
                status |= code
                print(line)
    finally:
        configure(HOME)
    sys.exit(status)


if __name__ == "__main__":
    main()
