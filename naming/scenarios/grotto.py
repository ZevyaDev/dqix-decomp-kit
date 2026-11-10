import struct

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/grotto.mst"}
ZONE = 0x020FB3F0
BATTLE = 0x02114E04
IN_BATTLE = 0x22
FIELD = 20002
LEGACY = (41101, 41505)


def zone(F):
    return struct.unpack("<H", F.cons[0].read(ZONE, 2))[0]


def battle_scene(F):
    return F.cons[0].read(BATTLE + 1, 1)[0] == IN_BATTLE


def until(F, what, cond, limit, step=10):
    for _ in range(0, limit, step):
        if cond():
            return
        F.run(step)
    raise RuntimeError(f"grotto: {what} not seen after {limit} frames (zone {zone(F)})")


def play(F):
    if zone(F) != FIELD:
        raise RuntimeError(f"grotto: start zone {zone(F)}, not Western Stornway")
    F.run(60)
    F.hold(0, ["Up"], 40)
    F.hold(0, ["A"], 4)
    until(F, "Zoma's grotto", lambda: LEGACY[0] <= zone(F) <= LEGACY[1], 400)
    F.run(300)
    last = None
    for _ in range(80):
        F.hold(0, ["Up"], 6)
        z = F.pos(0)[1]
        if last is not None and abs(z - last) < 0.02:
            break
        last = z
    for _ in range(12):
        if battle_scene(F):
            break
        F.hold(0, ["A"], 4)
        F.run(86)
    until(F, "the Zoma battle", lambda: battle_scene(F), 600)
    F.run(600)
