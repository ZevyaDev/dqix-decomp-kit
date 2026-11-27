import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location(
    "b12M5_recruit_done", os.path.join(os.path.dirname(__file__), "b12M5_recruit_done.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

START = R.START
OUT = os.path.join(kitpaths.SP, "names", "b12", "M5", "recruit_priest")


def play(F):
    R.create(F, OUT, 1)
