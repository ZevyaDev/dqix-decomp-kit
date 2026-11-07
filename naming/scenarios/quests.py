import struct

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
SLOT_SET = 0x01FFD348
SLOTS = 0x01FFD364
MENU_CALLBACK_OVERLAY = 4
QUEST_MENU = 0x0217101C


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def slot0(F):
    return F.cons[0].read(SLOTS + 6 * u32(F, SLOT_SET), 1)[0]


def quest_counts(F):
    if slot0(F) != MENU_CALLBACK_OVERLAY:
        return None
    menu = u32(F, QUEST_MENU)
    if not 0x02000000 <= menu < 0x02400000:
        return None
    return struct.unpack("<4h", F.cons[0].read(menu + 0x48, 8))


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def open_list(F, extra):
    if extra:
        press(F, "Down", 30)
    press(F, "A", 150)
    counts = quest_counts(F)
    if counts is None or counts[2] <= 0 or counts[2] != counts[1 if extra else 0]:
        raise RuntimeError(f"quests: {'extra' if extra else 'normal'} quest list did not open ({counts})")
    for _ in range(12):
        press(F, "Down", 40)
    press(F, "B", 60)


def play(F):
    F.run(30)
    press(F, "X", 60)
    press(F, "Right", 20)
    press(F, "Down", 20)
    press(F, "A", 200)
    for _ in range(5):
        press(F, "Down", 30)
    press(F, "A", 200)
    if quest_counts(F) is None:
        raise RuntimeError("quests: Battle Records > Quest List did not open")
    open_list(F, extra=False)
    open_list(F, extra=True)
    for _ in range(4):
        press(F, "B", 60)
    if quest_counts(F) is not None:
        raise RuntimeError("quests: quest list still open")
