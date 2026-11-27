import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location("barrier", os.path.join(os.path.dirname(__file__), "b11M7_barrier.py"))
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

START = M.START
M.POKES = ((M.T.LAURA, 0x4, 0x6D),)
M.WATCH = ((M.T.LAURA, 0x4, "ice"),)
M.OUT = os.path.join(kitpaths.SP, "names", "b11", "M7", "icebarrier")
M.LOG = os.path.join(M.OUT, "icebarrier_rounds.log")


def play(F):
    M.play(F)
