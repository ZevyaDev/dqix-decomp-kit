import os
import shutil
import struct
import tempfile

import kitpaths

START = {"save": "states/host.sav", "state": "states/found_world.0.mst"}
PLAY = kitpaths.PLAY
OUT = os.path.join(kitpaths.SP, "names", "b10", "M1", "join")
WIRELESS = 0x020FEFEC


def note(F, log, name):
    for n, c in enumerate(F.cons):
        state = struct.unpack("<i", c.read(WIRELESS, 4))[0]
        joined, count = c.read(WIRELESS + 0x100C, 2)
        slots = list(c.read(WIRELESS + 0x1038, 4))
        log.write(f"f{c.frames} {name} con{n} state {state} joined {joined:#04x} count {count} slots {slots}\n")
    log.flush()


def shot(F, log, name):
    from PIL import Image
    for n, c in enumerate(F.cons):
        px = bytes(c.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"f{c.frames}_con{n}_{name}.png"))
    note(F, log, name)


def play(F):
    from melonds_mcp.native import Console

    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="dyn_guest_")
    guest = Console(nickname="NamingGuest")
    log = open(os.path.join(OUT, "join.log"), "w", encoding="utf-8")
    try:
        save = os.path.join(work, "guest.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "guest.sav"), save)
        guest.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        guest.load_state(os.path.join(PLAY, "states", "found_world.1.mst"))
        F.cons.append(guest)
        F.run(60)
        shot(F, log, "start")
        for step in range(8):
            F.hold(1, ["A"], 4)
            F.run(150)
            shot(F, log, f"a{step}")
            if F.cons[0].read(WIRELESS + 0x100C, 1)[0] & 2:
                break
    finally:
        log.close()
        if guest in F.cons:
            F.cons.remove(guest)
        guest.close()
        shutil.rmtree(work, ignore_errors=True)
