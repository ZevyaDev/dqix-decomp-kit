import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
LOG = os.path.join(kitpaths.SP, "names", "dyn", "probe", "N6_wfc_memory", "memory.log")
WATCH = {"keyboard": 0x02250BFC, "keypad": 0x02250C00, "settings": 0x02290CFC, "link": 0x0224E53C}


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def text(con, addr, size):
    raw = bytes(con.read(addr, size))
    return raw.split(b"\0", 1)[0].decode("latin-1")


def state(con):
    values = {name: word(con, addr) for name, addr in WATCH.items()}
    link = values["link"]
    extra = f" linkState={word(con, link + 0x2260)}" if link else ""
    return " ".join(f"{name}={value:08x}" for name, value in values.items()) + extra


def settings(con, out, label):
    block = word(con, WATCH["settings"])
    if not block:
        out.append(f"{con.frames} {label}: settings=0")
        return
    for i in range(4):
        entry = block + i * 0x100
        status = bytes(con.read(entry + 0xE7, 1))[0]
        out.append(f"{con.frames} {label}: settings+{i * 0x100:#x} ssid@+0x40={text(con, entry + 0x40, 0x20)!r} status@+0xe7={status:#04x}")
    out.append(f"{con.frames} {label}: settings+0x400 ssid@+0x440={text(con, block + 0x440, 0x20)!r} index@+0x4f4={bytes(con.read(block + 0x4F4, 1))[0]}")


def step(F, out, frames, every=30):
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
    out.append(f"{con.frames} press A (connection 1)")
    F.hold(0, ["A"], 3)
    step(F, out, 300)
    settings(con, out, "connection 1 page")
    out.append(f"{con.frames} tap Test Connection")
    tap(F, 190, 36)
    step(F, out, 900, every=10)
    out.append(f"{con.frames} press A (dismiss result)")
    F.hold(0, ["A"], 3)
    step(F, out, 300)
    out.append(f"{con.frames} press A (SSID Edit)")
    F.hold(0, ["A"], 3)
    step(F, out, 300)
    out.append(f"{con.frames} tap Cancel")
    tap(F, 50, 180)
    step(F, out, 300)
    out.append(f"{con.frames} tap No (auto-obtain IP)")
    tap(F, 180, 122)
    step(F, out, 120)
    out.append(f"{con.frames} tap IP Address Edit")
    tap(F, 228, 152)
    step(F, out, 300)
    out.append(f"{con.frames} press B")
    F.hold(0, ["B"], 3)
    step(F, out, 300)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
