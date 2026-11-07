import struct

START = {"save": "D:/Downloads/dqvc/work/saves/github_playinful_dq9-tools/006 - Ivor Accompanied.sav",
         "state": "states/joined.mst"}
GAME_STATE = 0x020F33D8
ZONE = 0x020FB3F0
LAURA, IVOR = 0, 3


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def guest_nibble(F, index):
    member = u32(F, GAME_STATE + 8 + 4 * index)
    data = u32(F, member + 0x150) if 0x02000000 <= member < 0x02400000 else 0
    if not 0x02000000 <= data < 0x02400000:
        return None
    return F.cons[0].read(data + 0x56B, 1)[0] & 0xF


def map_name(F):
    return F.cons[0].read(u32(F, ZONE + 8) + 5, 7).split(b"\0")[0].decode("latin-1")


def play(F):
    if guest_nibble(F, LAURA) != 0 or not guest_nibble(F, IVOR):
        raise RuntimeError(f"joined: Laura {guest_nibble(F, LAURA)}, Ivor {guest_nibble(F, IVOR)}")
    F.hold(0, ["Left"], 30)
    F.hold(0, ["Down"], 240)
    F.hold(0, ["Right"], 28)
    F.hold(0, ["Down"], 200)
    F.run(150)
    if map_name(F) != "M01":
        raise RuntimeError(f"joined: still on {map_name(F)}, not Angel Falls outside the church")
    if not guest_nibble(F, IVOR):
        raise RuntimeError("joined: Ivor left the party")
    F.hold(0, ["Down"], 60)
    F.hold(0, ["Left"], 60)
    F.run(60)
