import struct

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

OVERLAY = 0x02108D5C
OUT = "D:/Downloads/decomp/dqix-sp/names/b7/M3/flash"


def play(F):
    import os
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "flash.log"), "w")

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def state(tag):
        active, color, target, time, alpha, hold = struct.unpack("<BxHBxxxifi", con.read(OVERLAY, 0x14))
        log.write(f"f{con.frames} {tag}: +0 {active} +2 {color:#06x} +4 {target} +8 {time} +0xc {alpha} +0x10 {hold}\n")
        log.flush()

    F.run(60)
    state("idle")
    shot("1_idle")
    con.write(OVERLAY, struct.pack("<BxHBxxxifi", 1, 0x001F, 0x1F, 0, 31.0, 0))
    state("written: active, colour 0x001f, target 0x1f, time 0, alpha 31.0")
    F.run(10)
    state("after 10 frames")
    shot("2_red")
    con.write(OVERLAY + 4, struct.pack("<B", 1))
    con.write(OVERLAY + 8, struct.pack("<i", 1000))
    state("written: target 1, time 1000")
    F.run(30)
    state("after 30 frames")
    shot("3_fading")
    F.run(60)
    state("after 90 frames")
    shot("4_after")
    log.close()
