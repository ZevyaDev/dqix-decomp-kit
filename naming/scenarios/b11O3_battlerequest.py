import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_STATE = 0x020F33D8
OUT = os.path.join(kitpaths.SP, "names", "b11", "O3", "battlerequest")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


START = load("battle").START


def play(F):
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "battlerequest.log"), "w")
    resources = struct.unpack("<I", con.read(GAME_STATE, 4))[0]
    manager = struct.unpack("<I", con.read(resources + 0x3718, 4))[0]
    log.write(f"resources {resources:#x} manager {manager:#x}\n")
    last = None
    for frame in range(60):
        block = con.read(manager + 0x1C, 0x38).hex()
        if block != last:
            log.write(f"f{con.frames} +0x1c..+0x53 {block}\n")
            last = block
        if frame < 40:
            F.hold(0, ["Left"], 1)
        else:
            F.run(1)
    log.close()
