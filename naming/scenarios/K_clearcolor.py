import os

import kitpaths

START = {"save": "saves/dq9ds_kheg_aug30.sav"}
TARGET = 0x020C5588
WHITE = 0x7FFF
RED = 0x001F


def probe_of(F):
    for cell in type(F).run.__closure__ or ():
        if type(cell.cell_contents).__name__ == "Probe":
            return cell.cell_contents
    return None


def shot(F, path):
    from PIL import Image
    px = bytes(F.cons[0].screen())
    Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)


def play(F):
    con = F.cons[0]
    folder = os.path.join(kitpaths.SP, "names", "b3", "K")
    out = []
    point = con.add_breakpoint(TARGET, cpu=9)
    probe = probe_of(F)
    forward = probe.hit

    def hit(brk):
        if brk.id != point:
            forward(brk)
            return
        regs = con.regs()
        line = f"{con.frames} r0={regs['r0']:#x} r1={regs['r1']:#x} r2={regs['r2']:#x} r3={regs['r3']:#x}"
        if regs["r0"] == WHITE:
            con.set_reg("r0", RED)
            line += f" -> r0 set to {RED:#x}"
        out.append(line)

    probe.hit = hit
    try:
        F.run(163)
        shot(F, os.path.join(folder, "clear_red_163.png"))
        out.append(f"{con.frames} shot clear_red_163.png")
    finally:
        probe.hit = forward
        con.remove_point(point)
        with open(os.path.join(folder, "clearcolor.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
