#!/usr/bin/env python3
"""Generate the existing decomp Ninja graph with opt-in link/check content caching.

Run from the decomp checkout: python "$DQIX_KIT/cached_build.py" usa [configure options].
Then use the normal explicit Ninja targets. DQIX_CACHE_COLD=1 forces real commands.
Running tools/configure.py directly restores the original graph.
"""
import os
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import sys

import kitpaths
from build_cache import canonical, digest, file_hash, lock, compile_unchanged


STAGES = {"mwld", "check_modules", "check_symbols", "check_delinks"}


def supported_link_flags(flags):
    if flags is None:
        return True
    args = shlex.split(flags)
    valued = {"-proc", "-m", "-map", "-msgstyle", "-force_active"}
    switches = {"-nostdlib", "-interworking", "-nodead"}
    index = 0
    while index < len(args):
        if args[index] in valued and index + 1 < len(args):
            index += 2
        elif args[index] in switches:
            index += 1
        else:
            return False
    return "-nostdlib" in args and "-map" in args


def compile_dependencies(inputs, depfile):
    paths = list(inputs)
    if Path(depfile).is_file():
        # mwcc/transform_dep writes one header path per continuation line.
        lines = Path(depfile).read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            name = line.strip().removesuffix("\\").strip()
            if name:
                paths.append(name)
    return [str(Path(name).absolute()) for name in paths]


def generate(options):
    namespace = digest(str(Path(kitpaths.REPO).resolve()).encode("utf-8"))[:16]
    with lock(Path(kitpaths.SP) / "build-cache" / namespace / "configure.lock"):
        return _generate(options)


def _generate(options):
    repo = Path(kitpaths.REPO)
    if repo.resolve() != Path.cwd().resolve():
        raise ValueError("run cached_build.py from the DQIX_REPO checkout")
    configure = repo / "tools/configure.py"
    sys.path.insert(0, str(configure.parent))
    previous_argv = sys.argv
    sys.argv = [str(configure), *options]
    try:
        cfg = runpy.run_path(str(configure), run_name="_cached_configure")
        syntax = cfg["ninja_syntax"]
        original = syntax.Writer
        project = cfg["Project"](cfg["args"].version)
        namespace = digest(str(repo.resolve()).encode("utf-8"))[:16]
        cache = Path(kitpaths.SP) / "build-cache" / namespace / project.game_version
        cache.mkdir(parents=True, exist_ok=True)
        runner = Path(__file__).with_name("build_cache.py")
        config_inputs = [str(project.game_config / "arm9"), str(project.baserom()),
                         str(project.baserom_config()), str(configure)]
        tools = [cfg["LD"], str(Path(cfg["LD"]).parent), cfg["DSD"]]
        if cfg["WINE"]:
            tools.append(cfg["WINE"])
        seen = set()
        link_supported = supported_link_flags(cfg.get("LD_FLAGS"))
        if not link_supported:
            print("Unsupported linker dependencies/options: using the original full link", flush=True)
        compile_inputs = {}
        hashed = {}
        compile_targets = []
        compiler_files = {}
        # Snapshot headers even before a first compile has discovered its depfile.
        for include in cfg.get("includes", []):
            for path in sorted(Path(include).rglob("*")):
                if path.is_file():
                    name = str(path.absolute())
                    hashed[name] = file_hash(path)
                    compile_inputs[name] = hashed[name]
        (cache / "configure-options.json").write_bytes(canonical(options))

        class CachedWriter(original):
            def rule(self, name, command, **kwargs):
                if name in STAGES:
                    seen.add(name)
                    if name != "mwld" or link_supported:
                        command = '"%s" "%s" "$cache_spec" -- %s' % (sys.executable, runner, command)
                    if name == "mwld" and link_supported:
                        kwargs["restat"] = True
                return super().rule(name, command, **kwargs)

            def build(self, outputs, rule, inputs=None, implicit=None, **kwargs):
                if rule in ("mwcc", "mwasm"):
                    variables = dict(kwargs.get("variables", {}) or {})
                    target = Path(outputs)
                    depfile = variables.get("basefile", str(target.with_suffix(""))) + ".d"
                    cc = variables.get("cc_exe", cfg.get("CC" if rule == "mwcc" else "AS"))
                    base = [inputs]
                    if cc:
                        directory = str(Path(cc).parent.absolute())
                        if directory not in compiler_files:
                            compiler_files[directory] = [str(path.absolute()) for path in sorted(Path(directory).iterdir())
                                                         if path.is_file()]
                        base += compiler_files[directory]
                    if cfg["WINE"]:
                        base.append(cfg["WINE"])
                    paths = compile_dependencies(base, depfile)
                    for name in paths:
                        if name not in hashed:
                            hashed[name] = file_hash(name) if Path(name).is_file() else None
                        if hashed[name] is not None:
                            compile_inputs[name] = hashed[name]
                    proof = canonical([[name, hashed[name]] for name in paths])
                    stamp = cache / "compile" / (digest(str(target).encode("utf-8")) + ".json")
                    # No compilation result is reused solely on mtime. Unknown/new provenance
                    # and same-mtime source/header changes rebuild the dependent object only.
                    if not stamp.is_file() or stamp.read_bytes() != proof:
                        target.unlink(missing_ok=True)
                        stamp.parent.mkdir(parents=True, exist_ok=True)
                        temporary = stamp.with_suffix(".pending")
                        temporary.write_bytes(proof)
                        os.replace(temporary, stamp)
                    compile_targets.append({"inputs": [str(Path(name).absolute()) for name in base], "depfile": depfile,
                                            "stamp": str(stamp)})
                if rule in STAGES:
                    source_inputs = [inputs] if isinstance(inputs, str) else list(inputs or [])
                    explicit_outputs = [outputs] if isinstance(outputs, str) else list(outputs)
                    spec = {"stage": rule, "region": project.game_version, "cache_dir": str(cache),
                            "tools": tools if rule == "mwld" else [cfg["DSD"], str(configure)],
                            "inputs": source_inputs + config_inputs,
                            "outputs": explicit_outputs if rule == "mwld" else [],
                            "objects_file": str(project.arm9_objects_txt()),
                            "lcf": str(project.arm9_lcf()), "target_dir": str(project.game_build)}
                    if rule == "mwld":
                        spec["compile_inputs"] = compile_inputs
                        (cache / "compile-targets.json").write_bytes(canonical(compile_targets))
                    if rule == "check_delinks":
                        spec["tools"] = ["tools/check_delinks.py"]
                    path = cache / (rule + ".json")
                    temporary = path.with_suffix(".pending")
                    temporary.write_bytes(canonical(spec))
                    os.replace(temporary, path)
                    variables = dict(kwargs.pop("variables", {}) or {})
                    variables["cache_spec"] = str(path)
                    kwargs["variables"] = variables
                    dependencies = [implicit] if isinstance(implicit, str) else list(implicit or [])
                    dependencies += [str(runner), str(path)]
                    if rule == "check_delinks":
                        # The original edge reads every response-file object but waits only
                        # for objects.txt, so it can silently skip objects still compiling.
                        dependencies += list(project.source_object_files()) + [str(project.arm9_delink_yaml())]
                    if rule == "mwld":
                        # A content probe also catches same-mtime object/config edits.
                        dependencies.append("cache_link_probe")
                    implicit = dependencies
                return super().build(outputs, rule, inputs=inputs, implicit=implicit, **kwargs)

        syntax.Writer = CachedWriter
        try:
            cfg["main"]()
        finally:
            syntax.Writer = original
        if seen != STAGES:
            raise ValueError("configure.py did not expose the supported link/check rules")
        with (repo / "build.ninja").open("a", encoding="utf-8") as stream:
            original(stream).build("cache_link_probe", "phony")
        return cache
    finally:
        sys.argv = previous_argv


def finish_compile_proofs(cache):
    spec = json.loads((cache / "mwld.json").read_text(encoding="utf-8"))
    if not compile_unchanged(spec):
        raise ValueError("compile inputs changed during the build")
    expected = spec["compile_inputs"]
    for target in json.loads((cache / "compile-targets.json").read_text(encoding="utf-8")):
        paths = compile_dependencies(target["inputs"], target["depfile"])
        if all(name in expected for name in paths):
            proof = canonical([[name, expected[name]] for name in paths])
            stamp = Path(target["stamp"])
            if stamp.read_bytes() != proof:
                temporary = stamp.with_suffix(".pending")
                temporary.write_bytes(proof)
                os.replace(temporary, stamp)


if __name__ == "__main__":
    try:
        if len(sys.argv) > 2 and sys.argv[1] == "build":
            region = sys.argv[2]
            namespace = digest(str(Path(kitpaths.REPO).resolve()).encode("utf-8"))[:16]
            options_file = Path(kitpaths.SP) / "build-cache" / namespace / region / "configure-options.json"
            options = json.loads(options_file.read_text(encoding="utf-8"))
            cache = generate(options)
            print("Build cache: %s" % cache, flush=True)
            targets = sys.argv[3:]
            if targets[:1] == ["--"]:
                targets = targets[1:]
            if not targets or not any(not x.startswith("-") for x in targets):
                raise ValueError("name explicit Ninja targets, such as check rom sha1")
            result = subprocess.run(["ninja", *targets])
            if result.returncode == 0:
                finish_compile_proofs(cache)
            sys.exit(result.returncode)
        else:
            print("Build cache: %s" % generate(sys.argv[1:]))
    except (OSError, ValueError) as error:
        sys.exit(str(error))
