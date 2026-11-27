import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "M1", "zonedraw_off")
DRAW_ZONE = 0x02016874
RETURN_AT_ONCE = bytes.fromhex("1eff2fe1")


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"f{F.cons[0].frames:05d}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)
    return path


def play(F):
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    with open(os.path.join(OUT, "zonedraw_off.log"), "w", encoding="utf-8", newline="\n") as log:
        F.run(60)
        log.write(f"f{con.frames} before {shot(F, 'before')}\n")
        original = bytes(con.read(DRAW_ZONE, 4))
        log.write(f"f{con.frames} first word {original.hex()}\n")
        con.write(DRAW_ZONE, RETURN_AT_ONCE)
        F.run(20)
        log.write(f"f{con.frames} patched {bytes(con.read(DRAW_ZONE, 4)).hex()} {shot(F, 'off')}\n")
        con.write(DRAW_ZONE, original)
        F.run(20)
        log.write(f"f{con.frames} restored {bytes(con.read(DRAW_ZONE, 4)).hex()} {shot(F, 'on')}\n")
