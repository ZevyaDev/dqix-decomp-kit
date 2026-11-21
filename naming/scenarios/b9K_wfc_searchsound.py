import contextlib
import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b9", "K", "searchsound")
SOUND = 0x02290D00


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def byte(con, addr):
    return bytes(con.read(addr, 1))[0]


def state(con):
    sound = word(con, SOUND)
    if not sound:
        return "sound=0"
    player = word(con, sound + 0x94)
    flag = byte(con, player + 0x2C) if player else -1
    return f"handle={player:08x} player+0x2c={flag}"


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"f{con.frames}_{label}.png"))


def step(F, out, frames, every=2):
    con = F.cons[0]
    last = None
    for _ in range(0, frames, every):
        F.run(every)
        now = state(con)
        if now != last:
            out.append(f"{con.frames} {now}")
            last = now


def probe_of(F):
    for cell in type(F).run.__closure__ or ():
        if type(cell.cell_contents).__name__ == "Probe":
            return cell.cell_contents
    return None


@contextlib.contextmanager
def channel_log(F, out):
    con = F.cons[0]
    points = {}
    for ch in range(16):
        points[con.add_watchpoint(0x04000404 + ch * 0x10, 4, write=True, cpu=7)] = ch
    probe = probe_of(F)
    forward = probe.hit if probe else None

    def hit(brk):
        if brk.id in points:
            out.append(f"{con.frames} ch{points[brk.id]} sad={brk.value:08x}")
        elif forward:
            forward(brk)

    if probe:
        probe.hit = hit
    try:
        yield out
    finally:
        if probe:
            probe.hit = forward
        for point in points:
            con.remove_point(point)


def tap(F, x, y):
    F.cons[0].touch(x, y)
    F.run(6)
    F.cons[0].touch()


def play(F):
    import dqix_flows
    T = dqix_flows.T
    con = F.cons[0]
    out = []
    try:
        F.run(T["power_on_to_title"])
        F.hold(0, ["Start"], 4)
        F.run(T["title_start_to_log_list"])
        F.hold(0, ["A"], 4)
        F.run(T["title_start_to_log_list"])
        for _ in range(2):
            F.hold(0, ["Down"], 3)
            F.run(T["menu_cursor_step"])
        F.hold(0, ["A"], 3)
        F.run(900)
        F.hold(0, ["A"], 3)
        F.run(300)
        tap(F, 128, 63)
        F.run(300)
        with channel_log(F, out):
            out.append(f"{con.frames} press A (search)")
            F.hold(0, ["A"], 3)
            step(F, out, 150)
            snap(F, "searching")
            step(F, out, 300)
            snap(F, "found")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "searchsound.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
