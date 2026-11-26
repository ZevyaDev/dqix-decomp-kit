import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/host.sav", "state": "states/mp_joined.0.mst"}
PLAY = kitpaths.PLAY
OUT = os.path.join(kitpaths.SP, "names", "b10", "O2", "mptalk")


def shot(F, name):
    from PIL import Image

    for i, c in enumerate(F.cons):
        px = bytes(c.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"f{F.cons[0].frames}_{name}_c{i}.png"))


def play(F):
    from melonds_mcp.native import Console

    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="dyn_guest_")
    guest = Console(nickname="NamingGuest")
    try:
        save = os.path.join(work, "guest.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "guest.sav"), save)
        guest.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        guest.load_state(os.path.join(PLAY, "states", "mp_joined.1.mst"))
        F.cons.append(guest)
        F.run(30)
        hx, hz = F.pos(0)
        F.move_to(1, tz=hz + 1.1)
        F.move_to(1, tx=hx, tol=0.2)
        F.move_to(1, tz=hz + 1.0, tol=0.2)
        shot(F, "near")
        F.hold(1, ["Up"], 2)
        F.run(4)
        F.hold(1, ["A"], 3)
        for n in range(6):
            F.run(60)
            shot(F, f"talk{n}")
        for n in range(4):
            F.hold(1, ["A"], 3)
            F.run(90)
            shot(F, f"next{n}")
    finally:
        if guest in F.cons:
            F.cons.remove(guest)
        guest.close()
        shutil.rmtree(work, ignore_errors=True)
