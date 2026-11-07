import struct

START = {"save": "D:/Downloads/dqvc/work/saves/github_playinful_dq9-tools/038 - Drak.sav",
         "state": "states/ladder.mst"}
GAME_STATE = 0x020F33D8
ZONE = 0x020FB3F0
LADDER = 0x26C
BOTTOM, TOP = "D08M06", "D08M05"


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def hero(F):
    return u32(F, GAME_STATE + 8 + u32(F, GAME_STATE + 0x3AC) * 4)


def on_ladder(F):
    return F.cons[0].read(hero(F) + LADDER, 1)[0]


def map_name(F):
    return F.cons[0].read(u32(F, ZONE + 8) + 5, 7).split(b"\0")[0].decode("latin-1")


def climb(F, key, start, end, limit=120):
    if map_name(F) != start:
        raise RuntimeError(f"ladder: on {map_name(F)}, not {start}")
    seen = False
    for _ in range(limit):
        F.hold(0, [key], 4)
        seen = seen or on_ladder(F) != 0
        if seen and on_ladder(F) == 0 and map_name(F) == end:
            F.run(30)
            return
    raise RuntimeError(f"ladder: {key} from {start} never reached {end} (climbed: {seen})")


def play(F):
    F.run(20)
    climb(F, "Up", BOTTOM, TOP)
    climb(F, "Down", TOP, BOTTOM)
