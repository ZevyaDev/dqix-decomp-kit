import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "M4", "queuereset")
QUEUE = 0x02100044
WIRELESS = 0x020FEFEC


def state(F):
    c = F.cons[0]
    free, outgoing, incoming = (struct.unpack("<i", c.read(QUEUE + off, 4))[0] for off in (0x1508, 0x1514, 0x1520))
    free_head, = struct.unpack("<I", c.read(QUEUE + 0x1500, 4))
    mask = c.read(QUEUE + 0x1524, 0x20).hex()
    own = WIRELESS + 0x7C0
    kinds = [c.read(own + 0x10 + i * 0x14, 1)[0] for i in range(5)]
    return (f"free {free:#x} head {free_head:#x} outgoing {outgoing} incoming {incoming} "
            f"mask {mask} own slot kinds {[hex(k) for k in kinds]}")


def play(F):
    import dqix_flows
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "queuereset.log"), "w", encoding="utf-8") as log:
        last = None
        for _ in range(40):
            now = state(F)
            if now != last:
                log.write(f"f{F.cons[0].frames} {now}\n")
                last = now
            F.run(1)
        dqix_flows.boot_all(F)
        log.write(f"f{F.cons[0].frames} after boot {state(F)}\n")
        dqix_flows.leave_church(F, 0)
        log.write(f"f{F.cons[0].frames} after leaving the church {state(F)}\n")
