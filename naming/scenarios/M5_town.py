import importlib.util
import os

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(kitpaths.SP, "names", "b7", "M5")
START = {"save": "saves/dq9ds_kheg_aug30.sav"}

PALETTE_ALLOCATOR = 0x0210CF88
MAC_ADDRESS = 0x027FFCF4
INPUT_LOCK = 0x02153628
DISPCNT = (0x04000000, 0x04001000)

SPECS = {
    0x020BB780: ("func_020bb780", [("allocator", PALETTE_ALLOCATOR, 12)], None),
    0x020BC078: ("func_020bc078", [], 4),
    0x020C555C: ("func_020c555c", [("edge", 0x04000330, 16)], 16),
    0x020C99AC: ("func_020c99ac", [("mac", MAC_ADDRESS, 6)], 6),
    0x020CF0FC: ("func_020cf0fc", [], 16),
    0x020E1154: ("func_020e1154", [("lock", INPUT_LOCK, 12)], None),
    0x020E2CC4: ("func_020e2cc4", [], 12),
    0x020E526C: ("func_020e526c", [], 4),
    0x020E2D24: ("func_020e2d24", [], 12),
}


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe_of(F):
    for cell in type(F).run.__closure__ or ():
        if type(cell.cell_contents).__name__ == "Probe":
            return cell.cell_contents
    return None


def in_ram(addr):
    return 0x02000000 <= addr < 0x02800000


def watch(F, log_name, play, poll_lock=False, only=None):
    con = F.cons[0]
    probe = probe_of(F)
    forward = probe.hit
    specs = {a: s for a, s in SPECS.items() if only is None or s[0] in only}
    points = [con.add_breakpoint(addr) for addr in specs]
    returns = {}
    out = []
    last = [None]

    def display(r0):
        screen = con.read(r0 + 1, 1)[0] & 1
        return int.from_bytes(con.read(DISPCNT[screen], 4), "little")

    def hit(brk):
        pc = brk.pc & ~1
        regs = con.regs()
        key = (con.frames, pc, regs["sp"], regs["lr"])
        if key == last[0]:
            return
        last[0] = key
        if pc in specs:
            name, fixed, size = specs[pc]
            line = (f"{con.frames} {name} enter lr={regs['lr']:#x} r0={regs['r0']:#x} r1={regs['r1']:#x} "
                    f"r2={regs['r2']:#x} r3={regs['r3']:#x}")
            if size and in_ram(regs["r0"]):
                line += f" [r0]={con.read(regs['r0'], size).hex()}"
            if name == "func_020e2cc4":
                line += f" dispcnt={display(regs['r0']):#010x}"
            out.append(line)
            lr = regs["lr"] & ~1
            if lr not in returns:
                returns[lr] = [con.add_breakpoint(lr), []]
            returns[lr][1].append((regs["sp"], name, regs["r0"], fixed, size))
        if pc in returns:
            pending = returns[pc][1]
            for i, (sp, name, r0, fixed, size) in enumerate(pending):
                if sp == regs["sp"]:
                    line = f"{con.frames} {name} return r0={regs['r0']:#x}"
                    if size and in_ram(r0):
                        line += f" [entry r0]={con.read(r0, size).hex()}"
                    for label, addr, n in fixed:
                        line += f" {label}={con.read(addr, n).hex()}"
                    if name == "func_020e2cc4":
                        line += f" dispcnt={display(r0):#010x}"
                    out.append(line)
                    del pending[i]
                    break
            if not pending:
                con.remove_point(returns.pop(pc)[0])
        forward(brk)

    probe.hit = hit
    original_run = F.run
    state = {"lock": None}

    def polled(frames):
        result = None
        while frames > 0:
            step = min(frames, 2)
            result = original_run(step)
            frames -= step
            word = int.from_bytes(con.read(INPUT_LOCK, 4), "little")
            if word != state["lock"]:
                out.append(f"{con.frames} poll input_lock_word0={word:#x}")
                state["lock"] = word
        return result

    if poll_lock:
        F.run = polled
    try:
        play(F)
    finally:
        F.run = original_run
        probe.hit = forward
        for point in points:
            con.remove_point(point)
        for point, _ in returns.values():
            con.remove_point(point)
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, log_name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")


def play(F):
    town = load("town")
    watch(F, "M5_town.log", town.play)
