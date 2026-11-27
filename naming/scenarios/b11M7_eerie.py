import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location("barrier", os.path.join(os.path.dirname(__file__), "b11M7_barrier.py"))
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

START = M.START
M.POKES = ()
M.LAST_ROUND = 14
M.WATCH = ((M.T.LAURA, 0x10, "eerie"),)
M.OUT = os.path.join(kitpaths.SP, "names", "b11", "M7", "eerie")
M.LOG = os.path.join(M.OUT, "eerie_rounds.log")


def play(F):
    M.play(F)
