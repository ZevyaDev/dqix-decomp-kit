import importlib.util
import os
import shutil
import tempfile

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
START = {"save": "states/guest.sav", "state": "states/mp_joined.1.mst"}
PLAY = kitpaths.PLAY
BATTLE = 0x02114E04


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROUTE = load("GS2_mpbattle").ROUTE


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
        for keys, frames in ROUTE:
            if keys:
                F.hold(1, keys, frames)
            else:
                F.run(frames)
        for _ in range(8):
            if F.cons[1].read(BATTLE, 1)[0] == 3:
                break
            F.hold(1, ["Left"], 24)
        F.run(300)
    finally:
        if host in F.cons:
            F.cons.remove(host)
        host.close()
        shutil.rmtree(work, ignore_errors=True)
