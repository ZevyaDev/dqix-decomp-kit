import os
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "O3", "equipturn")


def run_name(base):
    os.makedirs(OUT, exist_ok=True)
    name, n = base, 1
    while True:
        try:
            os.makedirs(os.path.join(OUT, name))
            return name
        except FileExistsError:
            n += 1
            name = f"{base}.r{n}"


def snap(F, run, label):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, run, f"f{con.frames}_{label}.png"))


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    run = run_name("run")
    F.run(30)
    press(F, "X", 40)
    press(F, "Down", 15)
    press(F, "A", 120)
    snap(F, run, "front")
    F.hold(0, ["L"], 30)
    F.run(10)
    snap(F, run, "turned_l")
    F.hold(0, ["L", "R"], 4)
    for i in range(4):
        F.run(6)
        snap(F, run, f"returning{i}")
    F.run(60)
    snap(F, run, "front_again")
    F.hold(0, ["R"], 30)
    F.run(10)
    snap(F, run, "turned_r")
    F.hold(0, ["L", "R"], 4)
    F.run(60)
    snap(F, run, "front_end")
