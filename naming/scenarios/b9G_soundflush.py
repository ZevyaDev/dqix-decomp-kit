import importlib.util
import os

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(kitpaths.SP, "names", "b9", "G")
START = {"save": "saves/dq9ds_kheg_aug30.sav"}

FLUSH = 0x020D24C4
STATE = 0x02112780
STATE_SIZE = 0x24
LIMIT = 200


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


def words(con):
    raw = bytes(con.read(STATE, STATE_SIZE))
    return " ".join(f"{int.from_bytes(raw[i:i + 4], 'little'):08x}" for i in range(0, STATE_SIZE, 4))


def watch(F, play, log_name):
    con = F.cons[0]
    probe = probe_of(F)
    forward = probe.hit
    entry = con.add_breakpoint(FLUSH)
    returns = {}
    out = []
    seen = [0]

    def hit(brk):
        pc = brk.pc & ~1
        regs = con.regs()
        if pc == FLUSH and seen[0] < LIMIT:
            seen[0] += 1
            out.append(f"{con.frames} enter lr={regs['lr']:#x} r0={regs['r0']:#x} state={words(con)}")
            lr = regs["lr"] & ~1
            if lr not in returns:
                returns[lr] = [con.add_breakpoint(lr), []]
            returns[lr][1].append(regs["sp"])
        if pc in returns:
            pending = returns[pc][1]
            if regs["sp"] in pending:
                pending.remove(regs["sp"])
                out.append(f"{con.frames} return r0={regs['r0']:#x} state={words(con)}")
            if not pending:
                con.remove_point(returns.pop(pc)[0])
        forward(brk)

    probe.hit = hit
    try:
        play(F)
    finally:
        probe.hit = forward
        con.remove_point(entry)
        for point, _ in returns.values():
            con.remove_point(point)
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, log_name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")


def play(F):
    watch(F, load("town").play, "b9G_soundflush.log")
