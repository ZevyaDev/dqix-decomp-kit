import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/mp_joined.0.mst"}
QUEUES = 0x02100044 + 0x1500
SLOTS = 0x020fefec + 0x7c0


def play(F):
    con = F.cons[0]
    out, last = [], None
    for _ in range(300):
        F.run(1)
        queues = con.read(QUEUES, 0x24)
        slots = con.read(SLOTS, 0x74)
        now = (queues, slots)
        if now != last:
            out.append(f"{con.frames} queues={queues.hex()} slots={slots.hex()}")
            last = now
    folder = os.path.join(kitpaths.SP, "names", "dyn", "probe", "C_mphost_queue")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "queues.log"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
