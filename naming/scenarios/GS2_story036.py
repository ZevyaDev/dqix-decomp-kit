START = {"save": "D:/Downloads/dqvc/work/saves/github_playinful_dq9-tools/036 - Arrival at Gleeba.sav"}


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
