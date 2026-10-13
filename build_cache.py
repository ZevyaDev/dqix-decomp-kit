#!/usr/bin/env python3
"""Content-verified cache for the existing configure.py link/check commands."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

FORMAT = 1
LOCAL_TRANSPORT_ENV = {
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY", "WS_PROXY", "WSS_PROXY",
    "BUNDLE_HTTP_PROXY", "BUNDLE_HTTPS_PROXY", "DOCKER_HTTP_PROXY", "DOCKER_HTTPS_PROXY",
    "NPM_CONFIG_PROXY", "NPM_CONFIG_HTTP_PROXY", "NPM_CONFIG_HTTPS_PROXY",
    "PIP_PROXY", "YARN_HTTP_PROXY", "YARN_HTTPS_PROXY",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(paths):
    """Retain names and input order; never trust timestamps, including on a hit."""
    entries = []
    files_to_hash = {}
    for name in paths:
        path = Path(name)
        if path.is_dir():
            files = sorted(p for p in path.rglob("*") if p.is_file())
            entries.append([str(path), "directory", [str(p) for p in files]])
        else:
            files = [path]
        for item in files:
            name = str(item)
            entries.append([name, None, None])
            files_to_hash.setdefault(name, item)
    def read(item):
        return item.stat().st_size, file_hash(item)
    workers = max(1, min(32, int(os.environ.get("DQIX_CACHE_JOBS", "4"))))
    items = list(files_to_hash.values())
    if len(items) > 1 and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            values = list(pool.map(read, items))
    else:
        values = [read(item) for item in items]
    hashed = dict(zip(files_to_hash, values))
    for entry in entries:
        if entry[1] is None:
            entry[1], entry[2] = hashed[entry[0]]
    return entries


def objects(path):
    # dsd's objects.txt is one literal path per line, as check_delinks.py reads it.
    result = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines()
              if line.strip()]
    if any(name.startswith(("@", "-")) for name in result):
        raise ValueError("unknown response-file syntax")
    for name in result:
        if not Path(name).is_file():
            raise FileNotFoundError(name)
    return result


def memory_outputs(spec):
    text = Path(spec["lcf"]).read_text(encoding="utf-8")
    memory = re.search(r"(?ms)^MEMORY\s*\{(.*?)^\}", text)
    if not memory or re.search(r"(?im)^\s*(INCLUDE|INPUT|GROUP|SEARCH_DIR)\b", text):
        raise ValueError("unsupported LCF dependencies")
    redirects = re.findall(r">\s*(\S+)", memory.group(1))
    if len(redirects) != memory.group(1).count(">"):
        raise ValueError("unknown LCF output syntax")
    result = []
    for name in redirects:
        path = Path(spec["target_dir"]) / name
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("LCF output outside the build directory")
        result.append(str(path))
    return result


def link_outputs(spec):
    result = list(spec["outputs"])
    if spec["stage"] == "mwld":
        # -map closure,unused writes <ELF filename>.xMAP, including the .o extension.
        result += [name + ".xMAP" for name in spec["outputs"]]
        result += memory_outputs(spec)
    return result


def context(spec, command):
    # Keep environment values private. Changes still invalidate the command's success.
    # These four stages only read local files. Session-specific transport proxy
    # endpoints are not their inputs; leave the real process environment untouched.
    env = {k: v for k, v in os.environ.items()
           if k not in ("DQIX_CACHE_COLD", "DQIX_CACHE_JOBS", "_", "SHLVL", "OLDPWD")
           and k.upper() not in LOCAL_TRANSPORT_ENV}
    executable = shutil.which(command[0]) or command[0]
    tools = [executable, sys.executable, __file__] + spec.get("tools", [])
    return {"format": FORMAT, "stage": spec["stage"], "region": spec["region"],
            "isa": spec.get("isa", "arm946e/interworking"), "cwd": str(Path.cwd()), "command": command,
            "environment": digest(canonical(env)), "python": sys.version,
            "tools": fingerprint(tools)}


def compile_unchanged(spec):
    return all(file_hash(path) == expected for path, expected in spec.get("compile_inputs", {}).items())


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def read_entry(entry, key, outputs):
    try:
        manifest = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
        if (manifest["format"] != FORMAT or manifest["key"] != key or
                manifest["outputs"] != outputs or manifest["returncode"] != 0):
            return None
        hashes = manifest["hashes"]
        if len(hashes) != len(outputs):
            return None
        for i, expected in enumerate(hashes):
            if file_hash(entry / str(i)) != expected:
                return None
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        return None


def restore(entry, manifest):
    # Validate the entire entry before changing any output, then install each file atomically.
    for i, name in enumerate(manifest["outputs"]):
        path = Path(name)
        if path.is_file() and file_hash(path) == manifest["hashes"][i]:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".cache-", dir=path.parent)
        os.close(fd)
        try:
            shutil.copyfile(entry / str(i), temporary)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def publish(entry, key, outputs):
    entry.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=entry.parent))
    try:
        hashes = []
        for i, name in enumerate(outputs):
            shutil.copyfile(name, temporary / str(i))
            hashes.append(file_hash(temporary / str(i)))
        manifest = {"format": FORMAT, "key": key, "outputs": outputs,
                    "hashes": hashes, "returncode": 0}
        (temporary / "manifest.json").write_bytes(canonical(manifest))
        if entry.exists():
            shutil.rmtree(entry)
        os.rename(temporary, entry)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def run(command):
    started = time.perf_counter()
    if os.name != "nt":
        import resource
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
    code = subprocess.run(command).returncode
    elapsed = time.perf_counter() - started
    cpu = None
    if os.name != "nt":
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime
    return code, elapsed, cpu


def record(spec, start, status, code, elapsed=0, cpu=None, **detail):
    row = {"stage": spec["stage"], "region": spec["region"], "status": status,
           "returncode": code, "started_at": start, "finished_at": time.time(),
           "wall_seconds": time.time() - start, "process_seconds": elapsed,
           "process_cpu_seconds": cpu, **detail}
    row["wrapper_cpu_seconds"] = time.process_time() - spec["cpu_start"]
    row["relinked_units"] = int(spec["stage"] == "mwld" and status in ("cold", "miss") and code == 0)
    log = Path(spec["cache_dir"]) / "timings.jsonl"
    with lock(log.with_suffix(".lock")):
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    print("CACHE %s %s %s %.3fs" % (spec["region"], spec["stage"], status, row["wall_seconds"]),
          flush=True)
    return code


def cached_delinks(spec, command, start, cold):
    names = objects(spec["objects_file"])
    normalized = ["<object-list>" if x == spec["objects_file"] else x for x in command]
    common = context(spec, normalized)
    root = Path(spec["cache_dir"]) / "delinks"
    pending = []
    states = fingerprint(names)
    for name, state in zip(names, states):
        state = [state]
        key = digest(canonical([common, state]))
        entry = root / key
        if cold or read_entry(entry, key, []) is None:
            pending.append((name, key, entry, state))
    if not pending:
        return record(spec, start, "hit", 0, hits=len(names), misses=0,
                      inputs=len(names), input_bytes=sum(Path(p).stat().st_size for p in names))
    with tempfile.TemporaryDirectory(prefix="delink-check-", dir=spec["cache_dir"]) as temp:
        subset = Path(temp) / "objects.txt"
        subset.write_text("".join(str(Path(p).absolute()) + "\n" for p, _, _, _ in pending),
                          encoding="utf-8")
        actual = [str(subset) if x == spec["objects_file"] else x for x in command]
        code, elapsed, cpu = run(actual)
    if code == 0:
        after = fingerprint([p for p, _, _, _ in pending])
        if common != context(spec, normalized) or any([current] != old for current, (_, _, _, old) in zip(after, pending)):
            return record(spec, start, "inputs-changed", 1, elapsed, cpu)
        for _, key, entry, _ in pending:
            publish(entry, key, [])
    return record(spec, start, "cold" if cold else "miss", code, elapsed, cpu,
                  hits=len(names) - len(pending), misses=len(pending), inputs=len(names),
                  input_bytes=sum(Path(p).stat().st_size for p in names))


def execute(spec, command):
    spec = dict(spec, cpu_start=time.process_time())
    start = time.time()
    cold = os.environ.get("DQIX_CACHE_COLD") == "1"
    directory = Path(spec["cache_dir"])
    directory.mkdir(parents=True, exist_ok=True)
    name = digest(canonical([str(Path.cwd()), spec["stage"], spec["outputs"]]))
    with lock(directory / "locks" / name):
        if spec["stage"] == "check_delinks":
            return cached_delinks(spec, command, start, cold)
        try:
            if spec["stage"] == "mwld":
                if not compile_unchanged(spec):
                    print("Compile inputs changed: run cached_build.py build before linking", flush=True)
                    return record(spec, start, "compile-inputs-changed", 1)
            outputs = link_outputs(spec)
            paths = list(spec["inputs"])
            if spec["stage"] == "check_modules":
                paths += [spec["lcf"], *memory_outputs(spec)]
            if spec["stage"] == "mwld":
                if "-nostdlib" not in command or any(x.startswith(("-l", "-L", "-cmdfile")) for x in command):
                    raise ValueError("unknown library or command-file dependency")
                paths += objects(spec["objects_file"])
            common = context(spec, command)
            before = fingerprint(paths)
        except (OSError, ValueError) as error:
            # Unknown dependencies can never be a hit or seed a cache entry.
            print("CACHE bypass: %s" % error, flush=True)
            code, elapsed, cpu = run(command)
            return record(spec, start, "bypass", code, elapsed, cpu)
        key = digest(canonical([common, before, outputs]))
        entry = directory / spec["stage"] / key
        manifest = None if cold else read_entry(entry, key, outputs)
        if manifest is not None:
            restore(entry, manifest)
            if before != fingerprint(paths) or common != context(spec, command) or not compile_unchanged(spec):
                return record(spec, start, "inputs-changed", 1)
            return record(spec, start, "hit", 0, key=key, inputs=len(before),
                          input_bytes=sum(x[1] for x in before if isinstance(x[1], int)))
        # Prevent a failed/no-output invocation from publishing a stale output as new success.
        for output in outputs:
            Path(output).unlink(missing_ok=True)
        code, elapsed, cpu = run(command)
        if code == 0:
            if before != fingerprint(paths) or common != context(spec, command):
                return record(spec, start, "inputs-changed", 1, elapsed, cpu)
            if not compile_unchanged(spec):
                return record(spec, start, "compile-inputs-changed", 1, elapsed, cpu)
            if not all(Path(p).is_file() for p in outputs):
                return record(spec, start, "outputs-missing", 1, elapsed, cpu)
            publish(entry, key, outputs)
        return record(spec, start, "cold" if cold else "miss", code, elapsed, cpu,
                      key=key, inputs=len(before),
                      input_bytes=sum(x[1] for x in before if isinstance(x[1], int)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    try:
        return execute(spec, command)
    except (OSError, ValueError, KeyError) as error:
        print("CACHE error: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
