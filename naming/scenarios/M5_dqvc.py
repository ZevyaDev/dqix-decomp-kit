import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load("N5b_dqvc")
START = BASE.START


def play(F):
    load("M5_town").watch(F, "M5_dqvc.log", BASE.play, only={"func_020cf0fc"})
