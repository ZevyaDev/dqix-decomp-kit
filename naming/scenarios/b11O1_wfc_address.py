import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "O1", "address")
SETUP_HANDLER = 0x02250C18
ADDRESS_PAGE = 0x02290C98


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def state(con):
    page = word(con, ADDRESS_PAGE)
    text = f"handler={word(con, SETUP_HANDLER):08x} address={page:08x}"
    if page:
        body = bytes(con.read(page, 0x18))
        text += (f" address+0={struct.unpack_from('<I', body, 0)[0]:08x} address+4={struct.unpack_from('<I', body, 4)[0]:08x}"
                 f" address+8..13={body[8:0x14].hex()} address+14={body[0x14]} address+15={body[0x15]}")
    return text


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"f{con.frames}_{label}.png"))


def step(F, out, frames):
    con = F.cons[0]
    for _ in range(frames):
        F.run(1)
        now = state(con)
        if now != step.last:
            out.append(f"{con.frames} {now}")
            step.last = now


step.last = None


def tap(F, out, x, y, label, frames):
    out.append(f"{F.cons[0].frames} tap ({x}, {y}) {label}")
    F.cons[0].touch(x, y)
    F.run(6)
    F.cons[0].touch()
    step(F, out, frames)


def press(F, out, key, label, frames):
    out.append(f"{F.cons[0].frames} press {key} ({label})")
    F.hold(0, [key], 3)
    step(F, out, frames)


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
        step(F, out, 900)
        press(F, out, "A", "connection settings", 300)
        press(F, out, "A", "connection 1", 300)
        snap(F, "settings")
        tap(F, out, 180, 122, "Auto-obtain IP Address: No", 120)
        snap(F, "auto_ip_no")
        tap(F, out, 228, 152, "IP Address: Edit", 300)
        snap(F, "ip_keypad")
        for x, y, label in ((100, 80, "digit"), (100, 80, "digit"), (100, 80, "digit"), (100, 80, "digit")):
            tap(F, out, x, y, label, 40)
        snap(F, "digits")
        press(F, out, "B", "leave keypad", 120)
        snap(F, "b_pressed")
        press(F, out, "A", "answer", 300)
        snap(F, "end")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "address.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
