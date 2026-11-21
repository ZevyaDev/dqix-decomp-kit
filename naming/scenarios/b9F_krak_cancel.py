import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location("b9F_krak_touchno", os.path.join(os.path.dirname(__file__), "b9F_krak_touchno.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

START = T.START
LOG = os.path.join(kitpaths.SP, "names", "b9", "F", "b9F_krak_cancel.log")


def play(F):
    with open(LOG, "w", encoding="utf-8") as log:
        T.to_prompt(F)
        log.write(f"f{F.cons[0].frames} open {T.window_state(F)}\n")
        F.run(30)
        T.K.press(F, "Down", 30)
        log.write(f"f{F.cons[0].frames} after Down {T.window_state(F)}\n")
        T.K.press(F, "B", 120)
        log.write(f"f{F.cons[0].frames} after B {T.window_state(F)}\n")
        F.run(120)
        for _ in range(6):
            T.K.press(F, "B", 60)
