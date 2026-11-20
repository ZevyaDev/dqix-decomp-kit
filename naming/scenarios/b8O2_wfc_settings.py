import os
import struct
import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
OUT = os.path.join(kitpaths.SP, "names", "b8", "O2", "settings")
PAGE = 0x02290CA0


def state(con):
    raw = bytes(con.read(PAGE, 12))
    block = struct.unpack("<I", raw[8:12])[0]
    extra = ""
    if block:
        extra = f" block+0x40..0x45={bytes(con.read(block + 0x40, 6)).hex()}"
    return f"page={raw.hex()} scroll@+4={struct.unpack('<H', raw[4:6])[0]} block@+8={block:08x}{extra}"


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
        for label in ("connection settings", "connection 1"):
            out.append(f"{con.frames} press A ({label})")
            F.hold(0, ["A"], 3)
            step(F, out, 300)
        snap(F, "page")
        for i in range(8):
            out.append(f"{con.frames} press Down")
            F.hold(0, ["Down"], 3)
            step(F, out, 40)
        snap(F, "scrolled")
        out.append(f"{con.frames} press B")
        F.hold(0, ["B"], 3)
        step(F, out, 300)
        snap(F, "back")
    finally:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "settings.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
