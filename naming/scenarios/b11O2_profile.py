import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "O2")


def tap(F, log, key, wait, name=""):
    log.append(f"f{F.cons[0].frames} press {key} {name}")
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    log = []
    F.run(30)
    tap(F, log, "X", 40, "open menu")
    tap(F, log, "Right", 15)
    tap(F, log, "Down", 15)
    tap(F, log, "Down", 15)
    tap(F, log, "A", 90, "Misc.")
    for _ in range(4):
        tap(F, log, "Down", 20)
    tap(F, log, "A", 150, "Profile Settings")
    tap(F, log, "A", 90, "Location")
    tap(F, log, "A", 90, "Countries")
    tap(F, log, "B", 60, "back to Location")
    tap(F, log, "B", 60, "back to Profile Settings")
    tap(F, log, "Down", 30)
    tap(F, log, "A", 90, "Birthday")
    tap(F, log, "B", 60, "back to Profile Settings")
    tap(F, log, "Down", 30)
    tap(F, log, "A", 90, "Title")
    tap(F, log, "A", 90, "Occupations")
    tap(F, log, "B", 60, "back to Title")
    tap(F, log, "B", 60, "back to Profile Settings")
    for n in range(3):
        tap(F, log, "B", 60, f"exit {n}")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "b11O2_profile_presses.log"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(log) + "\n")
