import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b11", "O1", "watch")
SETUP = 0x02250C0C
LIST_PAGE = 0x02290CC0
ADDRESS_PAGE = 0x02290C98
SCROLL_BAR = 0x02290CF4
INPUT = 0x02290D40
SPRITE_FILES = 0x02290D2C
STACK_CONFIG = 0x022496A4
STACK_ALLOCATE = 0x0224C994
STACK_FREE = 0x0224C9C0
LOGIN = 0x0224E5E8


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def raw(con, addr, size):
    return bytes(con.read(addr, size))


def state(con):
    setup = raw(con, SETUP, 0x20)
    parts = [
        f"setup+0={setup[0]} setup+1={setup[1]} setup+c={struct.unpack_from('<I', setup, 0xC)[0]:08x}"
        f" setup+10={struct.unpack_from('<I', setup, 0x10)[0]} setup+14={struct.unpack_from('<I', setup, 0x14)[0]}",
    ]
    block = word(con, LIST_PAGE + 4)
    parts.append(f"list+0={raw(con, LIST_PAGE, 1)[0]} list+4={block:08x}")
    if block:
        parts.append(f"list.block+1c={raw(con, block + 0x1C, 1)[0]} list.block+1d={raw(con, block + 0x1D, 1)[0]}")
    page = word(con, ADDRESS_PAGE)
    parts.append(f"address={page:08x}")
    if page:
        body = raw(con, page, 0x18)
        parts.append(f"address+8..13={body[8:0x14].hex()} address+14={body[0x14]} address+15={body[0x15]}")
    bar = word(con, SCROLL_BAR)
    parts.append(f"scroll={bar:08x}")
    if bar:
        body = raw(con, bar, 0x20)
        parts.append(
            f"scroll+10={struct.unpack_from('<H', body, 0x10)[0]} scroll+12={struct.unpack_from('<H', body, 0x12)[0]}"
            f" scroll+18..1d={body[0x18:0x1E].hex()}")
    parts.append(f"input+0={raw(con, INPUT, 1)[0]} input+4={word(con, INPUT + 4):08x}")
    parts.append(f"sprites[0]={word(con, SPRITE_FILES):08x} sprites[1]={word(con, SPRITE_FILES + 4):08x}")
    config = word(con, STACK_CONFIG)
    parts.append(f"config={config:08x} alloc={word(con, STACK_ALLOCATE):08x} free={word(con, STACK_FREE):08x}")
    if config:
        body = raw(con, config, 0x38)
        parts.append("config+0..34=" + ",".join(f"{v:08x}" for v in struct.unpack("<14I", body)))
    login = raw(con, LOGIN, 0x18)
    parts.append("login=" + ",".join(f"{v:08x}" for v in struct.unpack("<6I", login)))
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
    for _ in range(0, frames, every):
        F.run(every)
        now = state(con)
        if now != step.last:
            out.append(f"{con.frames} {now}")
            step.last = now


step.last = None


def tap(F, out, x, y, label):
    out.append(f"{F.cons[0].frames} tap ({x}, {y}) {label}")
    F.cons[0].touch(x, y)
    F.run(6)
    F.cons[0].touch()


def press(F, out, key, label, frames):
    out.append(f"{F.cons[0].frames} press {key} ({label})")
    F.hold(0, [key], 3)
    step(F, out, frames)


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
        step(F, out, 900, every=10)
        snap(F, "top")
        out.append(f"{con.frames} lid closed")
        con.set_lid(True)
        step(F, out, 30)
        snap(F, "lid_closed")
        press(F, out, "A", "lid closed", 60)
        out.append(f"{con.frames} lid opened")
        con.set_lid(False)
        step(F, out, 120)
        snap(F, "lid_open")
        press(F, out, "A", "connection settings", 300)
        snap(F, "list")
        for key in ("Right", "Left", "Down", "Up"):
            press(F, out, key, "list cursor", 40)
            snap(F, f"list_{key.lower()}")
        press(F, out, "A", "connection 1", 300)
        snap(F, "settings")
        for i in range(8):
            press(F, out, "Down", "settings", 40)
        snap(F, "scrolled")
        for i in range(8):
            press(F, out, "Up", "settings", 40)
        snap(F, "unscrolled")
        tap(F, out, 190, 36, "Test Connection")
        for i in range(5):
            step(F, out, 180)
            snap(F, f"test{i}")
        press(F, out, "A", "test result", 300)
        snap(F, "after_test")
        tap(F, out, 180, 122, "Auto-obtain IP Address: No")
        step(F, out, 120)
        snap(F, "auto_ip_no")
        tap(F, out, 228, 152, "IP Address: Edit")
        step(F, out, 300)
        snap(F, "ip_keypad")
        tap(F, out, 100, 80, "keypad digit")
        step(F, out, 60)
        snap(F, "digit")
        press(F, out, "B", "leave keypad", 300)
        snap(F, "end")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "watch.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
