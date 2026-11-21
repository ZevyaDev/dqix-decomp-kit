import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/host.sav", "state": "states/mp_joined.0.mst"}
PLAY = os.environ.get("DQIX_PLAY") or os.path.join(os.path.dirname(kitpaths.KIT), "dqix-play")


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
        F.run(240)
        guest.reset()
        F.run(1500)
        for _ in range(6):
            F.hold(0, ["A"], 4)
            F.run(200)
    finally:
        if guest is not None:
            if guest in F.cons:
                F.cons.remove(guest)
            guest.close()
        shutil.rmtree(work, ignore_errors=True)
