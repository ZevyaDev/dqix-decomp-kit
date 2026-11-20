import os
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/field_battle.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b8", "M4", "spot")
BATTLE = 0x02114E04
ROUTE = [("Right", 120), ("Up", 360), ("Left", 180)]


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))
    with open(os.path.join(OUT, "pos.log"), "a") as fh:
        fh.write(f"{con.frames} {tag} {tuple(round(v, 2) for v in F.pos3(0))} hero {hero(F)} "
                 f"entrance {xyz(F, GROTTO + 0x10)}\n")


HERO = 0x022BBBDC
GROTTO = 0x020F97BC


def xyz(F, addr):
    import struct
    return tuple(round(v / 4096, 2) for v in struct.unpack("<3i", F.cons[0].read(addr, 12)))


def hero(F):
    return xyz(F, HERO + 0x44)


def in_battle(F):
    return F.cons[0].read(BATTLE, 1)[0] != 0


def clear_battle(F):
    shot(F, "battle")
    for _ in range(200):
        if not in_battle(F):
            break
        F.hold(0, ["A"], 4)
        F.run(26)
    if in_battle(F):
        raise RuntimeError("b8M4_spot: battle did not end")
    F.run(120)
    shot(F, "battle_over")


def walk_hero(F, axis, target, step):
    keys = (("Left", "Right"), ("Up", "Down"))[axis]
    for _ in range(400):
        if in_battle(F):
            clear_battle(F)
        here = hero(F)[2 * axis]
        if abs(here - target) <= 0.15:
            return
        F.hold(0, [keys[here < target]], step)
        F.run(2)
    raise RuntimeError(f"b8M4_spot: hero stuck at {hero(F)}")


def go(F, keys, frames):
    for _ in range(frames // 10):
        if in_battle(F):
            clear_battle(F)
        F.hold(0, [keys], 10)


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def set_out_with_zoma_map(F):
    for key, wait in [("X", 40), ("A", 60), ("Down", 15), ("Down", 15), ("A", 200), ("Down", 15),
                      ("Down", 15), ("Down", 15), ("A", 90), ("A", 120)]:
        press(F, key, wait)
    shot(F, "map_chosen")
    for key, wait in [("A", 90), ("B", 60), ("B", 60), ("B", 60), ("B", 60)]:
        press(F, key, wait)


def play(F):
    F.run(30)
    set_out_with_zoma_map(F)
    shot(F, "map_active")
    for keys, frames in ROUTE:
        go(F, keys, frames)
        shot(F, keys)
    walk_hero(F, 1, -27.3, 3)
    shot(F, "ridge")
    walk_hero(F, 0, -67.2, 3)
    walk_hero(F, 1, -27.3, 1)
    walk_hero(F, 0, -67.2, 1)
    F.run(60)
    shot(F, "spot")
    F.hold(0, ["A"], 4)
    F.run(200)
    shot(F, "found")
    F.hold(0, ["A"], 4)
    F.run(150)
    shot(F, "end")
