import importlib.util
import os
import struct

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("b10M2_battle_base", os.path.join(HERE, "battle.py"))
battle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(battle)

START = battle.START
CAMERA_SLOT = 0x020F33D8 + 0x3B0
SPRITE_TEXT_SLOT = 0x02105244
SUB_OBJ_PALETTE = 0x05000600
LOG = os.path.join(kitpaths.SP, "names", "b10", "M2", "battlewatch.log")


def snapshot(con):
    camera = struct.unpack("<I", con.read(CAMERA_SLOT, 4))[0]
    orbit = shake = None
    if camera:
        orbit = struct.unpack("<3i", con.read(camera + 0x70, 12))
        shake = struct.unpack("<2i", con.read(camera + 0x1E4, 8))
    manager = struct.unpack("<I", con.read(SPRITE_TEXT_SLOT, 4))[0]
    screen = offset = None
    if manager:
        screen, _, offset = struct.unpack("<3i", con.read(manager + 0x504, 12))
    palettes = con.read(SUB_OBJ_PALETTE, 0xE0).hex()
    return camera, orbit, shake, manager, screen, offset, palettes


def play(F):
    con = F.cons[0]
    lines, last = [], [None]
    base_run = F.run

    def run(frames):
        for _ in range(frames):
            base_run(1)
            now = snapshot(con)
            if now != last[0]:
                camera, orbit, shake, manager, screen, offset, palettes = now
                orbit_text = "-" if orbit is None else " ".join(f"{v:#x}" for v in orbit)
                shake_text = "-" if shake is None else " ".join(f"{v:#x}" for v in shake)
                lines.append(f"f{con.frames} camera={camera:#010x} orbit70={orbit_text} shake1e4={shake_text} "
                             f"spriteText={manager:#010x} screen504={screen} offset50c={offset} subObjPal={palettes}")
                last[0] = now
        return True

    F.run = run
    try:
        battle.play(F)
    finally:
        F.run = base_run
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
