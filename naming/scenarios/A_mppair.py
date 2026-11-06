import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/guest.sav", "state": "states/mp_joined.1.mst"}
PLAY = os.environ.get("DQIX_PLAY") or os.path.join(os.path.dirname(kitpaths.KIT), "dqix-play")


def play(F):
    from melonds_mcp.native import Console

    work = tempfile.mkdtemp(prefix="dyn_host_")
    host = Console(nickname="NamingHost")
    try:
        save = os.path.join(work, "host.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "host.sav"), save)
        host.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        host.load_state(os.path.join(PLAY, "states", "mp_joined.0.mst"))
        F.cons.append(host)
        F.run(300)
    finally:
        if host in F.cons:
            F.cons.remove(host)
        host.close()
        shutil.rmtree(work, ignore_errors=True)
