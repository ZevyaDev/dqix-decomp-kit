import os

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "M8", "shots")


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"wfc_f{con.frames}_{label}.png"))


def tap(F, x, y):
    F.cons[0].touch(x, y)
    F.run(6)
    F.cons[0].touch()


def play(F):
    import dqix_flows
    T = dqix_flows.T
    F.run(T["power_on_to_title"])
    F.hold(0, ["Start"], 4)
    F.run(T["title_start_to_log_list"])
    F.hold(0, ["A"], 4)
    F.run(T["title_start_to_log_list"])
    for _ in range(2):
        F.hold(0, ["Down"], 3)
        F.run(T["menu_cursor_step"])
    F.hold(0, ["A"], 3)
    F.run(900)
    for _ in range(2):
        F.hold(0, ["A"], 3)
        F.run(300)
    snap(F, "settings")
    tap(F, 190, 36)
    for i in range(6):
        F.run(180)
        snap(F, f"test{i}")
