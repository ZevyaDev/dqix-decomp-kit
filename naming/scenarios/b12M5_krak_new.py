import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
GAME_STATE = 0x020F33D8
TABLE = GAME_STATE + 0x7AC4
ENTRIES = 0x1D7
CURSOR = ["Right"]
LOG = os.path.join(kitpaths.SP, "names", "b12", "M5", "krak_new")


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def table(F):
    return struct.unpack(f"<{ENTRIES}H", bytes(F.cons[0].read(TABLE, 2 * ENTRIES)))


def shot(F, run, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        f"{LOG}.{run}.f{con.frames}_{tag}.png")


def play(F):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    run = 1
    while os.path.exists(f"{LOG}.{run}.log"):
        run += 1
    before = table(F)
    F.run(30)
    F.move_to(0, tz=9.12)
    F.move_to(0, tx=1.74)
    F.align(0, tx=1.74)
    F.move_to(0, tz=7.92)
    F.hold(0, ["Up"], 2)
    F.run(4)
    for _ in range(5):
        press(F, "A", 90)
    for _ in range(4):
        press(F, "Down", 20)
    press(F, "A", 90)
    for key in CURSOR:
        press(F, key, 30)
    shot(F, run, "list")
    press(F, "A", 90)
    shot(F, run, "chosen")
    press(F, "A", 90)
    F.run(240)
    shot(F, run, "brewing")
    for n in range(6):
        press(F, "A", 90)
        shot(F, run, f"a{n}")
    after = table(F)
    for _ in range(10):
        press(F, "B", 60)
    F.run(120)
    with open(f"{LOG}.{run}.log", "w", encoding="utf-8", newline="\n") as log:
        log.write(f"cursor {CURSOR}; table {TABLE:#x}\n")
        log.write(f"before: {sum(1 for w in before if w >> 2)} used, {sum(1 for w in before if w & 2)} with bit1\n")
        log.write(f"after:  {sum(1 for w in after if w >> 2)} used, {sum(1 for w in after if w & 2)} with bit1\n")
        for i, (a, b) in enumerate(zip(before, after)):
            if a != b:
                log.write(f"changed [{i}] {a:#06x} -> {b:#06x} id {b >> 2:#x} bit1 {(a >> 1) & 1}->{(b >> 1) & 1} "
                          f"bit0 {a & 1}->{b & 1}\n")
