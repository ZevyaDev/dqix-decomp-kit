import struct

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
SLOT_SET = 0x01FFD348
SLOTS = 0x01FFD364
MENU_CALLBACK_OVERLAY = 4
QUEST_MENU = 0x0217101C
FLAG_MANAGER = 0x02108844
QUEST_MANAGER = 0x02109418
OUT = "D:/Downloads/decomp/dqix-sp/names/b7/M3/quests"


def press(F, key, wait):
    F.hold(0, [key], 3)
    F.run(wait)


def play(F):
    import os
    from PIL import Image
    con = F.cons[0]
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "quests.log"), "w")

    def u32(a):
        return struct.unpack("<I", con.read(a, 4))[0]

    def shot(name):
        px = bytes(con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
            os.path.join(OUT, f"{name}.png"))
        log.write(f"f{con.frames} shot {name}.png\n")

    def slot0():
        return con.read(SLOTS + 6 * u32(SLOT_SET), 1)[0]

    def counts():
        if slot0() != MENU_CALLBACK_OVERLAY:
            return None
        menu = u32(QUEST_MENU)
        if not 0x02000000 <= menu < 0x02400000:
            return None
        return struct.unpack("<4h", con.read(menu + 0x48, 8))

    def dump():
        nibbles = con.read(FLAG_MANAGER + 0x2CC, 0x66)
        table = u32(QUEST_MANAGER + 0xA8)
        order = con.read(QUEST_MANAGER + 0xAC, 0xCC)
        entries = struct.unpack("<204H", con.read(table, 0x198))
        extra = {e & 0x1FF for e in entries if e & 0x400}
        number = {}
        for n in range(1, 0xCC):
            if order[n] not in number:
                number[order[n]] = n
        log.write(f"f{con.frames} menu +0x48 = {counts()}\n")
        by_state = {0: [], 1: [], 2: [], 3: []}
        bit8 = {True: [], False: []}
        for q in range(1, 0xCC):
            v = nibbles[q // 2] >> (4 * (q % 2)) & 0xF
            by_state[v & 3].append(q)
            if q in extra:
                bit8[bool(v & 8)].append(q)
        for s in range(4):
            qs = by_state[s]
            log.write(f"  state {s}: {len(qs)} ids ({len([q for q in qs if q in extra])} extra)\n")
        for q in by_state[2]:
            log.write(f"  state 2: id {q:#x} display number {number.get(q)} extra {q in extra}\n")
        log.write(f"  extra quests (table bit 0x400): {len(extra)}; nibble bit 0x8 set {len(bit8[True])}, clear {len(bit8[False])}\n")
        log.write(f"  extra with bit 0x8 clear: {[hex(q) for q in bit8[False]]}\n")
        log.write(f"  normal ids with bit 0x8 set: {len([q for q in range(1, 0xCC) if q not in extra and nibbles[q // 2] >> (4 * (q % 2)) & 8])}\n")
        log.flush()

    F.run(30)
    press(F, "X", 60)
    press(F, "Right", 20)
    press(F, "Down", 20)
    press(F, "A", 200)
    for _ in range(5):
        press(F, "Down", 30)
    press(F, "A", 200)
    press(F, "A", 150)
    dump()
    shot("1_normal")
    press(F, "B", 60)
    press(F, "Down", 30)
    press(F, "A", 150)
    dump()
    shot("2_extra")
    for _ in range(5):
        press(F, "B", 60)
    log.close()
