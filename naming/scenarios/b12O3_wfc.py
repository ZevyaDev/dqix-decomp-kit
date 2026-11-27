import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b12", "O3", "wfc")
SETUP = 0x02250C0C
TEXT_PAGE = 0x02290C94
BUFFERS = 0x0224E5C4
PACKED = 0x0224E6AC
CREDENTIALS = 0x0224E5F4
KEYBOARD = 0x02250BFC
EDITED = 0x02290CFC


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def raw(con, addr, size):
    return bytes(con.read(addr, size))


def state(con):
    setup = raw(con, SETUP, 0x20)
    parts = [f"handler={struct.unpack_from('<I', setup, 0xC)[0]:08x}"
             f" setup+18={struct.unpack_from('<i', setup, 0x18)[0]} setup+1c={struct.unpack_from('<i', setup, 0x1C)[0]}"]
    page = word(con, TEXT_PAGE)
    parts.append(f"text={page:08x}")
    if page:
        body = raw(con, page, 0x2C)
        text = body[8:0x28].split(b"\0", 1)[0].decode("latin1")
        parts.append(f"text+8='{text}' text+29={body[0x29]} text+2a={body[0x2A]}")
    keyboard = word(con, KEYBOARD)
    parts.append(f"keyboard={keyboard:08x}")
    if keyboard:
        parts.append(f"keyboard+11d={raw(con, keyboard + 0x11D, 1)[0]}")
    edited = word(con, EDITED)
    if edited:
        parts.append(f"edited+f4={raw(con, edited + 0x4F4, 1)[0]}")
    parts.append("buffers=" + ",".join(f"{v:08x}" for v in struct.unpack("<5I", raw(con, BUFFERS, 0x14))))
    parts.append(f"packed={raw(con, PACKED, 14).hex()} credentials={raw(con, CREDENTIALS, 0x14).hex()}")
    return " ".join(parts)


def run_name(base):
    os.makedirs(OUT, exist_ok=True)
    name, n = base, 1
    while True:
        try:
            with open(os.path.join(OUT, f"{name}.log"), "x", encoding="utf-8"):
                return name
        except FileExistsError:
            n += 1
            name = f"{base}.r{n}"


def snap(F, run, label):
    from PIL import Image
    con = F.cons[0]
    folder = os.path.join(OUT, f"{run}_shots")
    os.makedirs(folder, exist_ok=True)
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(folder, f"f{con.frames}_{label}.png"))


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
    run = run_name("wfc")
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
        snap(F, run, "top")
        tap(F, out, 176, 100, "between the two top buttons", 60)
        snap(F, run, "top_gap")
        tap(F, out, 90, 100, "Nintendo Wi-Fi Connection Settings button", 300)
        snap(F, run, "list")
        press(F, out, "A", "Connection 1", 300)
        snap(F, run, "settings")
        tap(F, out, 220, 67, "SSID Edit", 12)
        for i in range(6):
            snap(F, run, f"ssid_slide{i}")
            step(F, out, 4)
        step(F, out, 280)
        snap(F, run, "ssid_keyboard")
        tap(F, out, 40, 112, "key q", 30)
        tap(F, out, 17, 112, "CAPS", 30)
        tap(F, out, 58, 112, "key w", 30)
        snap(F, run, "ssid_typed")
        tap(F, out, 236, 90, "backspace", 30)
        snap(F, run, "ssid_backspace")
        tap(F, out, 64, 179, "Cancel", 4)
        for i in range(6):
            snap(F, run, f"ssid_out{i}")
            step(F, out, 4)
        step(F, out, 280)
        snap(F, run, "settings_again")
        tap(F, out, 220, 94, "WEP Key Edit", 300)
        snap(F, run, "wep_keyboard")
        tap(F, out, 64, 179, "Cancel", 300)
        snap(F, run, "settings_after_wep")
        tap(F, out, 190, 36, "Test Connection", 60)
        snap(F, run, "test_start")
        for i in range(5):
            step(F, out, 180)
            snap(F, run, f"test{i}")
        press(F, out, "A", "test result", 300)
        snap(F, run, "end")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, f"{run}.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
