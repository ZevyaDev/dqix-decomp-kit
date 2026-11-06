START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def tap(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    F.run(30)
    tap(F, "X", 60)
    tap(F, "Down", 20)
    tap(F, "A", 90)
    tap(F, "A", 300)
    for _ in range(3):
        tap(F, "Y", 300)
