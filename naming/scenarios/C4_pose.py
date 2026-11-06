START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    F.run(60)
    F.hold(0, ["B"], 10)
    F.hold(0, ["B", "Up"], 4)
    F.hold(0, ["B"], 10)
    F.run(240)
    F.hold(0, ["B"], 10)
    F.hold(0, ["B", "Down"], 4)
    F.hold(0, ["B"], 10)
    F.run(480)
