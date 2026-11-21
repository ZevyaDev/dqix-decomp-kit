import os
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b9", "K", "conn1")


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"f{con.frames}_{label}.png"))


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
    F.hold(0, ["A"], 3)
    F.run(300)
    snap(F, "step1")
    F.hold(0, ["A"], 3)
    F.run(300)
    snap(F, "conn1")
