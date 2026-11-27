import importlib.util
import os
import struct

_spec = importlib.util.spec_from_file_location("b11M2_battleface", os.path.join(os.path.dirname(__file__), "b11M2_battleface.py"))
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

START = W.START
MANAGERS = {"se": 0x02108760, "bgm": 0x02109BF4}


def play(F):
    base = type(F)
    seen = {}
    log = open(os.path.join(W.OUT, "soundpending.log"), "w", encoding="utf-8")

    class Watched(base):
        def run(self, frames):
            result = None
            for _ in range(frames):
                result = base.run(self, 1)
                for name, addr in MANAGERS.items():
                    value = struct.unpack("<Ihh", F.cons[0].read(addr, 4) + F.cons[0].read(addr + 0xAC, 4))
                    if seen.get(name) != value:
                        seen[name] = value
                        log.write(f"f{F.cons[0].frames} {name} word0 {value[0]:#x} ac {value[1]} ae {value[2]}\n")
            return result

    F.__class__ = Watched
    try:
        W.BATTLE.play(F)
    finally:
        F.__class__ = base
        log.close()
