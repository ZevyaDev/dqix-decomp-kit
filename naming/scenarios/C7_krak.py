START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
POT = (1.6, 7.92)


def tap(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    F.run(30)
    x, z = POT
    F.move_to(0, tz=z + 1.2)
    F.align(0, tx=x)
    F.move_to(0, tz=z)
    F.align(0, tx=x)
    F.talk(0, "Up", close=False)
    F.run(60)
    for _ in range(4):
        tap(F, "A", 90)
    tap(F, "Down", 30)
    tap(F, "A", 90)
    tap(F, "A", 300)
    for _ in range(6):
        tap(F, "A", 120)
