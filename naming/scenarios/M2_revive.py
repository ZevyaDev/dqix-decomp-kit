import struct

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
GAME_STATE = 0x020F33D8
GARREK = 3
OUT = "D:/Downloads/decomp/dqix-sp/names/b7/M2/revive"


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def status(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x130)


def shot(F, name):
    import os
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"{name}.png"))
    s = status(F, GARREK)
    flags = u32(F, s)
    hp = struct.unpack("<H", con.read(s + 4, 2))[0]
    with open(os.path.join(OUT, "revive.log"), "a") as log:
        log.write(f"f{con.frames} {name}: Garrek +0x130 record {s:#x} flags {flags:#x} hp {hp}\n")


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    s = status(F, GARREK)
    F.cons[0].write(s, struct.pack("<I", u32(F, s) | 1))
    F.cons[0].write(s + 4, struct.pack("<H", 0))
    shot(F, "00_dead")
    for _ in range(3):
        press(F, "A", 90)
    F.run(90)
    shot(F, "01_priest_menu")
    for _ in range(2):
        press(F, "Down", 15)
    shot(F, "02_on_resurrection")
    press(F, "A", 90)
    shot(F, "03_on_whom")
    press(F, "Down", 15)
    shot(F, "04_on_garrek")
    for step in range(5, 15):
        press(F, "A", 30)
        F.run(60)
        shot(F, f"{step:02d}_A")
