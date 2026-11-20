START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/field_battle.mst"}


def play(F):
    F.run(30)
    F.hold(0, ["Y"], 4)
    F.run(300)
    F.hold(0, ["B"], 4)
    F.run(300)
    F.hold(0, ["X"], 4)
    F.run(120)
    F.hold(0, ["B"], 4)
    F.run(300)
