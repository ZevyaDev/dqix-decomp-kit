import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "R3")
SCRIPT_PTR = 0x02109D8C
SIZES = {
    0x1D18: "cmtB13", 0x3938: "cmtB14B15", 0x6278: "cmtC16C17", 0x56D8: "cmtC18C22",
    0x4898: "cmtC23C24_1", 0x138: "cmtClear", 0x5AC8: "cmtD25D29", 0x36E8: "cmtD30D33",
    0x1F3C8: "cmtE36T86", 0x9788: "cmtHeader", 0x3138: "cmtK87", 0x46D8: "cmtK88K94",
    0x5318: "cmtK95K98", 0x5888: "cmtK99L101", 0x4AC8: "cmtL102L106", 0x46A8: "cmtM116M117",
    0x35B8: "cmtM118M121", 0x64C8: "cmtN122N126", 0x6018: "cmtN127N130", 0x52D8: "cmtO131O133",
    0x6808: "cmtO134O139", 0xF338: "cmtQ141", 0x1CDF8: "cmtTailC", 0x2598: "cmtTailG",
    0x3688: "title_btl", 0x4728: "title_clr", 0x150F8: "title_gyalel", 0x20938: "title_skl",
}


RUN = {"suffix": ""}


def log_path():
    base = os.path.join(OUT, "records.log")
    path, n = base, 1
    while os.path.exists(path):
        n += 1
        path = f"{base[:-4]}.r{n}.log"
    RUN["suffix"] = "" if n == 1 else f".r{n}"
    return path


def shot(F, name):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    path = os.path.join(OUT, "shots", f"rec_f{F.cons[0].frames}_{name}{RUN['suffix']}.png")
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)
    return path


def describe(F):
    con = F.cons[0]
    ptr = struct.unpack("<I", con.read(SCRIPT_PTR, 4))[0]
    if not ptr:
        return "script ptr 0"
    block = con.read(ptr, 0xD0)
    size = struct.unpack_from("<I", block, 8)[0]
    queued, running = struct.unpack_from("<ii", block, 0x60)
    count = struct.unpack_from("<h", block, 0x68)[0]
    ended = struct.unpack_from("<i", block, 0x48)[0]
    if not 0 <= count <= 50:
        return f"script 0x{ptr:08x} count {count} (block reused)"
    ids = struct.unpack_from("<50h", block, 0x6A)[:count]
    return (f"script 0x{ptr:08x} +8 0x{size:x} ({SIZES.get(size, '?')}.stb) +0x48 {ended} "
            f"+0x60 {queued} +0x64 {running} +0x68 {count} ids {[hex(i) for i in ids]}")


def play(F):
    os.makedirs(os.path.join(OUT, "shots"), exist_ok=True)
    log = open(log_path(), "w", encoding="utf-8", newline="\n")
    try:
        F.run(30)
        log.write(f"f{F.cons[0].frames} before {describe(F)}\n")
        for key, wait in (("X", 60), ("Right", 20), ("Down", 20)):
            F.hold(0, [key], 3)
            F.run(wait)
        F.hold(0, ["A"], 3)
        last = None
        for i in range(600):
            F.run(1)
            now = describe(F)
            if now != last:
                log.write(f"f{F.cons[0].frames} {now}\n")
                last = now
            if i in (150, 300, 599):
                log.write(f"f{F.cons[0].frames} shot {os.path.basename(shot(F, f'open{i}'))}\n")
        F.hold(0, ["B"], 3)
        F.run(120)
        log.write(f"f{F.cons[0].frames} shot {os.path.basename(shot(F, 'closed'))}\n")
    finally:
        log.close()
