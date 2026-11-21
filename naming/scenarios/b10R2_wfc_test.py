import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "R2", "wfctest")
CONNECTION = 0x0224E53C


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def state(con):
    link = word(con, CONNECTION)
    if not link:
        return "link=00000000"
    return f"link={link:08x} state+0x2260={word(con, link + 0x2260)}"


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"f{con.frames}_{label}.png"))


def step(F, out, frames):
    con = F.cons[0]
    last = None
    for _ in range(frames):
        F.run(1)
        now = state(con)
        if now != last:
            out.append(f"{con.frames} {now}")
            last = now


def tap(F, x, y):
    F.cons[0].touch(x, y)
    F.run(6)
    F.cons[0].touch()


def play(F):
    import dqix_flows
    T = dqix_flows.T
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
        for _ in range(2):
            F.hold(0, ["A"], 3)
            F.run(300)
        snap(F, "settings")
        out.append(f"{F.cons[0].frames} tap Test Connection")
        tap(F, 190, 36)
        for i in range(10):
            step(F, out, 180)
            snap(F, f"test{i}")
        out.append(f"{F.cons[0].frames} press A")
        F.hold(0, ["A"], 3)
        step(F, out, 300)
        snap(F, "after_a")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "state.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
