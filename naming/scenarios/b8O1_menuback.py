START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    F.run(30)
    press(F, "X", 60)
    press(F, "A", 90)
    press(F, "A", 90)
    press(F, "A", 150)
    press(F, "B", 200)
    press(F, "B", 200)
    press(F, "B", 200)
    press(F, "B", 200)
