import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location("volume", os.path.join(os.path.dirname(__file__), "b9E_volume.py"))
V = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V)

START = V.START
V.OUT = os.path.join(kitpaths.SP, "names", "b11", "M7", "volume")


def play(F):
    V.play(F)
    with open(os.path.join(V.OUT, "volume.log"), "a", encoding="utf-8") as log:
        for i in range(5):
            V.tap(F, log, "B", 60, f"back{i}")
        F.run(60)
        V.tap(F, log, "X", 90, "reopen")
        F.run(60)
        V.shot(F, log, "reopen_end")
