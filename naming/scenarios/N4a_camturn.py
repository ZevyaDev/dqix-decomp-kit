import struct

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
GAME_STATE = 0x020F33D8
LOG = "D:/Downloads/decomp/dqix-sp/names/b6/N4a/camturn.log"


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def snapshot(F, camera, label, out):
    yaw = struct.unpack("<i", F.cons[0].read(camera + 0x70, 4))[0]
    follow, turn, zone = struct.unpack("<3i", F.cons[0].read(camera + 0x238, 12))
    flags = F.cons[0].read(camera + 0x244, 1)[0]
    out.append(f"{label} frame={F.cons[0].frames} camera={camera:#x} word0={u32(F, camera):#x} "
               f"yaw={yaw:#x} +238={follow} +23c={turn} +240={zone} +244={flags:#x}")


def turn(F, camera, label, out):
    snapshot(F, camera, label + " start", out)
    F.hold(0, ["R"], 15)
    snapshot(F, camera, label + " after 15f R", out)
    F.hold(0, ["L"], 15)
    snapshot(F, camera, label + " after 15f L", out)
    F.run(20)


def walk(F, camera, label, key, out):
    for step in ("start", "after 30f " + key):
        if step != "start":
            F.hold(0, [key], 30)
        hero_object = u32(F, GAME_STATE + 8)
        hero = struct.unpack("<3i", F.cons[0].read(hero_object + 0x44, 12))
        target = struct.unpack("<3i", F.cons[0].read(camera + 0x10, 12))
        out.append(f"{label} {step} frame={F.cons[0].frames} hero={[hex(v) for v in hero]} "
                   f"target+10={[hex(v) for v in target]}")
    F.run(20)


def play(F):
    out = []
    F.run(30)
    camera = u32(F, GAME_STATE + 0x3B0)
    turn(F, camera, "A untouched", out)
    F.cons[0].write(camera + 0x23C, struct.pack("<i", 0))
    F.run(4)
    turn(F, camera, "B +23c=0", out)
    F.cons[0].write(camera + 0x23C, struct.pack("<i", 1))
    F.run(4)
    turn(F, camera, "C +23c=1", out)
    flags = F.cons[0].read(camera + 0x244, 1)[0]
    F.cons[0].write(camera + 0x244, bytes([flags | 2]))
    F.run(4)
    turn(F, camera, "D +244|=2", out)
    F.cons[0].write(camera + 0x244, bytes([flags]))
    F.run(4)
    turn(F, camera, "E +244 restored", out)
    F.cons[0].write(camera + 0x238, struct.pack("<i", 0))
    F.run(4)
    walk(F, camera, "F +238=0", "Down", out)
    F.cons[0].write(camera + 0x238, struct.pack("<i", 1))
    F.run(4)
    walk(F, camera, "G +238=1", "Up", out)
    with open(LOG, "w") as f:
        f.write("\n".join(out) + "\n")
