import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_STATE = 0x020F33D8
OUT = os.path.join(kitpaths.SP, "names", "b11", "O3", "scenewatch")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load("battle")
START = BASE.START


def play(F):
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "scenewatch.log"), "w")

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def valid(a):
        return 0x02000000 <= a < 0x02400000

    last = {}

    def watch():
        resources = u32(GAME_STATE)
        manager = u32(resources + 0x3718) if valid(resources) else 0
        scene = u32(manager + 0x6AC) if valid(manager) else 0
        now = {"scene": scene}
        if valid(scene):
            now["flags"] = u32(scene + 0x55F4)
            now["anchor"] = struct.unpack("<i", con.read(scene + 0xC18 + 0x224, 4))[0]
        for key, value in now.items():
            if last.get(key) != value:
                log.write(f"f{con.frames} {key} {value & 0xFFFFFFFF:#x}\n")
                last[key] = value
        log.flush()

    step = F.run

    def run(frames):
        result = None
        for _ in range(frames):
            result = step(1)
            watch()
        return result

    F.run = run
    watch()
    BASE.play(F)
    log.close()
