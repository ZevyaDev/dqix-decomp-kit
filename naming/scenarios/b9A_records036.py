import importlib.util
import os

_spec = importlib.util.spec_from_file_location("b9A_records011", os.path.join(os.path.dirname(__file__), "b9A_records011.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

START = {"save": "D:/Downloads/dqvc/work/saves/github_playinful_dq9-tools/036 - Arrival at Gleeba.sav"}


def play(F):
    R.records(F, "s036")
