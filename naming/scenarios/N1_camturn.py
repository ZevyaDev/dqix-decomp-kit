START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    F.run(250)
    F.hold(0, ["R"], 15)
    F.run(250)
    F.hold(0, ["L"], 40)
    F.run(250)
