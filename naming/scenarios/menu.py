START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    F.run(30)
    for index in range(6):
        F.hold(0, ["X"], 4)
        F.run(40)
        for _ in range(index):
            F.hold(0, ["Down"], 3)
            F.run(15)
        F.hold(0, ["A"], 3)
        F.run(60)
        F.hold(0, ["A"], 3)
        F.run(60)
        for _ in range(5):
            F.hold(0, ["B"], 3)
            F.run(25)
