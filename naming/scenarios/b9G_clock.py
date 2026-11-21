import importlib.util
import os

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(kitpaths.SP, "names", "b9", "G")
SPECS = {0x020CF1A8: ("func_020cf1a8", 12), 0x020CF0FC: ("func_020cf0fc", 16)}


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load("N5b_dqvc")
START = BASE.START


def probe_of(F):
    for cell in type(F).run.__closure__ or ():
        if type(cell.cell_contents).__name__ == "Probe":
            return cell.cell_contents
    return None


def play(F):
    con = F.cons[0]
    probe = probe_of(F)
    forward = probe.hit
    points = [con.add_breakpoint(addr) for addr in SPECS]
    returns = {}
    out = []

    def hit(brk):
        pc = brk.pc & ~1
        regs = con.regs()
        if pc in SPECS:
            name, size = SPECS[pc]
            out.append(f"{con.frames} {name} enter lr={regs['lr']:#x} r0={regs['r0']:#x} "
                       f"[r0]={bytes(con.read(regs['r0'], size)).hex()}")
            lr = regs["lr"] & ~1
            if lr not in returns:
                returns[lr] = [con.add_breakpoint(lr), []]
            returns[lr][1].append((regs["sp"], name, regs["r0"], size))
        if pc in returns:
            pending = returns[pc][1]
            for i, (sp, name, r0, size) in enumerate(pending):
                if sp == regs["sp"]:
                    out.append(f"{con.frames} {name} return r0={regs['r0']:#x} "
                               f"[entry r0]={bytes(con.read(r0, size)).hex()}")
                    del pending[i]
                    break
            if not pending:
                con.remove_point(returns.pop(pc)[0])
        forward(brk)

    probe.hit = hit
    try:
        BASE.play(F)
    finally:
        probe.hit = forward
        for point in points:
            con.remove_point(point)
        for point, _ in returns.values():
            con.remove_point(point)
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "b9G_clock.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
