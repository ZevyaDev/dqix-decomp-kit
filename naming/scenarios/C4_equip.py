START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    F.run(30)
    press(F, "X", 40)
    press(F, "Down", 15)
    press(F, "A", 90)
    press(F, "A", 90)
    press(F, "A", 90)
    press(F, "Down", 20)
    press(F, "A", 120)
    press(F, "A", 120)
    press(F, "A", 120)
    for _ in range(4):
        press(F, "B", 40)
