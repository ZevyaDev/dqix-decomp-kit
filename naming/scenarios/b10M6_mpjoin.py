import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/guest.sav", "state": "states/mp_joined.1.mst"}
PLAY = kitpaths.PLAY
BATTLE = 0x02114E04
LOG = os.path.join(kitpaths.SP, "names", "b10", "M6", "b10M6_mpjoin.log")
SHOTS = os.path.join(kitpaths.SP, "names", "b10", "M6", "mpjoin")
ROUTE = [
    (["Down"], 30), (["Left"], 45), (["Down"], 80), (["Left"], 40), (["Down"], 60), (None, 150),
    (["Down"], 16), (["Right"], 94), (["Down"], 150), (None, 150),
    (["Down"], 180), (["Left"], 180), (["Down", "Left"], 30),
]


def shot(F, i, name):
    from PIL import Image
    px = bytes(F.cons[i].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(SHOTS, f"f{F.cons[0].frames}_{name}.png"))


def both(F, keys, frames):
    for c in F.cons:
        c.set_keys(keys or [])
    F.run(frames)
    for c in F.cons:
        c.set_keys([])


def note(F, log, tag):
    g, h = F.pos(0), F.pos(1)
    log.write(f"f{F.cons[0].frames} {tag} guest {g[0]:.2f},{g[1]:.2f} battle {F.cons[0].read(BATTLE, 1)[0]} "
              f"host {h[0]:.2f},{h[1]:.2f} battle {F.cons[1].read(BATTLE, 1)[0]}\n")


def play(F):
    from melonds_mcp.native import Console

    os.makedirs(SHOTS, exist_ok=True)
    work = tempfile.mkdtemp(prefix="dyn_host_")
    host = Console(nickname="NamingHost")
    try:
        save = os.path.join(work, "host.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "host.sav"), save)
        host.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        host.load_state(os.path.join(PLAY, "states", "mp_joined.0.mst"))
        F.cons.append(host)
        with open(LOG, "w", encoding="utf-8") as log:
            F.run(30)
            note(F, log, "start")
            hx, hz = F.pos(1)
            F.move_to(0, tx=hx, tz=hz, max_steps=200)
            note(F, log, "gathered")
            for keys, frames in ROUTE:
                both(F, keys, frames)
                note(F, log, "+".join(keys) if keys else "wait")
            for _ in range(10):
                if F.cons[1].read(BATTLE, 1)[0] == 3 or F.cons[0].read(BATTLE, 1)[0] == 3:
                    break
                both(F, ["Left"], 24)
                note(F, log, "Left")
            for n in range(6):
                F.run(150)
                note(F, log, "after")
                shot(F, 0, f"guest{n}")
                shot(F, 1, f"host{n}")
    finally:
        if host in F.cons:
            F.cons.remove(host)
        host.close()
        shutil.rmtree(work, ignore_errors=True)
