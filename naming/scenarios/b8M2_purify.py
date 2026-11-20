import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
GAME_STATE = 0x020F33D8
NATALIA, GARREK = 2, 3
POISONED, CURSED = 2, 4
OUT = os.path.join(kitpaths.SP, "names", "b8", "M2", "purify")


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
    with open(os.path.join(OUT, "purify.log"), "a") as log:
        for who, index in (("Natalia", NATALIA), ("Garrek", GARREK)):
            s = status(F, index)
            log.write(f"f{con.frames} {name}: {who} +0x130 record {s:#x} flags {u32(F, s):#x}\n")


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def mark(F, index, bits):
    s = status(F, index)
    F.cons[0].write(s, struct.pack("<I", u32(F, s) | bits))


def serve(F, label, service_downs, member_downs, steps):
    for _ in range(service_downs):
        press(F, "Down", 15)
    press(F, "A", 90)
    for _ in range(member_downs):
        press(F, "Down", 15)
    shot(F, f"{label}_target")
    for step in range(steps):
        press(F, "A", 30)
        F.run(60)
        shot(F, f"{label}_{step:02d}")


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    mark(F, NATALIA, POISONED)
    mark(F, GARREK, CURSED)
    shot(F, "00_marked")
    for _ in range(3):
        press(F, "A", 90)
    F.run(90)
    shot(F, "01_priest_menu")
    serve(F, "purify", 3, 2, 9)
    shot(F, "02_after_purify")
    serve(F, "benedict", 1, 1, 10)
    shot(F, "03_after_benedict")
