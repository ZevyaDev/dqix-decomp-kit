import importlib.util
import os
import struct
import kitpaths

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
GAME_STATE = 0x020F33D8
WIPE_FLAG = GAME_STATE + 0x5729
MEMBERS = (0, 1, 2, 3)
MENU_ORDER = (0, 3, 2, 1)
DEAD = 0x1
ROUNDS = 16
OUT = os.path.join(kitpaths.SP, "names", "b11", "M1", "wipeout")


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def stats(F, index):
    return u32(F, u32(F, GAME_STATE + 8 + 4 * index) + 0x138)


def dead(F, index):
    return u32(F, stats(F, index) + 0x14) & DEAD


def weaken(F):
    for i in MEMBERS:
        if not dead(F, i):
            st = stats(F, i)
            F.cons[0].write(st, struct.pack("<H", 1))
            F.cons[0].write(st + 0xA, struct.pack("<H", 0))


def shot(F, tag):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{con.frames:05d}_{tag}.png"))


def note(F, out, tag):
    flag = F.cons[0].read(WIPE_FLAG, 1)[0]
    alive = [i for i in MEMBERS if not dead(F, i)]
    out.write(f"f{F.cons[0].frames} {tag} wipeFlag {flag} battle {B.byte(F, B.BATTLE)} alive {alive}\n")


def play(F):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "wipeout.log"), "w") as out:
        for _ in range(120):
            if B.byte(F, B.BATTLE):
                break
            F.hold(0, ["Left"], 4)
        B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
        B.wait(F, "menu", lambda: B.hand(F) is not None, 900)
        note(F, out, "battle")
        for n in range(ROUNDS):
            B.choose(F)
            alive = [i for i in MENU_ORDER if not dead(F, i)]
            for i in alive:
                B.choose(F, ("Down", 2), last=i == alive[-1])
            for _ in range(0, 3000, 4):
                weaken(F)
                if B.round_over(F):
                    break
                F.run(4)
            else:
                raise RuntimeError("wipeout: no end of round after 3000 frames")
            note(F, out, f"round{n}")
            if B.finished(F) or not any(not dead(F, i) for i in MEMBERS):
                break
        shot(F, "last_round")
        for k in range(40):
            if k < 20:
                B.press(F, "A")
            F.run(60)
            note(F, out, f"after{k}")
            shot(F, f"after{k:02d}")
            if B.byte(F, B.BATTLE) == 0 and k >= 30:
                break
