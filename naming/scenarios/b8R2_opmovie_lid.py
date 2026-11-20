import os
import kitpaths
START = {"save": "saves/dq9ds_kheg_aug30.sav"}

MOVIE_REQUEST = 0x020F97AE
OPENING_MOVIE = 4
MANAGER = 0x02109BF4
LOG = os.path.join(kitpaths.SP, "names", "b8", "R2", "opmovie_lid.log")


def play(F):
    con = F.cons[0]
    out = open(LOG, "w")

    def state(note):
        handle = con.read(MANAGER + 0x9C, 4)[::-1].hex()
        index = con.read(MANAGER + 0xA4, 2)[::-1].hex()
        offset = con.read(MANAGER + 0xA8, 4)[::-1].hex()
        out.write(f"f{con.frames} {note}: +0x9c {handle} +0xa4 {index} +0xa8 {offset}\n")
        out.flush()

    F.run(800)
    for _ in range(600):
        F.run(1)
        if con.read(MOVIE_REQUEST, 1)[0]:
            out.write(f"f{con.frames} main requested movie {con.read(MOVIE_REQUEST, 1)[0]}; replaced by {OPENING_MOVIE}\n")
            con.write(MOVIE_REQUEST, bytes([OPENING_MOVIE]))
            break
    F.run(2100)
    state("before lid close")
    con.set_lid(True)
    for _ in range(6):
        F.run(30)
        state("lid closed")
    con.set_lid(False)
    for _ in range(10):
        F.run(30)
        state("lid open")
    for _ in range(30):
        F.run(300)
        state("playing")
    out.close()
