START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    F.run(30)
    press(F, "X", 60)
    press(F, "Right", 20)
    press(F, "A", 90)
    press(F, "A", 120)
    press(F, "A", 120)
    press(F, "Right", 60)
    press(F, "R", 60)
    for _ in range(4):
        press(F, "B", 40)
    press(F, "X", 60)
    press(F, "Down", 20)
    press(F, "Down", 20)
    press(F, "A", 90)
    press(F, "A", 120)
    for _ in range(4):
        press(F, "Right", 60)
    for _ in range(3):
        press(F, "R", 60)
