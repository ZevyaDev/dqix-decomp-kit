#!/usr/bin/env python3
"""Deterministic link/check fixture; no ROM or commercial tools required."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("stage")
parser.add_argument("--objects", default="objects.txt")
parser.add_argument("--lcf", default="arm9.lcf")
parser.add_argument("-o", default="arm9.o")
parser.add_argument("-nostdlib", action="store_true")
parser.add_argument("--delay", type=float, default=0)
parser.add_argument("--fail", action="store_true")
parser.add_argument("--no-output", action="store_true")
parser.add_argument("--interrupt", action="store_true")
parser.add_argument("--source", default="source.cpp")
parser.add_argument("--header", default="include/shared.h")
args = parser.parse_args()
with Path("calls.txt").open("a", encoding="utf-8") as stream:
    stream.write(args.stage + "\n")
time.sleep(args.delay)
if args.fail:
    sys.exit(1)
if args.stage == "compile":
    output = hashlib.sha256(Path(args.source).read_bytes() + Path(args.header).read_bytes()).digest()
    Path(args.o).write_bytes(output)
    Path(args.o).with_suffix(".d").write_text(args.o + ": " + args.source + " \\\n\t" +
                                            str(Path(args.header).absolute()) + "\n", encoding="utf-8")
if args.stage == "link" and not args.no_output:
    names = Path(args.objects).read_text(encoding="utf-8").splitlines()
    data = Path(args.lcf).read_bytes() + b"".join(Path(p).read_bytes() for p in names if p)
    output = hashlib.sha256(data).digest()
    Path(args.o).parent.mkdir(parents=True, exist_ok=True)
    Path(args.o).write_bytes(output)
    if args.interrupt:
        os._exit(130)
    Path(args.o + ".xMAP").write_bytes(output.hex().encode("ascii"))
    text = Path(args.lcf).read_text(encoding="utf-8")
    memory = re.search(r"(?ms)^MEMORY\s*\{(.*?)^\}", text)
    for name in re.findall(r">\s*(\S+)", memory.group(1)):
        target = Path(args.o).parent / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(output)
