START = {"save": "saves/dq9ds_kheg_aug30.sav"}


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
    F.cons[0].set_lid(True)
    F.run(30)
    F.hold(0, ["A"], 3)
    F.run(60)
    F.cons[0].set_lid(False)
    F.run(120)
    F.hold(0, ["A"], 3)
    F.run(300)
