START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    F.run(30)
    F.hold(0, ["X"], 4)
    F.run(250)
    for key in ["Down", "Right", "Down", "Left", "Down", "Right"]:
        F.hold(0, [key], 3)
        F.run(250)
    for _ in range(3):
        F.hold(0, ["B"], 3)
        F.run(40)
