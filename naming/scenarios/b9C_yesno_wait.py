START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

CHOICE_LIST = 0x02115384


def is_choice_list_open(F):
    data = F.cons[0].read(CHOICE_LIST, 0x240)
    frame_state = int.from_bytes(data[0xbc:0xc0], "little")
    return data[0x233] == 1 and frame_state == 2


def play(F):
    import dqix_flows
    F.run(30)
    F.go_npc(0, dqix_flows.NPC["Erinn"])
    F.run(90)
    dqix_flows.advance(F, 0, 1)
    dqix_flows.menu_pick(F, 0, 1)
    F.hold(0, ["Down"], 3)
    F.run(20)
    F.hold(0, ["A"], 3)
    for _ in range(80):
        if is_choice_list_open(F):
            break
        F.run(5)
    F.run(240)
    F.hold(0, ["Down"], 3)
    F.run(200)
    F.hold(0, ["Up"], 3)
    F.run(200)
    F.hold(0, ["B"], 3)
    F.run(150)
    for _ in range(4):
        F.hold(0, ["A"], 3)
        F.run(60)
    F.close(0)
    F.run(60)
