START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def play(F):
    import dqix_flows
    F.run(30)
    F.go_npc(0, dqix_flows.NPC["Erinn"])
    F.run(90)
    for _ in range(10):
        dqix_flows.advance(F, 0, 1, 90)
    F.run(300)
