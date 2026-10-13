"""Behavioral proofs shared by regress.py and the standalone fixture runner."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
import build_cache as cache


def elf(covered=True):
    # ELF32 LE with .text, a symbol/string table and section-name table.
    strings = b"\0f\0.text\0"
    names = b"\0.text\0.symtab\0.strtab\0.shstrtab\0"
    payload = b"\0" * 4
    symbol = struct.pack("<IIIBBH", 1 if covered else 3, 0, 4, 0x12 if covered else 3, 0, 1)
    offsets = [52, 56, 72, 72 + len(strings)]
    section_offset = offsets[3] + len(names)
    header = bytearray(52)
    header[:16] = b"\x7fELF\x01\x01\x01" + b"\0" * 9
    struct.pack_into("<HHIIIIIHHHHHH", header, 16, 1, 40, 1, 0, 0, section_offset, 0,
                     52, 0, 0, 40, 5, 4)
    sections = b"\0" * 40
    for name, kind, flags, offset, size, link, alignment, entry_size in [
            (1, 1, 6, offsets[0], 4, 0, 4, 0),
            (7, 2, 0, offsets[1], 16, 3, 4, 16),
            (15, 3, 0, offsets[2], len(strings), 0, 1, 0),
            (23, 3, 0, offsets[3], len(names), 0, 1, 0)]:
        sections += struct.pack("<IIIIIIIIII", name, kind, flags, 0, offset, size, link, 0,
                                alignment, entry_size)
    return bytes(header) + payload + symbol + strings + names + sections


class CacheProofs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cwd = Path.cwd()
        os.chdir(self.root)
        Path("a.o").write_bytes(elf())
        Path("b.o").write_bytes(elf())
        Path("objects.txt").write_text("a.o\nb.o\n", encoding="utf-8")
        Path("arm9.lcf").write_text("MEMORY {\n ARM9 : ORIGIN = 0 > build/arm9.bin\n}\n"
                                     "SECTIONS {\n}\n", encoding="utf-8")
        Path("symbols.txt").write_text("f=0\n", encoding="utf-8")
        Path("tool.version").write_text("1", encoding="utf-8")
        self.spec = {"stage": "mwld", "region": "usa", "cache_dir": str(self.root / "cache"),
                     "inputs": ["arm9.lcf", "objects.txt", "symbols.txt"],
                     "outputs": ["arm9.o"], "lcf": "arm9.lcf", "objects_file": "objects.txt",
                     "target_dir": ".", "tools": [str(KIT / "regress_fixtures/cache_command.py"),
                                                  "tool.version"]}
        self.command = [sys.executable, str(KIT / "regress_fixtures/cache_command.py"),
                        "link", "-nostdlib"]

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def invoke(self, command=None):
        self.assertEqual(cache.execute(self.spec, command or self.command), 0)

    def calls(self):
        return Path("calls.txt").read_text(encoding="utf-8").splitlines()

    def test_identical_and_cold_outputs(self):
        self.invoke()
        cold = {p: Path(p).read_bytes() for p in ("arm9.o", "arm9.o.xMAP", "build/arm9.bin")}
        self.invoke()
        self.assertEqual(self.calls(), ["link"])
        for p in cold:
            Path(p).unlink()
        self.invoke()
        self.assertEqual(self.calls(), ["link"])
        self.assertEqual(cold, {p: Path(p).read_bytes() for p in cold})
        with patch.dict(os.environ, {"DQIX_CACHE_COLD": "1"}):
            self.invoke()
        self.assertEqual(self.calls(), ["link", "link"])

    def test_all_content_and_order_invalidations(self):
        self.invoke()
        for path in ("a.o", "symbols.txt", "arm9.lcf", "tool.version"):
            stamp = Path(path).stat()
            Path(path).write_bytes(Path(path).read_bytes() + b"\n")
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            before = len(self.calls())
            self.invoke()
            self.assertEqual(len(self.calls()), before + 1, path)
        for names in ("b.o\na.o\n", "a.o\n", "b.o\na.o\nb.o\n"):
            Path("objects.txt").write_text(names, encoding="utf-8")
            before = len(self.calls())
            self.invoke()
            self.assertEqual(len(self.calls()), before + 1)
        Path("b.o").rename("renamed.o")
        Path("objects.txt").write_text("a.o\nrenamed.o\n", encoding="utf-8")
        self.invoke()
        self.spec["region"] = "jpn"
        self.invoke()
        self.invoke(self.command + ["--delay", "0.001"])
        self.assertEqual(len(self.calls()), 11)

    def test_corruption_is_never_a_hit(self):
        self.invoke()
        entry = next((Path("cache") / "mwld").iterdir())
        (entry / "0").write_bytes(b"broken")
        self.invoke()
        self.assertEqual(len(self.calls()), 2)
        (entry / "manifest.json").write_text("{", encoding="utf-8")
        self.invoke()
        self.assertEqual(len(self.calls()), 3)

    def test_isa_and_cache_format_invalidate(self):
        self.invoke()
        self.spec["isa"] = "thumb-only-fixture"
        self.invoke()
        with patch.object(cache, "FORMAT", cache.FORMAT + 1):
            self.invoke()
        self.assertEqual(len(self.calls()), 3)

    def test_failures_and_missing_output_do_not_publish(self):
        for command in (self.command + ["--fail"], self.command + ["--no-output"]):
            self.assertNotEqual(cache.execute(self.spec, command), 0)
        self.assertFalse((Path("cache") / "mwld").exists())
        self.invoke()
        self.assertEqual(len(self.calls()), 3)

    def test_parallel_same_entry_runs_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(lambda _: cache.execute(self.spec, self.command + ["--delay", "0.1"]), range(2)))
        self.assertEqual(codes, [0, 0])
        self.assertEqual(self.calls(), ["link"])

    def test_parallel_hashing_preserves_input_order(self):
        names = ["b.o", "a.o", "b.o", "symbols.txt"]
        with patch.dict(os.environ, {"DQIX_CACHE_JOBS": "1"}):
            serial = cache.fingerprint(names)
        with patch.dict(os.environ, {"DQIX_CACHE_JOBS": "4"}):
            parallel = cache.fingerprint(names)
        self.assertEqual(serial, parallel)

    def test_unknown_link_dependencies_bypass_cache(self):
        import cached_build
        self.assertTrue(cached_build.supported_link_flags("-proc arm946e -nostdlib -map closure,unused -nodead"))
        for flags in ("-nostdlib -map closure -L external", "-nostdlib @nested.txt", "-partial"):
            self.assertFalse(cached_build.supported_link_flags(flags))

    def test_session_proxy_changes_are_not_offline_link_inputs(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:1001"}):
            self.invoke()
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:1002"}):
            self.invoke()
        self.assertEqual(self.calls(), ["link"])
        with patch.dict(os.environ, {"MWLibraryFiles": "changed-runtime-library-list"}):
            self.invoke()
        self.assertEqual(self.calls(), ["link", "link"])

    def test_inputs_changing_during_command_are_rejected(self):
        real_run = cache.run
        def changed(command):
            result = real_run(command)
            Path("a.o").write_bytes(b"changed after read")
            return result
        with patch.object(cache, "run", changed):
            self.assertNotEqual(cache.execute(self.spec, self.command), 0)
        self.assertFalse((Path("cache") / "mwld").exists())

    def test_interrupted_command_leaves_no_success_entry(self):
        self.assertEqual(cache.execute(self.spec, self.command + ["--interrupt"]), 130)
        self.assertTrue(Path("arm9.o").is_file())
        self.assertFalse(Path("arm9.o.xMAP").exists())
        self.assertFalse((Path("cache") / "mwld").exists())
        self.invoke()

    def test_delink_only_changed_elf_is_checked_and_errors_survive(self):
        checker = Path(os.environ["DQIX_REPO"]) / "tools/check_delinks.py"
        self.spec.update(stage="check_delinks", outputs=[], tools=[str(checker)])
        command = [sys.executable, str(checker), "objects.txt", "-s", "symbols.txt"]
        self.invoke(command)
        self.invoke(command)
        rows = [json.loads(row) for row in Path("cache/timings.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(r["hits"], r["misses"]) for r in rows], [(0, 2), (2, 0)])
        Path("a.o").write_bytes(elf(False))
        self.assertEqual(cache.execute(self.spec, command), 1)
        Path("a.o").write_bytes(elf() + b"new metadata")
        self.invoke(command)
        row = json.loads(Path("cache/timings.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((row["hits"], row["misses"]), (1, 1))
        Path("a.o").unlink()
        with self.assertRaises(FileNotFoundError):
            cache.execute(self.spec, command)

    def make_ninja_project(self):
        repo = Path(os.environ["DQIX_REPO"])
        Path("tools").mkdir()
        for source, target in [(KIT / "regress_fixtures/cache_configure.py", "tools/configure.py"),
                               (KIT / "regress_fixtures/cache_command.py", "tools/cache_command.py"),
                               (repo / "tools/check_delinks.py", "tools/check_delinks.py"),
                               (repo / "tools/ninja_syntax.py", "tools/ninja_syntax.py")]:
            shutil.copyfile(source, target)
        Path("config/usa/arm9").mkdir(parents=True)
        Path("config/usa/arm9/symbols.txt").write_text("f=0", encoding="utf-8")
        Path("base.nds").write_bytes(b"synthetic ROM identity fixture")
        Path("rom.yaml").write_text("rom: base.nds", encoding="utf-8")
        Path("delink.yaml").write_text("generated objects", encoding="utf-8")
        Path("include").mkdir()
        Path("include/shared.h").write_text("header v1", encoding="utf-8")
        Path("source.cpp").write_text("source v1", encoding="utf-8")

    def test_changed_source_non_match_agrees_with_normal_cold_build(self):
        # All inputs are generated fixtures. No commercial tools or game ROM.
        self.make_ninja_project()
        env = dict(os.environ, DQIX_REPO=str(self.root), DQIX_STATE=str(self.root / "state"),
                   DQIX_NO_FRESHNESS="1")
        def command(*args, expected=0):
            result = subprocess.run(args, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            return result.stdout + result.stderr
        adapter = [sys.executable, str(KIT / "cached_build.py")]
        build = adapter + ["build", "usa", "--", "-j1", "check"]
        command(*adapter, "usa")
        command(*build)
        reference = Path("arm9.o").read_bytes()
        Path("config/usa/arm9/expected.bin").write_bytes(reference)
        # Establish a successful cached validation with the fixed reference.
        command(*build)
        before = self.calls().count("compile")
        stamp = Path("source.cpp").stat()
        Path("source.cpp").write_text("source v2 deliberately does not match", encoding="utf-8")
        os.utime("source.cpp", ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        # Reproduce the old false match: ordinary Ninja misses the same-mtime edit.
        command(sys.executable, "tools/configure.py", "usa")
        command("ninja", "-j1", "check")
        self.assertEqual(Path("arm9.o").read_bytes(), reference)
        self.assertEqual(self.calls().count("compile"), before)
        log = command(*build, expected=1)
        bad = Path("arm9.o").read_bytes()
        self.assertIn("NON_MATCH", log)
        self.assertNotEqual(bad, reference)
        self.assertEqual(self.calls().count("compile"), before + 1)
        # Repeating the bad source may reuse its link, but must still fail the check.
        links = self.calls().count("link")
        self.assertIn("NON_MATCH", command(*build, expected=1))
        self.assertEqual(self.calls().count("link"), links)
        # Rebuild the same bad source through the unmodified Ninja graph.
        command(sys.executable, "tools/configure.py", "usa")
        Path("a.o").unlink()
        Path("arm9.o").unlink()
        self.assertIn("NON_MATCH", command("ninja", "-j1", "check", expected=1))
        self.assertEqual(Path("arm9.o").read_bytes(), bad)
        # Restoring the original source is the only way back to the known match.
        Path("source.cpp").write_text("source v1", encoding="utf-8")
        os.utime("source.cpp", ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        command(*build)
        self.assertEqual(Path("arm9.o").read_bytes(), reference)

    def test_original_ninja_relinks_but_adapter_reuses(self):
        self.make_ninja_project()
        def command(*args, env=None):
            result = subprocess.run(args, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        command(sys.executable, "tools/configure.py", "usa")
        command("ninja", "-j1", "check")
        Path("objects.txt").write_bytes(Path("objects.txt").read_bytes())
        command("ninja", "-j1", "check")
        old = self.calls()
        self.assertEqual(old.count("link"), 2)
        self.assertEqual(old.count("modules"), 2)
        final = Path("arm9.o").read_bytes()
        Path("calls.txt").unlink()
        Path("a.d").unlink()
        env = dict(os.environ, DQIX_REPO=str(self.root), DQIX_STATE=str(self.root.parent / (self.root.name + "-state")),
                   DQIX_NO_FRESHNESS="1")
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _: command(sys.executable, str(KIT / "cached_build.py"), "usa", env=env), range(2)))
            command(sys.executable, str(KIT / "cached_build.py"), "build", "usa", "--", "-j4", "check", env=env)
            Path("objects.txt").write_bytes(Path("objects.txt").read_bytes())
            command("ninja", "-j1", "check", env=env)
            new = self.calls()
            self.assertEqual(new.count("link"), 1)
            self.assertEqual(new.count("modules"), 1)
            self.assertEqual(final, Path("arm9.o").read_bytes())
            # Ninja alone cannot see a same-mtime header edit. The adapter invalidates
            # its dependent object before Ninja evaluates the unmodified compile rule.
            stamp = Path("include/shared.h").stat()
            Path("include/shared.h").write_text("header v2", encoding="utf-8")
            os.utime("include/shared.h", ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            command(sys.executable, str(KIT / "cached_build.py"), "build", "usa", "--", "-j1", "check", env=env)
            self.assertEqual(self.calls().count("compile"), 2)
            self.assertEqual(self.calls().count("link"), 2)
            self.assertNotEqual(final, Path("arm9.o").read_bytes())
            command(sys.executable, str(KIT / "cached_build.py"), "build", "usa", "--", "-j1", "check", env=env)
            self.assertEqual(self.calls().count("compile"), 2)
            self.assertEqual(self.calls().count("link"), 2)
            # A new, untracked linker option must run the original producer and
            # expose its error, rather than reusing a previous successful link.
            with Path("tools/configure.py").open("a", encoding="utf-8") as stream:
                stream.write('\nLD_FLAGS = "--unknown-dependency"\n')
            command(sys.executable, str(KIT / "cached_build.py"), "usa", env=env)
            result = subprocess.run(["ninja", "-j1", "check"], capture_output=True, text=True, env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--unknown-dependency", result.stdout + result.stderr)
        finally:
            shutil.rmtree(env["DQIX_STATE"], ignore_errors=True)


def prove():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CacheProofs)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return None if result.wasSuccessful() else "%d cache proof(s) failed" % (len(result.failures) + len(result.errors))


if __name__ == "__main__":
    sys.exit(1 if prove() else 0)
