"""Small instance of the existing Ninja rules, for the old/new graph proof."""
import argparse
from pathlib import Path
import sys
import time
import ninja_syntax

parser = argparse.ArgumentParser()
parser.add_argument("version")
args = parser.parse_args()
LD = "tools/cache_command.py"
DSD = LD
WINE = sys.executable
includes = [Path("include")]


class Project:
    def __init__(self, region):
        self.game_version = region
        self.game_config = Path("config") / region
        self.game_build = Path(".")

    def baserom(self):
        return Path("base.nds")

    def baserom_config(self):
        return Path("rom.yaml")

    def arm9_lcf(self):
        return Path("arm9.lcf")

    def arm9_objects_txt(self):
        return Path("objects.txt")

    def source_object_files(self):
        return ["a.o", "b.o"]

    def arm9_delink_yaml(self):
        return Path("delink.yaml")


def main():
    with Path("build.ninja").open("w", encoding="utf-8") as stream:
        n = ninja_syntax.Writer(stream)
        n.rule("mwld", f'"{WINE}" {LD} link -nostdlib {globals().get("LD_FLAGS", "")}')
        n.rule("mwcc", f'"{WINE}" {LD} compile -o a.o --delay 0.1', depfile="a.d")
        reference = "config/usa/arm9/expected.bin"
        check_args = " --reference " + reference if Path(reference).is_file() else ""
        n.rule("check_modules", f'"{WINE}" {DSD} modules{check_args}')
        n.rule("check_symbols", f'"{WINE}" {DSD} symbols')
        n.rule("check_delinks", f'"{WINE}" tools/check_delinks.py objects.txt')
        n.build("a.o", "mwcc", "source.cpp", variables={"basefile": "a"})
        n.build("arm9.o", "mwld", ["a.o", "b.o", "objects.txt", "arm9.lcf"])
        n.build("check_modules", "check_modules", "arm9.o")
        n.build("check_symbols", "check_symbols", "arm9.o")
        n.build("check_delinks", "check_delinks", "objects.txt")
        n.build("check", "phony", ["check_modules", "check_symbols", "check_delinks"])
    time.sleep(0.05)


if __name__ == "__main__":
    main()
