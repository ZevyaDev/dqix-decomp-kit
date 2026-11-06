START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    F.run(30)
    F.move_to(0, tz=9.12)
    F.move_to(0, tx=1.74)
    F.align(0, tx=1.74)
    F.move_to(0, tz=7.92)
    F.hold(0, ["Up"], 2)
    F.run(4)
    for _ in range(5):
        press(F, "A", 90)
    for _ in range(4):
        press(F, "Down", 20)
    press(F, "A", 90)
    press(F, "A", 90)
    press(F, "A", 90)
    F.run(240)
    for _ in range(6):
        press(F, "A", 90)
    for _ in range(10):
        press(F, "B", 60)
    F.run(120)
