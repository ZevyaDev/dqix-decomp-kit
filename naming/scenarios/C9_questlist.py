START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    F.run(30)
    press(F, "X", 40)
    press(F, "Right", 15)
    press(F, "Down", 15)
    press(F, "A", 90)
    for index in range(5):
        for _ in range(index):
            press(F, "Down", 15)
        press(F, "A", 120)
        press(F, "A", 90)
        for _ in range(2):
            press(F, "B", 40)
    for _ in range(5):
        press(F, "Down", 15)
    press(F, "A", 600)
    press(F, "Right", 200)
    press(F, "Right", 200)
    press(F, "Down", 100)
    press(F, "A", 300)
