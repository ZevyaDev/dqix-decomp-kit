import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
WIRELESS = 0x020fefec
LINK = 0x021015a0
DRIVER = 0x021142e0
CHANNELS = 0x027ffcfa
LOG = os.path.join(kitpaths.SP, "names", "b10", "M7", "rapportal_search")


def u32(con, addr):
    return struct.unpack("<I", con.read(addr, 4))[0]


def snapshot(con):
    wireless = struct.unpack("<i", con.read(WIRELESS, 4))[0]
    link = struct.unpack("<i", con.read(LINK + 0x10, 4))[0]
    ready = struct.unpack("<H", con.read(DRIVER, 2))[0]
    block = u32(con, DRIVER + 4)
    status = u32(con, block + 4) if ready and 0x02000000 <= block < 0x02800000 else 0
    driver = struct.unpack("<H", con.read(status, 2))[0] if 0x02000000 <= status < 0x02800000 else -1
    channels = struct.unpack("<H", con.read(CHANNELS, 2))[0]
    return f"gLocalWireless={wireless} link+0x10={link} driverReady={ready} driverState={driver} u16@027ffcfa={channels:#06x}"


def watch(F, log, frames):
    con = F.cons[0]
    last = None
    for _ in range(frames):
        F.run(1)
        now = snapshot(con)
        if now != last:
            log.write(f"f{con.frames} {now}\n")
            last = now


def press(F, log, key, frames):
    F.hold(0, [key], 3)
    log.write(f"f{F.cons[0].frames} press {key}\n")
    watch(F, log, frames)


def play(F):
    import dqix_flows
    run = 1
    while os.path.exists(f"{LOG}.{run}.log"):
        run += 1
    with open(f"{LOG}.{run}.log", "w", encoding="utf-8", newline="\n") as log:
        watch(F, log, 30)
        dqix_flows.pavo_open(F, 0)
        log.write(f"f{F.cons[0].frames} Pavo menu open, cursor on 'Visit another world.'\n")
        for _ in range(9):
            press(F, log, "A", 150)
        for _ in range(4):
            press(F, log, "B", 150)
        watch(F, log, 300)
