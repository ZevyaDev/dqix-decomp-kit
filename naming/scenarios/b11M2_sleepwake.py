import importlib.util
import os

_spec = importlib.util.spec_from_file_location("b11M2_battleface", os.path.join(os.path.dirname(__file__), "b11M2_battleface.py"))
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

FAINT = W.load("faint")
START = FAINT.START


def play(F):
    W.watch(F, FAINT.play, [0, 1, 2, 3, 0xC0], "sleepwake.log")
