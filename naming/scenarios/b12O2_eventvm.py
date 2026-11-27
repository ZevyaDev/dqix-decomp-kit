import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(kitpaths.SP, "names", "b12", "O2")
EVENT_VM = 0x02165828


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


event = load("event")
START = event.START


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

    def note(self):
        con = self.field.cons[0]
        loaded = event.slot0(self.field) == event.EVENT_OVERLAY
        if loaded:
            words = struct.unpack("<21i", con.read(EVENT_VM, 0x54))
            now = (1,) + tuple(words[off // 4] for off in (0, 0x30, 0x34, 0x38, 0x3c, 0x40, 0x44, 0x48, 0x4c, 0x50))
        else:
            now = (0,)
        if now != self.last:
            if loaded:
                w = [v & 0xffffffff for v in now[1:]]
                self.log.write(
                    f"f{con.frames} vm+0 {w[0]} +0x30 {w[1]:#x} +0x34 {w[2]:#x} +0x38 {w[3]:#x} +0x3c {w[4]} "
                    f"+0x40 {w[5]} +0x44 {w[6]:#x} +0x48 {w[7]:#x} +0x4c {w[8]:#x} +0x50 {w[9]}\n")
            else:
                self.log.write(f"f{con.frames} ov001 not loaded\n")
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
    with open(log_path("eventvm.log"), "w", encoding="utf-8", newline="\n") as log:
        W = Watch(F, log)
        W.note()
        event.play(W)
