import os
import shutil
import struct
import tempfile

import kitpaths

START = {"save": "states/guest.sav", "state": "states/mp_joined.1.mst"}
PLAY = os.environ.get("DQIX_PLAY") or os.path.join(os.path.dirname(kitpaths.KIT), "dqix-play")
NOTICES = 0x02109030
OUT = os.path.join(kitpaths.SP, "names", "b6", "N4a", "hostlost")


def state(con):
    raw = con.read(NOTICES, 0x3d0)
    entries = []
    for i in range(raw[0x3cb]):
        e = raw[i * 0x34:(i + 1) * 0x34]
        entries.append((e[:0x30].split(b"\0")[0], struct.unpack("<h", e[0x30:0x32])[0], struct.unpack("<b", e[0x32:0x33])[0]))
    return (f"count={raw[0x3cb]} shown={raw[0x3c9] & 1} flags3cd={raw[0x3cd]:#x} entries={entries} "
            f"text={raw[0x348:0x3c8].rstrip(bytes([0]))!r}")


def shot(con, n):
    from PIL import Image
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(f"{OUT}_{n:03d}.png")


def play(F):
    from melonds_mcp.native import Console

    work = tempfile.mkdtemp(prefix="dyn_host_")
    host = Console(nickname="NamingHost")
    out, last, shots = [], None, 0
    guest = F.cons[0]

    def watch(frames, step):
        nonlocal last, shots
        for n in range(frames // step):
            F.run(step)
            now = state(guest)
            shown = guest.read(NOTICES + 0x3c9, 1)[0] & 1
            if now != last or (shown and n % 3 == 0):
                out.append(f"{guest.frames} {now}")
                last = now
                if shots < 80:
                    shot(guest, shots)
                    out.append(f"  shot {OUT}_{shots:03d}.png")
                    shots += 1

    try:
        save = os.path.join(work, "host.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "host.sav"), save)
        host.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        host.load_state(os.path.join(PLAY, "states", "mp_joined.0.mst"))
        F.cons.append(host)
        F.run(240)
        host.reset()
        F.run(60)
        watch(1440, 20)
        for _ in range(6):
            F.hold(0, ["A"], 4)
            watch(200, 20)
    finally:
        if host in F.cons:
            F.cons.remove(host)
        host.close()
        shutil.rmtree(work, ignore_errors=True)
        with open(OUT + ".log", "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
