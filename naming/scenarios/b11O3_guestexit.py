import os
import shutil
import struct
import tempfile

import kitpaths

START = {"save": "states/guest.sav", "state": "states/mp_joined.1.mst"}
PLAY = kitpaths.PLAY
ZONE = 0x020FB3F0
GAME_STATE = 0x020F33D8
OUT = os.path.join(kitpaths.SP, "names", "b11", "O3", "guestexit")


def play(F):
    from melonds_mcp.native import Console
    from PIL import Image

    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "guestexit.log"), "w")
    work = tempfile.mkdtemp(prefix="dyn_host_")
    host = Console(nickname="NamingHost")

    def zone(i):
        return struct.unpack("<H", F.cons[i].read(ZONE, 2))[0]

    def note(tag):
        x, z = F.pos(0)
        log.write(f"f{F.cons[0].frames} {tag}: guest zone {zone(0)} pos ({x:.2f}, {z:.2f}); host zone {zone(1)}\n")
        for index in range(4):
            obj = struct.unpack("<I", F.cons[0].read(GAME_STATE + 8 + 4 * index, 4))[0]
            if 0x02000000 <= obj < 0x02400000:
                follows, slot, leader = struct.unpack("<bbb", F.cons[0].read(obj + 0x1C8, 3))
                log.write(f"  object {index} {obj:#x} +0x1c8 {follows} +0x1c9 {slot} +0x1ca {leader}\n")
        log.flush()

    def shot(tag):
        px = bytes(F.cons[0].screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"f{F.cons[0].frames}_{tag}.png"))

    try:
        save = os.path.join(work, "host.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "host.sav"), save)
        host.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        host.load_state(os.path.join(PLAY, "states", "mp_joined.0.mst"))
        F.cons.append(host)
        F.run(30)
        note("start")
        shot("start")
        F.move_to(0, tz=12.0)
        F.move_to(0, tx=0.0)
        note("lined up")
        start_zone = zone(0)
        for _ in range(40):
            F.hold(0, ["Down"], 6)
            if zone(0) != start_zone:
                break
        note("after walk")
        F.run(240)
        note("settled")
        shot("settled")
    finally:
        log.close()
        if host in F.cons:
            F.cons.remove(host)
        host.close()
        shutil.rmtree(work, ignore_errors=True)
