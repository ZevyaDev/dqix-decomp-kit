import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(kitpaths.SP, "names", "b12", "O2")
GAME_STATE = 0x020F33D8
ZONE = 0x020FB3F0
PARTY_ZONE = GAME_STATE + 0x2A04 + 0x2C94
STATE_ZONE = GAME_STATE + 0x7E74
SEND_CALL = 0x021D0D58 + 0x38


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


confess = load("C6_confess")
sound = load("C_sound")
START = confess.START


def log_path(name):
    base = os.path.join(OUT, name)
    path, n = base, 1
    while os.path.exists(path):
        n += 1
        path = f"{base[:-4]}.r{n}.log"
    return path


def state(con):
    zone = struct.unpack("<H", con.read(ZONE, 2))[0]
    party_zone = struct.unpack("<I", con.read(PARTY_ZONE, 4))[0]
    state_zone = struct.unpack("<I", con.read(STATE_ZONE, 4))[0]
    return f"zone {zone} party+0x2c94 {party_zone} GameState+0x7e74 {state_zone}"


def play(F):
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    with open(log_path("churchzone.log"), "w", encoding="utf-8", newline="\n") as log:
        log.write(f"f{con.frames} start {state(con)}\n")
        probe = sound.probe_of(F)
        point = con.add_breakpoint(SEND_CALL)
        forward = probe.hit

        def hit(brk):
            if brk.id == point:
                regs = con.regs()
                packet = con.read(regs["r1"], 8)
                log.write(f"f{con.frames} pc {regs['pc']:#x} r1 {regs['r1']:#x} packet {packet.hex()} {state(con)}\n")
            else:
                forward(brk)

        probe.hit = hit
        try:
            confess.play(F)
        finally:
            probe.hit = forward
            con.remove_point(point)
        log.write(f"f{con.frames} end {state(con)}\n")
