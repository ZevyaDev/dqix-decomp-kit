import re

START = {"save": "saves/dq9ds_kheg_aug30.sav", "state": "states/field_battle.mst"}
BATTLE = 0x02114E04
PHASE = 0x02114E06
WON = 6
HAND = [re.compile(re.escape(bgr)) for bgr in (b"\x49\xf3\xfb", b"\x28\xcb\xfb", b"\x08\xba\xfb")]
BOTTOM = 256 * 192 * 4
ATTACK_TURNS = 4


def byte(F, addr):
    return F.cons[0].read(addr, 1)[0]


def hand(F):
    raw = bytes(F.cons[0].screen())[BOTTOM:]
    pts = [m.start() // 4 for p in HAND for m in p.finditer(raw) if m.start() % 4 == 0]
    if len(pts) < 5:
        return None
    return sum(i % 256 for i in pts) / len(pts), 192 + sum(i // 256 for i in pts) / len(pts)


def moved(a, b):
    return a is None or b is None or abs(a[0] - b[0]) >= 10 or abs(a[1] - b[1]) >= 2


def wait(F, what, cond, limit, step=4):
    for _ in range(0, limit, step):
        if cond():
            return
        F.run(step)
    if not cond():
        raise RuntimeError(f"battle: no {what} after {limit} frames")


def press(F, key):
    F.hold(0, [key], 3)


def move(F, key, rows=1):
    for _ in range(rows):
        before = hand(F)
        press(F, key)
        wait(F, f"cursor move on {key}", lambda: moved(before, hand(F)), 30, 2)
        F.run(4)


def choose(F, *moves, last=False):
    wait(F, "menu", lambda: hand(F) is not None, 900)
    for key, rows in moves:
        if key == "page":
            press(F, "Right")
            F.run(15)
        else:
            move(F, key, rows)
    before = hand(F)
    press(F, "A")
    wait(F, "menu change", lambda: moved(before, hand(F)), 60, 2)
    if not last:
        wait(F, "next menu", lambda: hand(F) is not None, 120, 2)


def finished(F):
    return byte(F, BATTLE) == 0 or byte(F, PHASE) == WON


def round_over(F):
    return finished(F) or hand(F) is not None


def attack_turn(F):
    while True:
        choose(F, last=True)
        for _ in range(20):
            if hand(F) is not None:
                break
            F.run(4)
        else:
            return


def play(F):
    for _ in range(120):
        if byte(F, BATTLE):
            break
        F.hold(0, ["Left"], 4)
    wait(F, "battle", lambda: byte(F, BATTLE) != 0, 300)

    choose(F)
    choose(F, ("Right", 1), ("Down", 1))
    choose(F, ("page", 0), ("Down", 2))
    choose(F, ("Down", 3))
    choose(F, ("Down", 2))
    choose(F, ("Down", 2))
    choose(F, ("Down", 1))
    choose(F, ("Down", 3))
    choose(F, last=True)

    for turn in range(ATTACK_TURNS + 1):
        wait(F, "end of round", lambda: round_over(F), 3000)
        if finished(F):
            break
        if turn < ATTACK_TURNS:
            attack_turn(F)
        else:
            choose(F, ("Down", 2), last=True)

    for _ in range(40):
        if byte(F, BATTLE) == 0:
            break
        if byte(F, PHASE) == WON:
            press(F, "A")
        F.run(30)
    wait(F, "field", lambda: byte(F, BATTLE) == 0, 600)
    F.run(120)
