#!/usr/bin/env python3
import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
# The compiler, flags and include paths the BUILD uses, read from tools/configure.py itself.
# wgate, classify and the repair sweeps each carried their own copy of the flag list, so the
# rebase onto sp2p2 left every one of them measuring on a compiler the ROM is no longer built
# with. Importing the build's own definitions is the only arrangement they cannot drift from.
import ast
import os
import re
import sys

REPO = _kp.REPO
_TOOLS = os.path.join(REPO, "tools")
# usa, jpn, or eur. Validated once in kitpaths. config/, extract/ and build/ follow this name.
REGION = _kp.region()


def _load():
    cwd, argv = os.getcwd(), sys.argv[:]
    os.chdir(REPO)
    sys.argv = ["configure.py", REGION]
    sys.path.insert(0, _TOOLS)
    try:
        import configure
        return configure
    finally:
        os.chdir(cwd)
        sys.argv = argv
        if _TOOLS in sys.path:
            sys.path.remove(_TOOLS)


def _mwcc_defines(configure):
    '''The -d flags on configure.py's mwcc rule, for the region it was loaded with.

    $game_version is the ninja variable that rule uses for usa and jpn. The gate
    does not run ninja, so that variable is expanded to the loaded region.
    '''
    path = configure.__file__
    source = open(path, encoding="utf-8").read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "region_defines":
                value = eval(compile(ast.Expression(node.value), path, "eval"), configure.__dict__)
                return value.replace("$game_version", REGION)
    return f"-d {REGION}"


_cfg = _load()

MWCC_VERSION = _cfg.MWCC_VERSION
DECOMP_ME_COMPILER = _cfg.DECOMP_ME_COMPILER
CC = f"{REPO}/tools/mwccarm/{MWCC_VERSION}/mwccarm.exe"
AS = f"{REPO}/tools/mwccarm/{MWCC_VERSION}/mwasmarm.exe"
AS_FLAGS = _cfg.AS_FLAGS.split()
FLAGS = (_cfg.CC_FLAGS + " " + _cfg.CC_INCLUDES + " " + _mwcc_defines(_cfg)).split()
CODEGEN_PRAGMA = re.compile(r"(?m)^[ \t]*#[ \t]*pragma[ \t]+(?!(?:define_section|section|once)\b)(\w+)")


def region_names():
    """Every region tree on disk, not the active one. Rename and merge walk this."""
    return [name for name in ("usa", "jpn", "eur")
            if os.path.isdir(os.path.join(REPO, "config", name))]


def config_dir(mod, region=None):
    root = f"config/{region or REGION}/arm9"
    return root if mod == "main" else f"{root}/overlays/ov{mod}"


def config_root():
    return config_dir("main")


def config_roots():
    return [config_dir("main", name) for name in region_names()]


def extract_root():
    return f"extract/{REGION}"


def build_root():
    return f"build/{REGION}"


def report_path():
    return f"{build_root()}/report.json"


def pristine(mod, region=None):
    name = region or REGION
    if mod == "main":
        return f"extract/{name}/arm9/arm9.bin"
    return f"extract/{name}/arm9_overlays/ov{mod}.bin"


def lcf_symbols():
    overlays = [d for d in os.listdir(f"{REPO}/{config_dir('main')}/overlays") if re.fullmatch(r"ov\d+", d)]
    return {f"OVERLAY_{int(d[2:])}_ID": int(d[2:]) for d in overlays}


def cc_path(version):
    return f"{REPO}/tools/mwccarm/{version}/mwccarm.exe" if version else CC


if __name__ == "__main__":
    if "--region" in sys.argv:
        print(REGION)
    elif "--cc" in sys.argv:
        print(CC)
    elif "--flags" in sys.argv:
        print(" ".join(FLAGS))
    else:
        print("MWCC", MWCC_VERSION)
        print("CC  ", CC)
        print("FLAGS", " ".join(FLAGS))
