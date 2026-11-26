START = {"save": "saves/story/036 - Arrival at Gleeba.sav"}


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
