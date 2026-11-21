import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
TABLE_WORD = 0x0238AFF0
FILE_DATA = 0x02120EF4
LOG = os.path.join(kitpaths.SP, "names", "b9", "E", "b9E_spelltable_mem.log")


def play(F):
    F.run(30)
    F.hold(0, ["X"], 4)
    F.run(60)
    c = F.cons[0]
    disk = open(os.path.join(kitpaths.REPO, "extract", "usa", "files", "data", "prm", "spelltable.bin"), "rb").read()
    loaded = bytes(c.read(FILE_DATA, len(disk)))
    block = struct.unpack("<I", c.read(TABLE_WORD, 4))[0]
    with open(LOG, "w", encoding="utf-8") as log:
        log.write(f"f{c.frames} spelltable.bin {len(disk):#x} bytes; memory at {FILE_DATA:#x} equal: {loaded == disk}\n")
        log.write(f"f{c.frames} word at {TABLE_WORD:#x} = {block:#x}\n")
        if block:
            raw = bytes(c.read(block, 0x550))
            nonzero = sum(1 for b in raw if b)
            log.write(f"block {block:#x}: {nonzero} nonzero bytes of 0x550; first 0x40: {raw[:0x40].hex()}\n")
