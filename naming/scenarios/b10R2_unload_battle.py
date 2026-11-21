import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/field_battle.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "R2", "unload")
LOG = "battle.log"
BATTLE = 0x02114E04
GAME_STATE = 0x020F33D8
NPC_MANAGER = 0x021075F4


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def half(con, addr):
    return struct.unpack("<H", bytes(con.read(addr, 2)))[0]


def obj(con, index):
    return word(con, GAME_STATE + 8 + 4 * index)


def state(con):
    resources = word(con, GAME_STATE)
    monsters = []
    for index in range(0x70, 0xA0):
        o = obj(con, index)
        if o and half(con, o) & 0x20:
            monsters.append(f"{index:x}:{o:08x}/model={word(con, o + 8):08x}")
    kinds = sum(1 for index in range(7, 0x13) if obj(con, index))
    npcs = sum(1 for i in range(32) if word(con, NPC_MANAGER + 0xC + 4 * i))
    extra = ",".join(f"{obj(con, index):x}" for index in range(0xC9, 0xCF))
    allocs = ""
    if resources:
        allocs = " ".join(f"res+{off:x}={word(con, resources + off):08x}" for off in (0x1244, 0x113C, 0x11C0))
    return (f"fieldMonsters=[{' '.join(monsters)}] slots7-12={kinds} npcEntries={npcs} "
            f"slotsC9-CE={extra} {allocs}")


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"battle_f{con.frames}_{label}.png"))


def play(F):
    con = F.cons[0]
    out = []
    last = None

    def log():
        nonlocal last
        now = state(con)
        if now != last:
            out.append(f"{con.frames} battle={bytes(con.read(BATTLE, 1))[0]} {now}")
            last = now

    try:
        log()
        snap(F, "start")
        for _ in range(120):
            if bytes(con.read(BATTLE, 1))[0]:
                break
            F.hold(0, ["Left"], 1)
            log()
        for _ in range(240):
            F.run(1)
            log()
        snap(F, "end")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, LOG), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
