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
# usa, jpn, or eur. Unset stays usa, which is every current config/ and extract/ path.
REGION = os.environ.get("DQIX_REGION", "usa")


def _system():
    return "Windows" if os.name == "nt" else os.uname().sysname


def _machine():
    if os.name == "nt":
        return os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "")
    return os.uname().machine


def _load():
    import platform
    cwd, argv = os.getcwd(), sys.argv[:]
    probes = platform.system, platform.machine
    os.chdir(REPO)
    sys.argv = ["configure.py", REGION]
    if os.environ.get("DQIX_WINE"):
        sys.argv += ["-w", os.environ["DQIX_WINE"]]
    if os.environ.get("DQIX_PREINSTALLED_COMPILER"):
        sys.argv += ["--compiler", os.environ["DQIX_PREINSTALLED_COMPILER"]]
    sys.path.insert(0, _TOOLS)
    platform.system, platform.machine = _system, _machine
    try:
        import configure
        return configure
    finally:
        platform.system, platform.machine = probes
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
EXE = getattr(_cfg, "EXE", ".exe" if os.name == "nt" else "")
COMPILER_ROOT = os.path.normpath(os.path.join(REPO, str(_cfg.mwcc_root)))
CC = f"{COMPILER_ROOT}/{MWCC_VERSION}/mwccarm.exe"
AS = f"{COMPILER_ROOT}/{MWCC_VERSION}/mwasmarm.exe"
AS_FLAGS = getattr(_cfg, "AS_FLAGS", "-proc arm5TE").split()
FLAGS = (_cfg.CC_FLAGS + " " + _cfg.CC_INCLUDES + " " + _mwcc_defines(_cfg)).split()
from pragmas import CODEGEN_PRAGMA


def config_dir(mod):
    root = f"config/{REGION}/arm9"
    return root if mod == "main" else f"{root}/overlays/ov{mod}"


def pristine(mod):
    if mod == "main":
        return f"extract/{REGION}/arm9/arm9.bin"
    return f"extract/{REGION}/arm9_overlays/ov{mod}.bin"


SDK_LCF_SYMBOLS = {"SDK_IRQ_STACKSIZE": 0x400, "SDK_SYS_STACKSIZE": 0}


def lcf_symbols():
    overlays = [d for d in os.listdir(f"{REPO}/{config_dir('main')}/overlays") if re.fullmatch(r"ov\d+", d)]
    out = {**SDK_LCF_SYMBOLS, **{f"OVERLAY_{int(d[2:])}_ID": int(d[2:]) for d in overlays}}
    head = open(f"{REPO}/{config_dir('main')}/delinks.txt", encoding="utf-8").read().split("\n\n")[0]
    for name, lo, hi in re.findall(r"(?m)^\s*\.(\w+)\s+start:0x([0-9a-fA-F]+)\s+end:0x([0-9a-fA-F]+)", head):
        out[f"ARM9_{name.upper()}_START"] = int(lo, 16)
        out[f"ARM9_{name.upper()}_END"] = int(hi, 16)
    return out


def cc_path(version):
    return f"{COMPILER_ROOT}/{version}/mwccarm.exe" if version else CC


LIBRARIES = {name: (f"src/{root}", ver, list(flags))
             for name, (root, ver, flags) in getattr(_cfg, "LIBRARY_BUILDS", {}).items()}
_LIB_RANGES = os.path.join(_kp.KIT, "lib_ranges.txt")


def lib_ranges(mod):
    out = []
    try:
        for line in open(_LIB_RANGES, encoding="utf-8"):
            p = line.split()
            if len(p) in (5, 6) and p[0] == REGION and p[1] == mod and p[4] in LIBRARIES:
                out.append((int(p[2], 16), int(p[3], 16), p[4], p[5:] == ["either"]))
    except OSError:
        pass
    return out


def lib_zone(mod, addr):
    a = int(addr, 16) if isinstance(addr, str) else addr
    return next(((b, either) for lo, hi, b, either in lib_ranges(mod) if lo <= a < hi), (None, False))


def lib_dir(mod, build):
    root = LIBRARIES[build][0]
    return f"{root}/Main" if mod == "main" else f"{root}/Overlay_{int(mod)}"


def lib_dirs(mod):
    return [lib_dir(mod, b) for b in dict.fromkeys(b for _lo, _hi, b, _e in lib_ranges(mod))]


def path_build(path):
    p = "/" + str(path).replace("\\", "/")
    return next((b for b, (root, _v, _f) in LIBRARIES.items() if f"/{root}/" in p), "game")


BUILDS = {"game": (None, []), **{b: (ver, flags) for b, (_root, ver, flags) in LIBRARIES.items()}}


def build_cc(name):
    return cc_path(BUILDS[name][0])


def build_flags(name):
    return FLAGS + BUILDS[name][1]


def lang_flags(path):
    return ["-lang=c"] if str(path).lower().endswith(".c") else []


SOURCE_EXTS = (".cpp", ".c", ".s")


def is_asm(path):
    return str(path).lower().endswith(".s")


def source_ext(path):
    ext = os.path.splitext(str(path))[1].lower()
    return ext if ext in SOURCE_EXTS else ".cpp"


def compile_command(src, obj, cc, flags):
    if is_asm(src):
        return tool_command(AS) + AS_FLAGS + ["-o", obj, src]
    return tool_command(cc) + list(flags) + ["-c", src, "-o", obj]


def builds_for(mod, addr, path=None):
    own = path_build(path) if path is not None else "game"
    if own != "game":
        return [own]
    build, either = lib_zone(mod, addr)
    return ([build, "game"] if either else [build]) if build else ["game"]


_POSTCOMPILE = []


def postcompile(obj):
    if not _POSTCOMPILE:
        path = os.path.join(_TOOLS, "mwcc.py")
        if os.path.exists(path):
            import importlib.util
            spec = importlib.util.spec_from_file_location("_decomp_mwcc", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _POSTCOMPILE.append(module.strip)
        else:
            _POSTCOMPILE.append(lambda _obj: [])
    return _POSTCOMPILE[0](obj)


def sections(elf, name):
    return [(i, s) for i, s in enumerate(elf.iter_sections()) if s.name == name and s["sh_size"]]


def relocations(elf, index):
    return [s for s in elf.iter_sections()
            if s.header["sh_type"] in ("SHT_REL", "SHT_RELA") and s.header["sh_info"] == index]


def tool_command(executable):
    runner = _cfg.WINE
    if runner and not os.path.isabs(runner) and ("/" in runner or "\\" in runner):
        runner = os.path.normpath(os.path.join(REPO, runner))
    return ([runner] if runner else []) + [executable]


_FRIDA_DEFER = """(function () {
const MSCDECL = Process.platform === 'windows' ? 'mscdecl' : 'sysv';
const text = ptr('0x401000');
const body = function () {
/*BODY*/
};
const mapped = Process.findRangeByAddress(text);
if (mapped !== null && mapped.protection.indexOf('x') !== -1) { body(); return; }
const mprotect = Module.getGlobalExportByName ? Module.getGlobalExportByName('mprotect')
                                              : Module.getExportByName(null, 'mprotect');
const gate = Interceptor.attach(mprotect, {
  onEnter(a) { this.lo = a[0]; this.hi = a[0].add(a[1]); this.prot = a[2].toInt32(); },
  onLeave(rv) {
    if (rv.toInt32() === 0 && (this.prot & 7) === 5 && text.compare(this.lo) >= 0 && text.compare(this.hi) < 0) {
      gate.detach();
      body();
    }
  }
});
})();
"""


def frida_script(js):
    return _FRIDA_DEFER.replace("/*BODY*/", js.replace("'mscdecl'", "MSCDECL"), 1)


def frida_spawn(device, argv, cwd):
    for attempt in range(3):
        pid = device.spawn(argv, cwd=cwd)
        try:
            return pid, device.attach(pid)
        except Exception as e:
            if attempt == 2 or "terminated" not in str(e):
                raise
            print(f"frida: {e} during attach; respawning", file=sys.stderr)


if __name__ == "__main__":
    if "--cc" in sys.argv:
        print(CC)
    elif "--flags" in sys.argv:
        print(" ".join(FLAGS))
    elif "--region" in sys.argv:
        print(REGION)
    elif "--source-exts" in sys.argv:
        print("|".join(e.lstrip(".") for e in SOURCE_EXTS))
    elif "--compiler-root" in sys.argv:
        print(COMPILER_ROOT.replace("\\", "/"))
    elif "--config-dir" in sys.argv:
        print(config_dir(sys.argv[sys.argv.index("--config-dir") + 1]))
    else:
        print("MWCC", MWCC_VERSION)
        print("CC  ", CC)
        print("FLAGS", " ".join(FLAGS))
