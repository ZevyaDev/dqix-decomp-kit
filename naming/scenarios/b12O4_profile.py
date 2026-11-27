START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
ROUTE = [("X", 40), ("Right", 15), ("Down", 15), ("Down", 15), ("A", 90),
         ("Down", 20), ("Down", 20), ("Down", 20), ("Down", 20), ("A", 150),
         ("A", 90), ("A", 90), ("B", 60), ("B", 60),
         ("Down", 30), ("A", 90), ("B", 60),
         ("Down", 30), ("A", 90), ("A", 90), ("B", 60), ("B", 60),
         ("B", 60), ("B", 60), ("B", 60)]


def play(F):
    F.run(30)
    for key, wait in ROUTE:
        F.hold(0, [key], 3)
        F.run(wait)
