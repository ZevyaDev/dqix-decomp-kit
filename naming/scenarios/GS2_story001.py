START = {"save": "saves/story/001 - Observatory.sav"}


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
