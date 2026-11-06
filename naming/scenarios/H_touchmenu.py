START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    F.run(30)
    F.hold(0, ["X"], 4)
    F.run(60)
    F.hold(0, ["Down"], 3)
    F.run(60)
    F.cons[0].touch(30, 37)
    F.run(40)
    F.cons[0].touch()
    F.run(130)
    for _ in range(4):
        F.hold(0, ["B"], 3)
        F.run(25)
