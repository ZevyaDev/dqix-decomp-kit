import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/host.sav", "state": "states/mp_joined.0.mst"}
PLAY = os.environ.get("DQIX_PLAY") or os.path.join(os.path.dirname(kitpaths.KIT), "dqix-play")


def records(F):
    F.run(30)
    F.hold(0, ["X"], 4)
    F.run(40)
    F.hold(0, ["Right"], 3)
    F.run(15)
    F.hold(0, ["Down"], 3)
    F.run(15)
    F.hold(0, ["A"], 3)
    F.run(90)
    F.hold(0, ["A"], 3)
    F.run(120)
    F.hold(0, ["A"], 3)
    F.run(90)


def play(F):
    from melonds_mcp.native import Console

    work = tempfile.mkdtemp(prefix="dyn_guest_")
    guest = Console(nickname="NamingGuest")
    try:
        save = os.path.join(work, "guest.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "guest.sav"), save)
        guest.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        guest.load_state(os.path.join(PLAY, "states", "mp_joined.1.mst"))
        F.cons.append(guest)
        records(F)
    finally:
        if guest in F.cons:
            F.cons.remove(guest)
        guest.close()
        shutil.rmtree(work, ignore_errors=True)
