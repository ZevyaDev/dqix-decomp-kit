import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("C5_krakpot", os.path.join(os.path.dirname(__file__), "C5_krakpot.py"))
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)

START = K.START
GAME_STATE = 0x020F33D8
PARTY = 0x020F5DDC
HERB = 0x55F0
OUT = os.path.join(kitpaths.SP, "names", "b10", "R1a", "krakheld")


def play(F):
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "krakheld.log"), "w")

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def bag(addr):
        ids_ptr, counts_ptr, slots = struct.unpack("<IIh", con.read(addr, 10))
        ids = list(struct.unpack(f"<{slots}h", con.read(ids_ptr, 2 * slots)))
        counts = list(struct.unpack(f"<{slots}b", con.read(counts_ptr, slots)))
        return ids_ptr, counts_ptr, slots, ids, counts

    def dump(tag):
        log.write(f"f{con.frames} {tag}\n")
        for index in range(4):
            obj = u32(GAME_STATE + 8 + 4 * index)
            data = u32(obj + 0x150) if 0x02000000 <= obj < 0x02400000 else 0
            if 0x02000000 <= data < 0x02400000:
                held = struct.unpack("<8h", con.read(data + 0x454, 16))
                log.write(f"  object {index} {obj:#x} data {data:#x} +0x454 {[hex(h & 0xFFFF) for h in held]}\n")
        log.write(f"  party order +0xf78 {list(con.read(PARTY + 0xF78, 4))} count {con.read(PARTY + 0xF7C, 1)[0]}\n")
        for addr in (PARTY, PARTY + 0xE04):
            _, _, slots, ids, counts = bag(addr)
            found = [(i, counts[i]) for i in range(slots) if ids[i] == HERB]
            used = sum(1 for i in ids if i >= 0)
            log.write(f"  bag {addr:#x} slots {slots} used {used} item {HERB:#x} at {found}\n")
        log.flush()

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    dump("start")
    ids_ptr, counts_ptr, slots, ids, counts = bag(PARTY)
    if HERB not in ids:
        raise RuntimeError("b10R1a_krakheld: no herb in the bag")
    slot = ids.index(HERB)
    kept = [(i, c) for i, c in zip(ids, counts) if i >= 0 and i != HERB]
    con.write(ids_ptr, struct.pack(f"<{slots}h", *([i for i, _ in kept] + [-1] * (slots - len(kept)))))
    con.write(counts_ptr, struct.pack(f"<{slots}b", *([c for _, c in kept] + [0] * (slots - len(kept)))))
    dump(f"item {HERB:#x} slot {slot} emptied and later slots moved up")
    original_press = K.press
    count = [0]

    def press(F2, key, wait):
        original_press(F2, key, wait)
        shot(f"k{count[0]:02d}_{key}")
        count[0] += 1

    K.press = press
    try:
        K.play(F)
    finally:
        K.press = original_press
    dump("end")
    log.close()
