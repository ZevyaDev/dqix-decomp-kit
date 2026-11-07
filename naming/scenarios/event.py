import struct

START = {"save": "D:/Downloads/dqvc/work/saves/github_playinful_dq9-tools/033 - Tyrantula.sav",
         "state": "states/event.mst"}
SLOT_SET = 0x01FFD348
SLOTS = 0x01FFD364
EVENT_OVERLAY = 1


def slot0(F):
    k = struct.unpack("<I", F.cons[0].read(SLOT_SET, 4))[0]
    return F.cons[0].read(SLOTS + 6 * k, 1)[0]


def play(F):
    F.hold(0, ["A"], 4)
    for _ in range(30):
        if slot0(F) == EVENT_OVERLAY:
            break
        F.run(4)
    else:
        raise RuntimeError("event: talking to Marionette did not load ov001")
    for _ in range(80):
        F.run(56)
        if slot0(F) != EVENT_OVERLAY:
            break
        F.hold(0, ["A"], 4)
    else:
        raise RuntimeError("event: ov001 still loaded after 80 pages")
    F.run(120)
