import importlib.util
import os
import struct

import kitpaths

GAME_STATE = 0x020F33D8
OUT = os.path.join(kitpaths.SP, "names", "b11", "M2")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(os.path.dirname(__file__), name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def u16(b, off):
    return struct.unpack_from("<H", b, off)[0]


def i32(b, off):
    return struct.unpack_from("<i", b, off)[0]


def state(F, index, moves):
    addr = struct.unpack("<I", F.cons[0].read(GAME_STATE + 8 + 4 * index, 4))[0]
    if not 0x02000000 <= addr < 0x02400000:
        return addr, None
    b = F.cons[0].read(addr, 0x1d0)
    key = (u16(b, 0xAE), b[0xBE], u16(b, 0xC4), b[0xE0], b[0x1CE], (i32(b, 0x6C) >> 18) & 1, b[0x40] >> 3)
    if moves:
        key += (i32(b, 0x44), i32(b, 0x4C), i32(b, 0x54))
    text = (f"x {i32(b, 0x44):#x} z {i32(b, 0x4C):#x} ry {i32(b, 0x54):#x} ae {key[0]:#x} "
            f"be {key[1]} b2 {u16(b, 0xB2):#x} c4 {key[2]:#x} e0 {key[3]:#x} 1ce {key[4]:#x} "
            f"flag18 {key[5]} alpha {key[6]}")
    return addr, (key, text)


def watch(F, play, indices, logname, moves=False):
    base = type(F)
    seen = {}
    log = open(os.path.join(OUT, logname), "w", encoding="utf-8")

    def note():
        for i in indices:
            addr, cur = state(F, i, moves)
            if cur is None:
                continue
            if seen.get(i) != (addr, cur[0]):
                seen[i] = (addr, cur[0])
                log.write(f"f{F.cons[0].frames} obj {i:#x} @{addr:08x} {cur[1]}\n")

    class Watched(base):
        def run(self, frames):
            result = None
            for _ in range(frames):
                result = base.run(self, 1)
                note()
            return result

    F.__class__ = Watched
    try:
        play(F)
    finally:
        F.__class__ = base
        log.close()


BATTLE = load("battle")
START = BATTLE.START


def play(F):
    watch(F, BATTLE.play, [0, 1, 2, 3, 0xC0], "battleface.log", moves=True)
