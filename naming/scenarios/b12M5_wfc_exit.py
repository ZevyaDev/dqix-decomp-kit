import os
import struct

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
DRIVER = 0x021142E0
LOG = os.path.join(kitpaths.SP, "names", "b12", "M5", "wfc_exit")


def snap(F, label):
    from PIL import Image
    con = F.cons[0]
    px = bytes(con.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        f"{LOG}.{F.run_id}.f{con.frames}_{label}.png")


def watch(F, log, frames):
    con = F.cons[0]
    last = None
    for _ in range(0, frames, 5):
        F.run(5)
        ready = struct.unpack("<H", con.read(DRIVER, 2))[0]
        if ready != last:
            log.write(f"f{con.frames} driverReady={ready}\n")
            last = ready


def play(F):
    import dqix_flows
    T = dqix_flows.T
    run = 1
    while os.path.exists(f"{LOG}.{run}.log"):
        run += 1
    F.run_id = run
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(f"{LOG}.{run}.log", "w", encoding="utf-8", newline="\n") as log:
        F.run(T["power_on_to_title"])
        F.hold(0, ["Start"], 4)
        F.run(T["title_start_to_log_list"])
        F.hold(0, ["A"], 4)
        F.run(T["title_start_to_log_list"])
        for _ in range(2):
            F.hold(0, ["Down"], 3)
            F.run(T["menu_cursor_step"])
        F.hold(0, ["A"], 3)
        watch(F, log, 900)
        for _ in range(2):
            F.hold(0, ["A"], 3)
            watch(F, log, 300)
        snap(F, "settings")
        F.cons[0].touch(190, 36)
        F.run(6)
        F.cons[0].touch()
        log.write(f"f{F.cons[0].frames} touched Test Connection\n")
        watch(F, log, 1800)
        snap(F, "tested")
        for n in range(6):
            F.hold(0, ["B"], 3)
            log.write(f"f{F.cons[0].frames} press B\n")
            watch(F, log, 240)
            snap(F, f"b{n}")
