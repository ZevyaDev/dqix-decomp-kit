START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    F.run(30)
    press(F, "X", 60)
    press(F, "Right", 20)
    press(F, "Down", 20)
    press(F, "A", 200)
    press(F, "A", 300)
    press(F, "A", 200)
    press(F, "A", 200)
    press(F, "A", 200)
    press(F, "Right", 120)
    for _ in range(4):
        press(F, "B", 120)
    press(F, "Down", 30)
    press(F, "Down", 30)
    press(F, "A", 300)
    press(F, "A", 200)
    press(F, "A", 200)
    for _ in range(5):
        press(F, "B", 90)
