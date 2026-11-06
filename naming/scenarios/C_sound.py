import contextlib
import os

import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}


def log_path(name):
    folder = os.path.join(kitpaths.SP, "names", "dyn", "probe", name)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "channels.log")


def probe_of(F):
    for cell in type(F).run.__closure__ or ():
        if type(cell.cell_contents).__name__ == "Probe":
            return cell.cell_contents
    return None


@contextlib.contextmanager
def channel_log(F, name="C_sound"):
    con = F.cons[0]
    out = []
    points = {}
    for ch in range(16):
        points[con.add_watchpoint(0x04000404 + ch * 0x10, 4, write=True, cpu=7)] = ch
    probe = probe_of(F)
    forward = probe.hit

    def hit(brk):
        if brk.id in points:
            out.append(f"{con.frames} ch{points[brk.id]} sad={brk.value:08x}")
        else:
            forward(brk)

    probe.hit = hit
    try:
        yield out
    finally:
        probe.hit = forward
        for point in points:
            con.remove_point(point)
        with open(log_path(name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")


def play(F):
    con = F.cons[0]
    steps = [("idle", [], 30), ("X", ["X"], 60), ("Down", ["Down"], 40), ("Down", ["Down"], 40),
             ("A", ["A"], 60), ("B", ["B"], 40), ("B", ["B"], 40)]
    with channel_log(F) as out:
        for label, keys, frames in steps:
            out.append(f"{con.frames} press {label}")
            F.hold(0, keys, 4) if keys else F.run(4)
            F.run(frames - 4)
