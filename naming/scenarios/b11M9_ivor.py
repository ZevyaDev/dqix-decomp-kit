START = {"save": "saves/story/006 - Ivor Accompanied.sav"}


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
    dqix_flows.leave_church(F, 0)
    F.run(300)
