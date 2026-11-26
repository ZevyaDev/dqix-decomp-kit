import json
from pathlib import Path

KNOWLEDGE = json.loads((Path(__file__).parent / "dqix_usa.json").read_text())
NPC = KNOWLEDGE["maps"]["questers_rest_1f"]["npcs"]
T = KNOWLEDGE["timings_frames"]


def boot_all(F):
    F.run(T["power_on_to_title"])
    for c in F.cons:
        c.set_keys(["Start"])
    F.run(4)
    for c in F.cons:
        c.set_keys([])
    F.run(T["title_start_to_log_list"])
    for wait in (T["title_start_to_log_list"], T["log_select_to_field"]):
        for c in F.cons:
            c.set_keys(["A"])
        F.run(4)
        for c in F.cons:
            c.set_keys([])
        F.run(wait)


def leave_church(F, i):
    F.close(i)
    F.hold(i, ["Down"], T["church_exit_hold_down"])
    F.run(T["room_transition"])
    return F.pos(i)


def church_to_inn(F, i):
    F.walk(i, ["Left"], lambda p: p[0] < 11.7)
    F.walk(i, ["Down"], lambda p: p[1] > 12.0)
    F.walk(i, ["Left"], lambda p: p[0] < 2.2)
    F.walk(i, ["Down"], lambda p: p[1] > 32.0)
    F.move_to(i, tz=32.5)
    F.move_to(i, tx=-7.6)
    F.align(i, tx=-7.6)
    F.walk(i, ["Up"], max_steps=10)
    F.run(T["room_transition"])
    return F.pos(i)


def menu_pick(F, i, index):
    for _ in range(index):
        F.hold(i, ["Down"], 3)
        F.run(T["menu_cursor_step"])
    F.hold(i, ["A"], 3)
    F.run(T["text_page"])


def advance(F, i, pages=1, wait=None):
    for _ in range(pages):
        F.hold(i, ["A"], 3)
        F.run(wait or T["text_page"])


def patty_drop_off(F, i, member_index=0):
    F.go_npc(i, NPC["Patty"])
    advance(F, i, 2)
    menu_pick(F, i, 1)
    menu_pick(F, i, member_index)
    advance(F, i, 1)
    return F.close(i)


def pavo_open(F, i):
    names = F.go_npc(i, NPC["Pavo"])
    if "Pavo" not in names:
        return names
    advance(F, i, 2)
    return names


def host_invite(F, i):
    if "Pavo" not in pavo_open(F, i):
        return False
    menu_pick(F, i, 1)
    advance(F, i, 1, 150)
    advance(F, i, 1, T["adventure_log_save"] + 200)
    advance(F, i, 3, 150)
    F.close(i)
    return True


def guest_search(F, i):
    if "Pavo" not in pavo_open(F, i):
        return False
    menu_pick(F, i, 0)
    advance(F, i, 4, 120)
    advance(F, i, 1, 150)
    advance(F, i, 1, T["adventure_log_save"])
    F.run(300)
    advance(F, i, 1, 200)
    advance(F, i, 1, 600)
    return True


def guest_join_live(L, i):
    L.hold(i, ["A"], 4)
    L.run(150)
    L.hold(i, ["A"], 4)
    L.run(900)
