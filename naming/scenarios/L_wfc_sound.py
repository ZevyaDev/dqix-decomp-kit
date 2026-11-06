import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
START = {"save": "saves/dq9ds_kheg_aug30.sav"}


def channel_log(F, name):
    spec = importlib.util.spec_from_file_location("C_sound", os.path.join(HERE, "C_sound.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.channel_log(F, name)


def play(F):
    import dqix_flows
    T = dqix_flows.T
    con = F.cons[0]
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
    with channel_log(F, "L_wfc_sound") as out:
        for _ in range(3):
            out.append(f"{con.frames} press A")
            F.hold(0, ["A"], 3)
            F.run(300)
        out.append(f"{con.frames} press B")
        F.hold(0, ["B"], 3)
        F.run(300)
