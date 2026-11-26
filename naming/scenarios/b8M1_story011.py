START = {"save": "saves/story/011 - Arrival in Stornway.sav"}


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
