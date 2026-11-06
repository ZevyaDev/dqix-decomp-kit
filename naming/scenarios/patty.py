START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    import dqix_flows
    F.run(30)
    dqix_flows.patty_drop_off(F, 0)
