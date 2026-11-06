import os
import shutil
import tempfile

import kitpaths

START = {"save": "states/guest.sav", "state": "states/mp_joined.1.mst"}
PLAY = os.environ.get("DQIX_PLAY") or os.path.join(os.path.dirname(kitpaths.KIT), "dqix-play")
QUEUES = 0x02100044 + 0x1500
OWN = 0x020fefec + 0x7c0
RECEIVED = 0x020fefec + 0xbc0
BLOCK = 0x74


def slots(block):
    out = []
    for i in range(5):
        slot = block[0x10 + i * 0x14:0x10 + (i + 1) * 0x14]
        if slot[0] != 0xff:
            out.append(f"s{i}:{slot.hex()}")
    return ",".join(out) or "-"


def counts(queues):
    words = [int.from_bytes(queues[i:i + 4], "little") for i in range(0, 0x24, 4)]
    return f"free={words[2]:#x} out={words[5]} in={words[8]}"


def state(con):
    received = con.read(RECEIVED, BLOCK * 4)
    return (counts(con.read(QUEUES, 0x24)), slots(con.read(OWN, BLOCK)),
            " ".join(f"b{i}[{slots(received[i * BLOCK:(i + 1) * BLOCK])}]" for i in range(4)))


def play(F):
    from melonds_mcp.native import Console

    work = tempfile.mkdtemp(prefix="dyn_host_")
    host = Console(nickname="NamingHost")
    out, last = [], {}

    def step(frames, i=None, keys=()):
        for j, con in enumerate(F.cons):
            con.set_keys(list(keys) if j == i else [])
        for _ in range(frames):
            F.run(1)
            for name, con in (("guest", F.cons[0]), ("host", F.cons[1])):
                now = state(con)
                if now != last.get(name):
                    out.append(f"{con.frames} {name} {now[0]} own={now[1]} received={now[2]}")
                    last[name] = now
        for con in F.cons:
            con.set_keys([])

    try:
        save = os.path.join(work, "host.sav")
        shutil.copyfile(os.path.join(PLAY, "states", "host.sav"), save)
        host.load_rom(os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds"), save=save)
        host.load_state(os.path.join(PLAY, "states", "mp_joined.0.mst"))
        F.cons.append(host)
        step(30)
        step(60, 1, ["Left"])
        step(60, 0, ["Down"])
        out.append(f"{F.cons[0].frames} guest press X")
        step(4, 0, ["X"])
        step(90)
        out.append(f"{F.cons[0].frames} guest press B")
        step(4, 0, ["B"])
        step(60)
        out.append(f"{F.cons[0].frames} host press X")
        step(4, 1, ["X"])
        step(90)
        out.append(f"{F.cons[0].frames} host press B")
        step(4, 1, ["B"])
        step(60)
    finally:
        folder = os.path.join(kitpaths.SP, "names", "dyn", "probe", "L_mppair_queue")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "queues.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
        if host in F.cons:
            F.cons.remove(host)
        host.close()
        shutil.rmtree(work, ignore_errors=True)
