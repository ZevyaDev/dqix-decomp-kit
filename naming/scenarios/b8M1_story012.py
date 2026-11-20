START = {"save": "D:/Downloads/dqvc/work/saves/github_playinful_dq9-tools/012 - To Loch Storn.sav"}


def play(F):
    import dqix_flows
    dqix_flows.boot_all(F)
    F.run(300)
