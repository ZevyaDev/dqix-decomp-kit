START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    F.run(30)
    F.hold(0, ["X"], 4)
    F.run(120)
    for _ in range(2):
        F.cons[0].touch(30, 18)
        F.run(6)
        F.cons[0].touch()
        F.run(90)
    F.run(120)
    for _ in range(4):
        F.hold(0, ["B"], 3)
        F.run(25)
