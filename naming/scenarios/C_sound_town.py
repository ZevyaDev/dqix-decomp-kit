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
    sound, town = load("C_sound"), load("town")
    with sound.channel_log(F, "C_sound_town"):
        town.play(F)
