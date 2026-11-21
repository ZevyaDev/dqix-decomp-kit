import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b9", "K", "dialog")
BUTTON_BAR = 0x02250BA8
SUB_MESSAGE_OPEN = 0x02250BAC
STEP_BLOCK = 0x02290D04
DIALOG = 0x02290D10
CONNECTION_SETTINGS = 0x02290CFC


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
    if bar:
        parts.append(f"bar+0x16={sbyte(con, bar + 0x16)} bar+0x17={byte(con, bar + 0x17)} bar+0x19={byte(con, bar + 0x19)}")
    parts.append(f"subMsg={byte(con, SUB_MESSAGE_OPEN)}")
    steps = word(con, STEP_BLOCK + 4)
    parts.append(f"step+0={word(con, STEP_BLOCK):08x} step+4={steps:08x}")
    if steps:
        parts.append(f"step+4->+0x14={word(con, steps + 0x14):08x} step+4->+0x18={byte(con, steps + 0x18)}")
    dialog = word(con, DIALOG)
    parts.append(f"dialog={dialog:08x}")
    if dialog:
        parts.append(f"dialog+0x1b={sbyte(con, dialog + 0x1b)} dialog+0x1c={byte(con, dialog + 0x1c)} dialog+0x1e={byte(con, dialog + 0x1e)}")
    settings = word(con, CONNECTION_SETTINGS)
    if settings:
        work = settings + 0x400
        ssid = bytes(con.read(work + 0x40, 0x20)).split(b"\0", 1)[0].decode("latin-1")
        entries = [byte(con, settings + i * 0x100 + 0xE7) for i in range(3)]
        parts.append(f"work+0xe7={byte(con, work + 0xE7)} work+0xf4={byte(con, work + 0xF4)} work+0x40='{ssid}' entries+0xe7={entries}")
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
