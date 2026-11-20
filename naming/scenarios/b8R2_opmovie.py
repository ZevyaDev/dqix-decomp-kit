import os
import kitpaths
START = {"save": "saves/dq9ds_kheg_aug30.sav"}

MOVIE_REQUEST = 0x020F97AE
OPENING_MOVIE = 4
LOG = os.path.join(kitpaths.SP, "names", "b8", "R2", "opmovie.log")


def play(F):
    con = F.cons[0]
    out = open(LOG, "w")
    F.run(800)
    for _ in range(600):
        F.run(1)
        if con.read(MOVIE_REQUEST, 1)[0]:
            out.write(f"f{con.frames} main requested movie {con.read(MOVIE_REQUEST, 1)[0]}; replaced by {OPENING_MOVIE}\n")
            con.write(MOVIE_REQUEST, bytes([OPENING_MOVIE]))
            break
    for _ in range(40):
        F.run(300)
        handle = con.read(0x02109BF4 + 0x9C, 4)
        index = con.read(0x02109BF4 + 0xA4, 2)
        out.write(f"f{con.frames} +0x9c {handle[::-1].hex()} +0xa4 {index[::-1].hex()}\n")
    out.close()
