START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    F.run(60)
    F.hold(0, ["B"], 10)
    F.hold(0, ["B", "Right"], 4)
    F.run(400)
