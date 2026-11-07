import importlib.util
import os
import struct

_spec = importlib.util.spec_from_file_location("battle", os.path.join(os.path.dirname(__file__), "battle.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

START = B.START
RECORDS = 0x020F384C
STRIDE = 0x964
PRIEST = 2
LOG = "D:/Downloads/decomp/dqix-sp/names/b7/M4/M4_levelup_mem.log"
SHOTS = "D:/Downloads/decomp/dqix-sp/names/b7/M4/levelup_shots"


def shot(F, path):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def u16(F, addr):
    return struct.unpack("<H", F.cons[0].read(addr, 2))[0]


def u32(F, addr):
    return struct.unpack("<I", F.cons[0].read(addr, 4))[0]


def describe(F, record):
    vocation = u32(F, record + 0x950)
    level = u16(F, record + 0x16C + 2 * vocation)
    exp = u32(F, record + 0x138 + 4 * vocation)
    spells = F.cons[0].read(record + 0x910, 9).hex()
    return f"record {record:#x} vocation {vocation} level {level} exp {exp} spells {spells}"


def play(F):
    with open(LOG, "w", encoding="utf-8") as log:
        records = [RECORDS + n * STRIDE for n in range(4)]
        for record in records:
            log.write(f"f{F.cons[0].frames} start {describe(F, record)}\n")
        target = next(r for r in records if u32(F, r + 0x950) == PRIEST)
        F.cons[0].write(target + 0x16C + 2 * PRIEST, struct.pack("<H", 1))
        F.cons[0].write(target + 0x910, bytes(9))
        log.write(f"f{F.cons[0].frames} poked {describe(F, target)}\n")

        for _ in range(120):
            if B.byte(F, B.BATTLE):
                break
            F.hold(0, ["Left"], 4)
        B.wait(F, "battle", lambda: B.byte(F, B.BATTLE) != 0, 300)
        for _ in range(8):
            B.attack_turn(F)
            B.wait(F, "end of round", lambda: B.round_over(F), 3000)
            if B.finished(F):
                break
        log.write(f"f{F.cons[0].frames} battle over {describe(F, target)}\n")
        os.makedirs(SHOTS, exist_ok=True)
        for n in range(60):
            if B.byte(F, B.BATTLE) == 0:
                break
            B.press(F, "A")
            F.run(40)
            shot(F, os.path.join(SHOTS, f"f{F.cons[0].frames}.png"))
            log.write(f"f{F.cons[0].frames} A {n} {describe(F, target)}\n")
        log.write(f"f{F.cons[0].frames} battle byte {B.byte(F, B.BATTLE)} phase {B.byte(F, B.PHASE)}\n")
        F.run(120)
        for record in records:
            log.write(f"f{F.cons[0].frames} end {describe(F, record)}\n")
