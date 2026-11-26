"""The naming pass's play data and emulator: the saves and savestates scenarios start from, and the
ZevyaDev/melonDS headless build dyn.py drives.

    python naming/play.py fetch               download the data release named in naming/play/data.json
                                              into kitpaths.PLAY and verify every file
    python naming/play.py check               everything dyn.py needs, ending in a savestate that loads
                                              and runs; prints READY or each missing piece
    python naming/play.py pack DIR TAG        maintainers: zip DIR's saves/ and states/, publish it as
                                              kit release TAG, rewrite naming/play/data.json
"""
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import kitpaths

DATA_JSON = os.path.join(HERE, "play", "data.json")
ASSET = "dqix-play-data.zip"
MELONDS_URL = "https://github.com/ZevyaDev/melonDS"
MELONDS_MIN = "39e48836bb16741f2fa9dde4fdd0ea29cb456c30"
PACKAGES = ("capstone", "PIL", "yaml", "numpy")
SMOKE = ("states/host.sav", "states/inn.0.mst")
POS_ADDR = 0x0210A134


def kit_repo():
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", kitpaths.KIT_URL)
    return m.group(1)


def digest(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest():
    with open(DATA_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def stale(files):
    out = []
    for rel, sha1 in sorted(files.items()):
        path = os.path.join(kitpaths.PLAY, rel)
        if not os.path.isfile(path):
            out.append(f"missing {rel}")
        elif digest(path, "sha1") != sha1:
            out.append(f"changed {rel}")
    return out


def fetch():
    m = manifest()
    if not stale(m["files"]):
        print(f"play data {m['tag']} already in {kitpaths.PLAY}")
        return 0
    url = f"https://github.com/{kit_repo()}/releases/download/{m['tag']}/{ASSET}"
    os.makedirs(kitpaths.PLAY, exist_ok=True)
    part = os.path.join(kitpaths.PLAY, ASSET + ".part")
    print(f"downloading {url} ({m['size'] >> 20} MiB)")
    with urllib.request.urlopen(url) as resp, open(part, "wb") as out:
        shutil.copyfileobj(resp, out, 1 << 20)
    if digest(part, "sha256") != m["sha256"]:
        os.remove(part)
        print(f"FAIL {ASSET}: sha256 differs from naming/play/data.json")
        return 1
    with zipfile.ZipFile(part) as z:
        z.extractall(kitpaths.PLAY)
    os.remove(part)
    bad = stale(m["files"])
    for line in bad:
        print(f"FAIL {line}")
    if bad:
        return 1
    print(f"play data {m['tag']}: {len(m['files'])} files in {kitpaths.PLAY}")
    return 0


def scenario_inputs():
    out = {}
    for path in sorted(glob.glob(os.path.join(HERE, "scenarios", "*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for rel in re.findall(r'"((?:saves|states)/[^"]+\.(?:sav|mst))"', text):
            out.setdefault(rel, []).append(name)
        for a, b in re.findall(r'os\.path\.join\(PLAY, "(saves|states)", "([^"]+)"\)', text):
            out.setdefault(f"{a}/{b}", []).append(name)
    return out


def melonds_problems():
    root = kitpaths.MELONDS
    if not os.path.isdir(os.path.join(root, "tools", "melonds-mcp")):
        return [f"no melonDS checkout at {root}: git clone -b debug {MELONDS_URL} (or set DQIX_MELONDS)"]
    r = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", MELONDS_MIN, "HEAD"],
                       capture_output=True, text=True)
    if r.returncode:
        return [f"{root} is not ZevyaDev/melonDS debug at {MELONDS_MIN[:8]} or later: git -C {root} pull"]
    return []


def smoke():
    sys.path.insert(0, os.path.join(kitpaths.MELONDS, "tools", "melonds-mcp"))
    try:
        from melonds_mcp.native import Console
    except Exception as e:
        return [f"melonds_mcp does not import: {e}"]
    rom = os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds")
    save_src, state = (os.path.join(kitpaths.PLAY, rel) for rel in SMOKE)
    work = tempfile.mkdtemp(prefix="playcheck_")
    try:
        con = Console(nickname="Check")
    except Exception as e:
        return [f"melonds_headless does not load ({e}): build it, see naming/HANDOFF.md"]
    try:
        save = os.path.join(work, "game.sav")
        shutil.copyfile(save_src, save)
        con.load_rom(rom, save=save)
        con.load_state(state)
        con.run(60)
        x, _, z = struct.unpack("<3i", con.read(POS_ADDR, 12))
        if not (x or z):
            return [f"{SMOKE[1]} loaded but the hero has no position after 60 frames"]
    except Exception as e:
        return [f"{SMOKE[1]} does not load and run: {e}"]
    finally:
        con.close()
        shutil.rmtree(work, ignore_errors=True)
    return []


def check():
    problems = []
    for name in PACKAGES:
        if importlib.util.find_spec(name) is None:
            problems.append(f"python package {name} missing: python -m pip install -e "
                            f"{kitpaths.MELONDS}/tools/melonds-mcp")
    problems += melonds_problems()
    rom = os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds")
    if not os.path.isfile(rom):
        problems.append(f"no USA base ROM at {rom} (docs/SETUP.md)")
    data = stale(manifest()["files"])
    if data:
        problems.append(f"play data incomplete ({len(data)} file(s), first: {data[0]}): "
                        f"python naming/play.py fetch")
    for rel, users in sorted(scenario_inputs().items()):
        if not os.path.isfile(os.path.join(kitpaths.PLAY, rel)):
            problems.append(f"scenario input {rel} missing (used by {', '.join(users[:4])})")
    if not problems:
        problems = smoke()
    for line in problems:
        print(f"MISSING {line}")
    print("READY" if not problems else f"NOT READY: {len(problems)} item(s)")
    return 1 if problems else 0


def pack(src, tag):
    files = {}
    for sub in ("saves", "states"):
        for path in sorted(glob.glob(os.path.join(src, sub, "**", "*"), recursive=True)):
            if os.path.isfile(path):
                files[os.path.relpath(path, src).replace("\\", "/")] = path
    missing = sorted(set(scenario_inputs()) - set(files))
    if missing:
        print("FAIL scenario inputs not in " + src + ": " + ", ".join(missing))
        return 1
    out = os.path.join(tempfile.mkdtemp(prefix="playpack_"), ASSET)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, path in files.items():
            z.write(path, rel)
    r = subprocess.run(["gh", "release", "create", tag, out, "-R", kit_repo(), "--title", f"Naming play data {tag}",
                        "--notes", "Saves and savestates for naming/scenarios. Fetch with `python naming/play.py fetch`."],
                       capture_output=True, text=True)
    if r.returncode:
        print(f"FAIL gh release create: {r.stderr.strip()}")
        return 1
    data = {"tag": tag, "sha256": digest(out, "sha256"), "size": os.path.getsize(out),
            "files": {rel: digest(path, "sha1") for rel, path in files.items()}}
    with open(DATA_JSON, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"released {tag}: {len(files)} files, {data['size'] >> 20} MiB; commit naming/play/data.json")
    return 0


def main():
    args = sys.argv[1:]
    if args == ["fetch"]:
        return fetch()
    if args == ["check"]:
        return check()
    if len(args) == 3 and args[0] == "pack":
        return pack(args[1], args[2])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
