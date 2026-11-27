import importlib.util
import os
import struct
import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = {"save": "saves/story/033 - Tyrantula.sav",
         "state": os.path.join(kitpaths.SP, "names", "b8", "R3", "tyb.mst")}
GAME_STATE = 0x020F33D8
WIPE_FLAG = GAME_STATE + 0x5729
LAURA = 0
ROUNDS = 20
OUT = os.path.join(kitpaths.SP, "names", "b11", "M1", "bosswipe")


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def dead(F):
    return u32(F, stats(F, LAURA) + 0x14) & 1


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def note(F, out, tag):
    flag = F.cons[0].read(WIPE_FLAG, 1)[0]
    st = stats(F, LAURA)
    out.write(f"f{F.cons[0].frames} {tag} wipeFlag {flag} battle {B.byte(F, B.BATTLE)} "
              f"laura hp {u16(F, st)} dead {dead(F)}\n")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "bosswipe.log"), "w") as out:
        B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
        for r in range(ROUNDS):
            B.wait(F, "menu", lambda: B.round_over(F) or dead(F), 4000)
            note(F, out, f"round{r}")
            if B.finished(F) or dead(F):
                break
            B.choose(F)
            B.choose(F, last=True)
            for _ in range(0, 4000, 4):
                if B.round_over(F) or dead(F):
                    break
                F.run(4)
        shot(F, "end_of_fight")
        for k in range(45):
            if k % 2 == 0:
                B.press(F, "A")
            F.run(60)
            note(F, out, f"after{k}")
            shot(F, f"after{k:02d}")
