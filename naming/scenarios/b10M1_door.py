import os

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "M1", "door")


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def play(F):
    import dqix_flows
    os.makedirs(OUT, exist_ok=True)
    dqix_flows.boot_all(F)
    dqix_flows.leave_church(F, 0)
    F.walk(0, ["Left"], lambda p: p[0] < 11.7)
    F.walk(0, ["Down"], lambda p: p[1] > 12.0)
    F.walk(0, ["Left"], lambda p: p[0] < 2.2)
    F.walk(0, ["Down"], lambda p: p[1] > 32.0)
    F.move_to(0, tz=32.5)
    F.move_to(0, tx=-7.6)
    F.align(0, tx=-7.6)
    shot(F, "at_door")
    for step in range(20):
        F.hold(0, ["Up"], 4)
        shot(F, f"up{step:02d}")
    F.run(90)
    shot(F, "inside")
