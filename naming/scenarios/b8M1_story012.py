START = {"save": "saves/story/012 - To Loch Storn.sav"}


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
