START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def tap(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def pick(F):
    tap(F, "Down", 30)
    for _ in range(5):
        tap(F, "Right", 20)
    tap(F, "Down", 30)
    tap(F, "A", 60)
    tap(F, "A", 150)


def play(F):
    F.run(30)
    tap(F, "X", 60)
    tap(F, "Down", 20)
    tap(F, "A", 90)
    tap(F, "A", 120)
    tap(F, "A", 90)
    pick(F)
    tap(F, "B", 60)
    tap(F, "R", 120)
    tap(F, "A", 90)
    pick(F)
    tap(F, "A", 60)
