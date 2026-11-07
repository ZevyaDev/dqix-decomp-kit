import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load("C5_krakpot")
START = BASE.START


def play(F):
    load("M5_town").watch(F, "M5_krak.log", BASE.play, only={"func_020e526c", "func_020e2d24", "func_020e2cc4"})
