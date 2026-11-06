START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    F.run(30)
    F.hold(0, ["X"], 4)
    F.run(40)
    F.hold(0, ["Right"], 3)
    F.run(15)
    F.hold(0, ["Down"], 3)
    F.run(15)
    F.hold(0, ["A"], 3)
    F.run(90)
    for index in range(6):
        for _ in range(index):
            F.hold(0, ["Down"], 3)
            F.run(15)
        F.hold(0, ["A"], 3)
        F.run(120)
        F.hold(0, ["A"], 3)
        F.run(90)
        for _ in range(2):
            F.hold(0, ["B"], 3)
            F.run(40)
