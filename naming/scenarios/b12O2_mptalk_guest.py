import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/guest.sav", "state": "states/mp_joined.1.mst"}
PLAY = kitpaths.PLAY
OUT = os.path.join(kitpaths.SP, "names", "b12", "O2", "mptalk_guest")


def shot(F, out, name):
    from PIL import Image

    for i, c in enumerate(F.cons):
        px = bytes(c.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(out, f"f{F.cons[0].frames}_{name}_c{i}.png"))


def play(F):
    from melonds_mcp.native import Console

    out, n = OUT, 1
    while os.path.exists(out):
        n += 1
        out = f"{OUT}.r{n}"
    os.makedirs(out)
    work = tempfile.mkdtemp(prefix="dyn_host_")
    host = Console(nickname="NamingHost")
    try:
        save = os.path.join(work, "host.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "host.sav"), save)
        host.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        host.load_state(os.path.join(PLAY, "states", "mp_joined.0.mst"))
        F.cons.append(host)
        F.run(30)
        hx, hz = F.pos(1)
        F.move_to(0, tz=hz + 1.1)
        F.move_to(0, tx=hx, tol=0.2)
        F.move_to(0, tz=hz + 1.0, tol=0.2)
        shot(F, out, "near")
        F.hold(0, ["Up"], 2)
        F.run(4)
        F.hold(0, ["A"], 3)
        for n in range(6):
            F.run(60)
            shot(F, out, f"talk{n}")
        for n in range(4):
            F.hold(0, ["A"], 3)
            F.run(90)
            shot(F, out, f"next{n}")
    finally:
        if host in F.cons:
            F.cons.remove(host)
        host.close()
        shutil.rmtree(work, ignore_errors=True)
