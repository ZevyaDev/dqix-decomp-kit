START = {"save": "saves/dq9ds_kheg_aug30.sav"}


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
