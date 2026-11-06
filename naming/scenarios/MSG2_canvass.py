START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    import dqix_flows
    F.run(30)
    F.go_npc(0, dqix_flows.NPC["Erinn"])
    F.run(90)
    dqix_flows.advance(F, 0, 1)
    dqix_flows.menu_pick(F, 0, 1)
    for _ in range(4):
        F.hold(0, ["Down"], 3)
        F.run(20)
        F.hold(0, ["A"], 3)
        F.run(90)
    F.close(0)
    F.run(60)
