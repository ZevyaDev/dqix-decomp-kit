import os

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
SETTINGS = 0x027FFC80
NAME_COPY = 0x02100000
LOG = os.path.join(kitpaths.SP, "names", "b12", "M5", "nickname")


def play(F):
    con = F.cons[0]
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    run = 1
    while os.path.exists(f"{LOG}.{run}.log"):
        run += 1
    with open(f"{LOG}.{run}.log", "w", encoding="utf-8", newline="\n") as log:
        for frames in (10, 30, 30):
            F.run(frames)
            raw = bytes(con.read(SETTINGS, 0x70))
            log.write(f"f{con.frames} 0x027ffc80..+0x70: {raw.hex()}\n")
            name = raw[6:6 + 0x14].decode("utf-16-le", "replace").split("\0", 1)[0]
            log.write(f"f{con.frames} +0x02 {raw[2]:#04x} +0x03 {raw[3]} +0x04 {raw[4]} +0x06 '{name}' "
                      f"+0x1a {raw[0x1a]} +0x50 {raw[0x50]} +0x64 {raw[0x64] | raw[0x65] << 8:#06x}\n")
            copy = bytes(con.read(NAME_COPY, 0x18))
            log.write(f"f{con.frames} 0x02100000..+0x18: {copy.hex()}\n")
