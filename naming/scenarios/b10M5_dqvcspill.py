import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location("b9D_dqvcspill", os.path.join(os.path.dirname(__file__), "b9D_dqvcspill.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

START = S.START
S.OUT = os.path.join(kitpaths.SP, "names", "b10", "M5", "dqvcspill")


def play(F):
    S.play(F)
