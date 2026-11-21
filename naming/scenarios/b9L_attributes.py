import os
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
MENU_ROW = int(os.environ.get("B9L_MENU_ROW", "2"))
OUT = os.path.join(kitpaths.SP, "names", "b9", "L", f"attributes_row{MENU_ROW}")


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def tap(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    F.run(30)
    tap(F, "X", 60)
    shot(F, "menu")
    for _ in range(MENU_ROW):
        tap(F, "Down", 20)
    tap(F, "A", 90)
    shot(F, "pick")
    tap(F, "A", 120)
    shot(F, "member0")
    F.run(120)
    shot(F, "member0_settled")
    for n in range(3):
        tap(F, "Right", 90)
        shot(F, f"page{n}")
    tap(F, "Down", 90)
    shot(F, "member1")
    for _ in range(4):
        tap(F, "B", 30)
