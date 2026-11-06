import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/guest.sav", "state": "states/mp_joined.1.mst"}
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

    work = tempfile.mkdtemp(prefix="dyn_host_")
    host = Console(nickname="NamingHost")
    try:
        save = os.path.join(work, "host.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "host.sav"), save)
        host.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        host.load_state(os.path.join(PLAY, "states", "mp_joined.0.mst"))
        F.cons.append(host)
        records(F)
    finally:
        if host in F.cons:
            F.cons.remove(host)
        host.close()
        shutil.rmtree(work, ignore_errors=True)
