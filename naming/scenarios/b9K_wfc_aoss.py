import contextlib
import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b9", "K", "aoss")
AOSS = 0x0224E6E0
SOUND = 0x02290D00
DIALOG = 0x02290D10


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def byte(con, addr):
    return bytes(con.read(addr, 1))[0]


def sbyte(con, addr):
    return struct.unpack("<b", bytes(con.read(addr, 1)))[0]


def state(con):
    words = struct.unpack("<15I", bytes(con.read(AOSS, 0x3C)))
    parts = ["aoss=" + ",".join(f"{w:x}" for w in words)]
    sound = word(con, SOUND)
    if sound:
        player = word(con, sound + 0x94)
        flag = byte(con, player + 0x2C) if player else -1
        parts.append(f"handle={player:08x} player+0x2c={flag}")
    dialog = word(con, DIALOG)
    parts.append(f"dialog={dialog:08x}")
    if dialog:
        parts.append(f"dialog+0x1b={sbyte(con, dialog + 0x1b)} dialog+0x1c={byte(con, dialog + 0x1c)}")
    return " ".join(parts)


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"f{con.frames}_{label}.png"))


def step(F, out, frames, every=5):
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
    channels = []
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
        step(F, out, 900)
        out.append(f"{con.frames} press A (settings)")
        F.hold(0, ["A"], 3)
        step(F, out, 300)
        out.append(f"{con.frames} tap Connection 2")
        tap(F, 128, 63)
        step(F, out, 300)
        snap(F, "conn2")
        with channel_log(F, channels):
            out.append(f"{con.frames} tap AOSS")
            tap(F, 65, 130)
            for i in range(8):
                step(F, out, 300)
                snap(F, f"aoss{i}")
            out.append(f"{con.frames} press A")
            F.hold(0, ["A"], 3)
            step(F, out, 300)
            snap(F, "aoss_a")
            out.append(f"{con.frames} press A")
            F.hold(0, ["A"], 3)
            step(F, out, 300)
            snap(F, "aoss_aa")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "aoss.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
        with open(os.path.join(OUT, "channels.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(channels) + "\n")
