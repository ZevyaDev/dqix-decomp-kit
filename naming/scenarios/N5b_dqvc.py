import struct

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
SLOT_SET = 0x01FFD348
SLOTS = 0x01FFD364
MENU_CALLBACK_OVERLAY = 4


def slot0(F):
    k = struct.unpack("<I", F.cons[0].read(SLOT_SET, 4))[0]
    return F.cons[0].read(SLOTS + 6 * k, 1)[0]


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    import dqix_flows
    F.run(30)
    if "Sellma" not in F.go_npc(0, dqix_flows.NPC["Sellma"]):
        raise RuntimeError("N5b_dqvc: Sellma did not answer")
    F.run(60)
    for _ in range(4):
        press(F, "A", 90)
    press(F, "Down", 30)
    press(F, "A", 150)
    press(F, "A", 120)
    if slot0(F) != MENU_CALLBACK_OVERLAY:
        raise RuntimeError("N5b_dqvc: DQVC did not load ov004")
    for _ in range(6):
        press(F, "A", 120)
    for _ in range(3):
        press(F, "Down", 40)
    press(F, "A", 120)
    for _ in range(4):
        press(F, "A", 120)
    for _ in range(6):
        press(F, "B", 60)
