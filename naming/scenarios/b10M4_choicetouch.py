import os
import struct

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "M4", "choicetouch")
CHOICE_LIST = 0x02115384
TOUCH_CURSOR = CHOICE_LIST + 0x20
ENTRY = 1


def is_choice_list_open(F):
    data = F.cons[0].read(CHOICE_LIST, 0x240)
    frame_state = int.from_bytes(data[0xbc:0xc0], "little")
    return data[0x233] == 1 and frame_state == 2


def shot(F, log, name):
    from PIL import Image
    c = F.cons[0]
    px = bytes(c.screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(
        os.path.join(OUT, f"f{c.frames}_{name}.png"))
    log.write(f"f{c.frames} {name} cursor {cursor_state(F)}\n")


def cursor_state(F):
    c = F.cons[0]
    touched, = struct.unpack("<i", c.read(TOUCH_CURSOR + 0x30, 4))
    again, pressed = c.read(TOUCH_CURSOR + 0x4c, 1)[0], c.read(TOUCH_CURSOR + 0x4e, 1)[0]
    return f"touched {touched} again {again} pressed {pressed}"


def entry_point(F, log, index):
    c = F.cons[0]
    count, = struct.unpack("<i", c.read(TOUCH_CURSOR + 0x34, 4))
    ox, oy = struct.unpack("<hh", c.read(TOUCH_CURSOR + 0x38, 4))
    px, py, pw, ph = struct.unpack("<IIII", c.read(TOUCH_CURSOR + 0x3c, 16))
    x, = struct.unpack("<h", c.read(px + 2 * index, 2))
    y, = struct.unpack("<h", c.read(py + 2 * index, 2))
    w, = struct.unpack("<h", c.read(pw + 2 * index, 2))
    h, = struct.unpack("<h", c.read(ph + 2 * index, 2))
    log.write(f"f{c.frames} rects count {count} origin ({ox}, {oy}) entry {index} x {x} y {y} w {w} h {h}\n")
    return ox + x + w // 2, oy + y + h // 2


def tap(F, log, point, name):
    c = F.cons[0]
    c.touch(*point)
    F.run(4)
    c.touch()
    F.run(2)
    log.write(f"f{c.frames} tapped {point} {cursor_state(F)}\n")
    F.run(30)
    shot(F, log, name)


def play(F):
    import dqix_flows
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "choicetouch.log"), "w", encoding="utf-8") as log:
        F.run(30)
        F.go_npc(0, dqix_flows.NPC["Erinn"])
        F.run(90)
        dqix_flows.advance(F, 0, 1)
        dqix_flows.menu_pick(F, 0, 1)
        F.hold(0, ["Down"], 3)
        F.run(20)
        F.hold(0, ["A"], 3)
        for _ in range(80):
            if is_choice_list_open(F):
                break
            F.run(5)
        F.run(60)
        shot(F, log, "open")
        point = entry_point(F, log, ENTRY)
        tap(F, log, point, "tap1")
        tap(F, log, point, "tap2")
        F.run(120)
        shot(F, log, "after")
        for _ in range(4):
            F.hold(0, ["B"], 3)
            F.run(60)
        F.close(0)
        F.run(60)
