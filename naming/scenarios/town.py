START = {"save": "saves/dq9ds_kheg_aug30.sav"}


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    dqix_flows.leave_church(F, 0)
    dqix_flows.church_to_inn(F, 0)
