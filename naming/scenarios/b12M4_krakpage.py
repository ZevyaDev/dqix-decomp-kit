import importlib.util
import os

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fresh(path):
    run, n = path, 1
    while os.path.exists(run):
        n += 1
        run = f"{path}.r{n}"
    return run


BASE = load("b10M4_krakpage")
START = BASE.START


def play(F):
    BASE.OUT = fresh(os.path.join(kitpaths.SP, "names", "b12", "M4", "krakpage"))
    BASE.play(F)
