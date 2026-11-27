import importlib.util
import os
import struct

import kitpaths

_spec = importlib.util.spec_from_file_location("faint", os.path.join(os.path.dirname(__file__), "faint.py"))
FAINT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FAINT)

START = FAINT.START
CLEAR = 0x020D7334
SET = 0x020D6F9C
SHOWN = 0xA24
LOG = os.path.join(kitpaths.SP, "names", "b11", "M9", "faintmask")


def play(F):
    con = F.cons[0]
    run = 1
    while os.path.exists(f"{LOG}.{run}.log"):
        run += 1
    log = open(f"{LOG}.{run}.log", "w", encoding="utf-8", newline="\n")
    take = con.take_break

    def take_break():
        brk = take()
        if brk is not None and (brk.pc & ~1) in (CLEAR, SET):
            regs = con.regs()
            slots, index = regs["r0"], regs["r1"]
            bit = index - 0xBC if index >= 0xC0 else index
            shown = struct.unpack("<H", con.read(slots + SHOWN, 2))[0]
            name = "clear" if (brk.pc & ~1) == CLEAR else f"set r2={regs['r2']}"
            state = "on" if shown >> bit & 1 else "off"
            log.write(f"f{con.frames} {name} lr={regs['lr'] & ~1:#010x} r0={slots:#x} r1={index:#x} "
                      f"+0xa24={shown:#06x} bit{bit}={state}\n")
            log.flush()
        return brk

    con.take_break = take_break
    try:
        FAINT.play(F)
    finally:
        con.take_break = take
        log.close()
