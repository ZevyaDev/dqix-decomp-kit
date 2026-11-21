import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "R2", "dialog")
BUTTON_BAR = 0x02250BA8
SUB_MESSAGE_OPEN = 0x02250BAC
CURSOR_SPRITES = 0x02250BF0
TOP_GRAPHICS = 0x02290D04
STEP_INDICATOR = 0x02290D08
DIALOG = 0x02290D10


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def byte(con, addr):
    return bytes(con.read(addr, 1))[0]


def sbyte(con, addr):
    return struct.unpack("<b", bytes(con.read(addr, 1)))[0]


def state(con):
    parts = []
    bar = word(con, BUTTON_BAR)
    parts.append(f"bar={bar:08x}")
    parts.append(f"subMsg={byte(con, SUB_MESSAGE_OPEN)}")
    cursor = word(con, CURSOR_SPRITES)
    parts.append(f"cursor={cursor:08x}")
    if cursor:
        parts.append("cursor[]=" + ",".join(f"{word(con, cursor + 4 * i):08x}" for i in range(4)))
    parts.append(f"top+0={word(con, TOP_GRAPHICS):08x} top+4={word(con, STEP_INDICATOR):08x}")
    dialog = word(con, DIALOG)
    parts.append(f"dialog={dialog:08x}")
    if dialog:
        parts.append(
            f"dialog+0x14={word(con, dialog + 0x14):08x} dialog+0x1a={sbyte(con, dialog + 0x1a)} "
            f"dialog+0x1b={sbyte(con, dialog + 0x1b)} dialog+0x1c={byte(con, dialog + 0x1c)} "
            f"dialog+0x1d={byte(con, dialog + 0x1d)} dialog+0x1e={byte(con, dialog + 0x1e)}")
    return " ".join(parts)


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"f{con.frames}_{label}.png"))


def step(F, out, frames, every=1):
    con = F.cons[0]
    last = None
    for _ in range(0, frames, every):
        F.run(every)
        now = state(con)
        if now != last:
            out.append(f"{con.frames} {now}")
            last = now


def tap(F, x, y):
    F.cons[0].touch(x, y)
    F.run(6)
    F.cons[0].touch()


def press(F, out, key, label, frames):
    out.append(f"{F.cons[0].frames} press {key} ({label})")
    F.hold(0, [key], 3)
    step(F, out, frames)
    snap(F, label)


def touch(F, out, x, y, label, frames):
    out.append(f"{F.cons[0].frames} tap {x},{y} ({label})")
    tap(F, x, y)
    step(F, out, frames)
    snap(F, label)


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
        snap(F, "top")
        press(F, out, "A", "settings", 300)
        touch(F, out, 128, 63, "conn2", 300)
        press(F, out, "A", "search", 300)
        step(F, out, 300)
        snap(F, "aplist")
        press(F, out, "A", "pick_ap", 600)
        press(F, out, "B", "saved_b", 300)
        press(F, out, "A", "saved_ok", 300)
        step(F, out, 900)
        snap(F, "tested")
        press(F, out, "A", "after_test", 300)
        snap(F, "step1")
        touch(F, out, 128, 97, "erase2", 120)
        press(F, out, "B", "erase2_no", 300)
        touch(F, out, 128, 97, "erase2_again", 120)
        press(F, out, "A", "erase2_yes", 300)
        press(F, out, "B", "back", 300)
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "dialog.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
