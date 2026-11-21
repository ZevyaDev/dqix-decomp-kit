import importlib.util
import os
import struct
import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_STATE = 0x020F33D8
OUT = os.path.join(kitpaths.SP, "names", "b9", "D", "battleitem")


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
    log = open(os.path.join(OUT, "battleitem.log"), "w")

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def dump(tag):
        log.write(f"f{con.frames} {tag}\n")
        for index in range(4):
            obj = u32(GAME_STATE + 8 + 4 * index)
            data = u32(obj + 0x150) if 0x02000000 <= obj < 0x02400000 else 0
            if 0x02000000 <= data < 0x02400000:
                held = struct.unpack("<8h", con.read(data + 0x454, 16))
                log.write(f"  object {index} {obj:#x} data {data:#x} +0x454 {[hex(h & 0xFFFF) for h in held]}\n")
        log.flush()

    dump("start")
    BASE.play(F)
    dump("end")
    log.close()
