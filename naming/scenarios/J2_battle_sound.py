import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


START = load("battle").START


def play(F):
    sound, battle = load("C_sound"), load("battle")
    with sound.channel_log(F, "J2_battle_sound"):
        battle.play(F)
