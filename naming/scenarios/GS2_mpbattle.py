import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/host.sav", "state": "states/mp_joined.0.mst"}
PLAY = os.environ.get("DQIX_PLAY") or os.path.join(os.path.dirname(kitpaths.KIT), "dqix-play")
BATTLE = 0x02114E04
ROUTE = [
    (["Down"], 30), (["Left"], 45), (["Down"], 80), (["Left"], 40), (["Down"], 60), (None, 150),
    (["Down"], 16), (["Right"], 94), (["Down"], 150), (None, 150),
    (["Down"], 180), (["Left"], 180), (["Down", "Left"], 30),
]


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
        F.run(30)
        for keys, frames in ROUTE:
            if keys:
                F.hold(0, keys, frames)
            else:
                F.run(frames)
        for _ in range(8):
            if F.cons[0].read(BATTLE, 1)[0] == 3:
                break
            F.hold(0, ["Left"], 24)
        F.run(900)
    finally:
        if guest in F.cons:
            F.cons.remove(guest)
        guest.close()
        shutil.rmtree(work, ignore_errors=True)
