import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "M4", "tagmode")


def play(F):
    import dqix_flows
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "tagmode.log"), "w", encoding="utf-8")

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"f{con.frames}_{name}.png"))
        log.write(f"f{con.frames} shot {name}\n")
        log.flush()

    def press(key, wait, name):
        F.hold(0, [key], 3)
        F.run(wait)
        shot(name)

    F.run(30)
    F.go_npc(0, dqix_flows.NPC["Erinn"])
    F.run(90)
    dqix_flows.advance(F, 0, 1)
    dqix_flows.menu_pick(F, 0, 1)
    press("Down", 20, "pick")
    press("A", 240, "pointers_question")
    press("Down", 30, "pointers_no")
    press("A", 240, "map_question")
    press("Down", 30, "map_no")
    for n in range(6):
        press("A", 150, f"a{n}")
    F.run(600)
    shot("waiting")
    press("B", 120, "finish_question")
    press("A", 300, "finish_yes")
    for n in range(6):
        press("A", 150, f"exit_a{n}")
    F.run(300)
    shot("end")
    log.close()
