START = {"save": "saves/dq9ds_kheg_aug30.sav"}


def tap(F, x, y, frames):
    F.cons[0].touch(x, y)
    F.run(6)
    F.cons[0].touch()
    F.run(frames)


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
    tap(F, 128, 63, 300)
    tap(F, 65, 130, 2400)
    F.hold(0, ["A"], 3)
    F.run(300)
