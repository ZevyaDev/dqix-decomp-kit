import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location("b9E_squelch", os.path.join(os.path.dirname(__file__), "b9E_squelch.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

START = S.START
OUT = os.path.join(kitpaths.SP, "names", "b9", "E", "squelch_kheg")


def play(F):
    S.run(F, OUT, 0)
