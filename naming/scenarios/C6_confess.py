import importlib.util
import os

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def play(F):
    import dqix_flows
    T = dqix_flows.T
    sound = load("C_sound")
    with sound.channel_log(F, "C6_confess"):
        dqix_flows.boot_all(F)
        dqix_flows.advance(F, 0, 2)
        dqix_flows.menu_pick(F, 0, 0)
        dqix_flows.advance(F, 0, 2, 150)
        dqix_flows.advance(F, 0, 1, T["adventure_log_save"] + 200)
        dqix_flows.advance(F, 0, 4, 150)
        F.run(300)
