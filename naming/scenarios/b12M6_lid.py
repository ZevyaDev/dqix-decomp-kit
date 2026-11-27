START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    F.run(60)
    F.cons[0].set_lid(True)
    F.run(300)
    F.cons[0].set_lid(False)
    F.run(300)
