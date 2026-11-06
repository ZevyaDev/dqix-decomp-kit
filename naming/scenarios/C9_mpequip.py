import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/guest.sav", "state": "states/mp_joined.1.mst"}
PLAY = os.environ.get("DQIX_PLAY") or os.path.join(os.path.dirname(kitpaths.KIT), "dqix-play")


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


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
        F.run(30)
        press(F, "X", 40)
        press(F, "Down", 15)
        press(F, "A", 90)
        press(F, "A", 90)
        press(F, "A", 90)
        press(F, "Down", 20)
        press(F, "A", 120)
        press(F, "A", 120)
        press(F, "A", 120)
        for _ in range(4):
            press(F, "B", 60)
        F.run(300)
    finally:
        if host in F.cons:
            F.cons.remove(host)
        host.close()
        shutil.rmtree(work, ignore_errors=True)
