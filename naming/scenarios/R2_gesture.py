START = {"save": "states/host.sav", "state": "states/inn.0.mst"}

HERO = 0x022bbbdc
LOG = "D:/Downloads/decomp/dqix-sp/names/b7/R2/gesture_mem.log"


def play(F):
    con = F.cons[0]
    out = open(LOG, "w")
    last = [None]

    def state():
        b = con.read(HERO + 0x178, 16)
        count = b[4] - 256 if b[4] > 127 else b[4]
        return (list(b[0:4]), count, b[5], b[6], b[0x0d])

    def watch(n):
        for _ in range(n):
            F.run(1)
            s = state()
            if s != last[0]:
                out.write(f"f{con.frames} ids={s[0]} count={s[1]} index={s[2]} phase={s[3]} +0x185={s[4]}\n")
                last[0] = s
        out.flush()

    watch(60)
    out.write(f"f{con.frames} press B, B+Up\n")
    F.hold(0, ["B"], 10)
    F.hold(0, ["B", "Up"], 4)
    F.hold(0, ["B"], 10)
    watch(240)
    out.write(f"f{con.frames} press B, B+Right\n")
    F.hold(0, ["B"], 10)
    F.hold(0, ["B", "Right"], 4)
    watch(240)
    out.write(f"f{con.frames} press A\n")
    F.hold(0, ["A"], 4)
    watch(240)
    out.close()
