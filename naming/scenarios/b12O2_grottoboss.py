import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_STATE = 0x020F33D8
OUT = os.path.join(kitpaths.SP, "names", "b12", "O2")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


grotto = load("grotto")
START = grotto.START


def log_path(name):
    base = os.path.join(OUT, name)
    path, n = base, 1
    while os.path.exists(path):
        n += 1
        path = f"{base[:-4]}.r{n}.log"
    return path


class Watch:
    def __init__(self, field, log):
        self.field = field
        self.log = log
        self.last = None
        con = field.cons[0]
        resources = struct.unpack("<I", con.read(GAME_STATE, 4))[0]
        self.manager = struct.unpack("<I", con.read(resources + 0x3718, 4))[0]
        log.write(f"resources {resources:#x} manager {self.manager:#x}\n")

    def note(self):
        con = self.field.cons[0]
        zone = struct.unpack("<H", con.read(grotto.ZONE, 2))[0]
        flags = con.read(self.manager + 0x40, 2)
        now = (zone, flags[0], flags[1])
        if now != self.last:
            self.log.write(f"f{con.frames} zone {zone} manager+0x40 {flags[0]} +0x41 {flags[1]}\n")
            self.last = now

    def run(self, frames):
        for _ in range(frames):
            self.field.run(1)
            self.note()

    def hold(self, i, keys, frames):
        self.field.hold(i, keys, frames)
        self.note()

    def __getattr__(self, name):
        return getattr(self.field, name)


def play(F):
    os.makedirs(OUT, exist_ok=True)
    with open(log_path("grottoboss.log"), "w", encoding="utf-8", newline="\n") as log:
        W = Watch(F, log)
        W.note()
        grotto.play(W)
