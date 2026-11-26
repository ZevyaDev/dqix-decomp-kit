import os
import shutil
import tempfile

import kitpaths

STATES = os.path.join(kitpaths.SP, "names", "b8", "M6")
START = {"save": "states/host.sav", "state": os.path.join(STATES, "inn_menu.0.mst")}
PLAY = kitpaths.PLAY


def play(F):
    import dqix_flows
    from melonds_mcp.native import Console

    work = tempfile.mkdtemp(prefix="dyn_guest_")
    guest = Console(nickname="NamingGuest")
    try:
        save = os.path.join(work, "guest.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "guest.sav"), save)
        guest.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        guest.load_state(os.path.join(STATES, "inn_menu.1.mst"))
        F.cons.append(guest)
        dqix_flows.advance(F, 0, 6, 90)
    finally:
        if guest in F.cons:
            F.cons.remove(guest)
        guest.close()
        shutil.rmtree(work, ignore_errors=True)
