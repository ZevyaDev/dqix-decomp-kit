import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b9", "K", "priority")
NODES = [0x02259898, 0x02259888, 0x02259878, 0x02259868, 0x02259858, 0x02259848, 0x02259838,
         0x02259AC0, 0x02259AB0, 0x02259AA0, 0x02259A90, 0x02259A80]


def word(con, addr):
    return struct.unpack("<I", bytes(con.read(addr, 4)))[0]


def half(con, addr):
    return struct.unpack("<H", bytes(con.read(addr, 2)))[0]


def nodes(con):
    parts = []
    for node in NODES:
        entries = word(con, node + 8)
        count = word(con, node + 0xC)
        if not entries or count > 16:
            parts.append(f"{node:08x}:-")
            continue
        prios = [(half(con, entries + i * 8 + 4) >> 10) & 3 for i in range(count)]
        parts.append(f"{node:08x}:{entries:08x}x{count}:{''.join(map(str, prios))}")
    return " ".join(parts)


def snap(F, label):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    con = F.cons[0]
    px = bytes(con.screen())
    image = Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB")
    image.save(os.path.join(OUT, f"f{con.frames}_{label}.png"))


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
        F.run(700)
        for _ in range(4):
            F.run(50)
            out.append(f"{con.frames} {nodes(con)}")
        snap(F, "top")
        out.append(f"{con.frames} press A")
        F.hold(0, ["A"], 3)
        F.run(10)
        for _ in range(8):
            F.run(5)
            out.append(f"{con.frames} {nodes(con)}")
        F.run(200)
        out.append(f"{con.frames} {nodes(con)}")
        snap(F, "step1")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "priority.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
