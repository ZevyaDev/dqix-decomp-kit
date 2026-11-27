import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "M8", "shots")
ACCOLADE_SCRIPT_PTR = 0x02109D8C


def shot(F, name):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, f"acc_f{F.cons[0].frames}_{name}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def tap(F, key, wait, name=None):
    F.hold(0, [key], 3)
    F.run(wait)
    if name:
        shot(F, name)


def describe(F):
    con = F.cons[0]
    ptr = struct.unpack("<I", con.read(ACCOLADE_SCRIPT_PTR, 4))[0]
    if not ptr:
        return "script ptr 0"
    block = con.read(ptr, 0xD0)
    words = struct.unpack_from("<3I", block, 0)
    queued, running = struct.unpack_from("<ii", block, 0x60)
    count = struct.unpack_from("<h", block, 0x68)[0]
    if not 0 <= count <= 50:
        return f"script 0x{ptr:08x} count {count} (block reused)"
    ids = struct.unpack_from("<50h", block, 0x6A)[:count]
    ended = struct.unpack_from("<i", block, 0x48)[0]
    return (f"script 0x{ptr:08x} +0 0x{words[0]:x} +4 0x{words[1]:08x} +8 0x{words[2]:x} "
            f"+0x48 {ended} queued {queued} running {running} count {count} "
            f"ids {[hex(i) for i in ids]}")


def play(F):
    F.run(30)
    print(f"f{F.cons[0].frames} {describe(F)}")
    tap(F, "X", 60)
    tap(F, "Right", 20)
    tap(F, "Down", 20)
    tap(F, "Down", 20)
    tap(F, "A", 90)
    tap(F, "Down", 20)
    tap(F, "Down", 20)
    tap(F, "A", 150)
    tap(F, "A", 200, "skill_member")
    F.hold(0, ["Right"], 1000)
    F.run(30)
    for _ in range(5):
        tap(F, "Down", 20)
    shot(F, "confirm_cursor")
    last = None
    for i in range(16):
        F.hold(0, ["A"], 3)
        for _ in range(150):
            F.run(1)
            now = describe(F)
            if now != last:
                print(f"a{i} f{F.cons[0].frames} {now}")
                last = now
        shot(F, f"after_a{i}")
