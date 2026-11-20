import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b8", "O2", "watch")
STACK = 0x0224C980
SCREENS = {"apList": 0x02290C8C, "settings": 0x02290CA0}
WORKERS = {"e580": 0x0224E580, "e588": 0x0224E588}
WIRELESS = 0x02290D18
LINK = 0x0224F670


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def half(con, addr):
    return struct.unpack("<H", bytes(con.read(addr, 2)))[0]


def byte(con, addr):
    return bytes(con.read(addr, 1))[0]


def ip(value):
    return ".".join(str((value >> s) & 0xFF) for s in (0, 8, 16, 24))


def state(con):
    parts = [
        f"stack[0]={byte(con, STACK)} stack[8]={half(con, STACK + 8)} stack[0xc]={word(con, STACK + 0xC)}"
        f" stack[0x44]={word(con, STACK + 0x44)} stack[0x50]={ip(word(con, STACK + 0x50))}"
    ]
    for name, addr in WORKERS.items():
        parts.append(f"{name}={word(con, addr):08x}")
    for name, addr in SCREENS.items():
        raw = bytes(con.read(addr, 12))
        parts.append(f"{name}={raw.hex()}")
        block = word(con, addr + (4 if name == "apList" else 8))
        if block and name == "apList":
            count = byte(con, block + 0x51)
            entries = word(con, block)
            ssids = []
            if entries:
                for i in range(min(count, 4)):
                    ssids.append(bytes(con.read(entries + i * 0x2A, 0x20)).split(b"\0", 1)[0].decode("latin-1"))
            parts.append(f"apList.block+0x51={count} ssids={ssids}")
    parts.append(f"wireless={word(con, WIRELESS):08x},{word(con, WIRELESS + 4):08x}")
    parts.append(f"link+0x2c={word(con, LINK + 0x2C)} link+0x28={word(con, LINK + 0x28)}")
    return " ".join(parts)


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"f{con.frames}_{label}.png"))


def step(F, out, frames, every=10):
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
        step(F, out, 900)
        out.append(f"{con.frames} press A (connection settings)")
        F.hold(0, ["A"], 3)
        step(F, out, 300)
        snap(F, "step1")
        out.append(f"{con.frames} tap Connection 2")
        tap(F, 128, 63)
        step(F, out, 300)
        snap(F, "conn2")
        out.append(f"{con.frames} press A")
        F.hold(0, ["A"], 3)
        step(F, out, 300)
        snap(F, "conn2_a")
        out.append(f"{con.frames} press A")
        F.hold(0, ["A"], 3)
        step(F, out, 600)
        snap(F, "conn2_aa")
        out.append(f"{con.frames} press A")
        F.hold(0, ["A"], 3)
        step(F, out, 600)
        snap(F, "conn2_aaa")
        for i in range(3):
            out.append(f"{con.frames} press B")
            F.hold(0, ["B"], 3)
            step(F, out, 300)
            snap(F, f"back{i}")
        out.append(f"{con.frames} tap Connection 1")
        tap(F, 46, 63)
        step(F, out, 300)
        out.append(f"{con.frames} press A (connection 1)")
        F.hold(0, ["A"], 3)
        step(F, out, 300)
        snap(F, "conn1")
        out.append(f"{con.frames} tap Test Connection")
        tap(F, 190, 36)
        step(F, out, 1200)
        snap(F, "tested")
        out.append(f"{con.frames} press A (dismiss result)")
        F.hold(0, ["A"], 3)
        step(F, out, 300)
        snap(F, "dismissed")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "watch.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
