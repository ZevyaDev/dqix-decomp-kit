import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "R2", "unload")
GAME_STATE = 0x020F33D8
NPC_MANAGER = 0x021075F4


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def obj(con, index):
    return word(con, GAME_STATE + 8 + 4 * index)


def state(con):
    resources = word(con, GAME_STATE)
    kinds = sum(1 for index in range(7, 0x13) if obj(con, index))
    npcs = sum(1 for i in range(32) if word(con, NPC_MANAGER + 0xC + 4 * i))
    extra = ",".join(f"{obj(con, index):x}" for index in range(0xC9, 0xCF))
    allocs = ""
    if resources:
        allocs = " ".join(f"res+{off:x}={word(con, resources + off):08x}" for off in (0x1244, 0x113C, 0x11C0))
    return f"slots7-12={kinds} npcEntries={npcs} slotsC9-CE={extra} {allocs}"


def play(F):
    import dqix_flows
    con = F.cons[0]
    out = []
    last = [None]
    original = F.run

    def run(frames):
        for _ in range(frames):
            original(1)
            now = state(con)
            if now != last[0]:
                out.append(f"{con.frames} {now}")
                last[0] = now

    F.run = run
    try:
        dqix_flows.boot_all(F)
        dqix_flows.leave_church(F, 0)
        dqix_flows.church_to_inn(F, 0)
    finally:
        F.run = original
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "town.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
