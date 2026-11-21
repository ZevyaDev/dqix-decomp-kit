import os
import struct
import kitpaths

START = {"save": "states/host.sav", "state": "states/inn.0.mst"}
OUT = os.path.join(kitpaths.SP, "names", "b10", "R2", "layout")
LAYOUT = 0x02352C70
STOP_FRAME = 700


def header(con):
    raw = bytes(con.read(LAYOUT, 0x18))
    groups, elements = struct.unpack_from("<II", raw, 8)
    group_count, element_count = struct.unpack_from("<HH", raw, 0x14)
    return groups, elements, group_count, element_count


def dump(con):
    groups, elements, group_count, element_count = header(con)
    lines = [f"{con.frames} layout={LAYOUT:08x} groups={groups:08x} x{group_count} elements={elements:08x} x{element_count}"]
    for i in range(group_count):
        gid, count, ids, x, y = struct.unpack("<hHIhh", bytes(con.read(groups + 0x18 * i, 0xC)))
        members = [struct.unpack("<h", bytes(con.read(ids + 2 * k, 2)))[0] for k in range(count)] if ids and count < 0x40 else []
        lines.append(f"group id={gid:#x} pos=({x},{y}) elements={[hex(m) for m in members]}")
    for i in range(element_count):
        eid, _, x, y = struct.unpack("<hhhh", bytes(con.read(elements + 0x14 * i, 8)))
        lines.append(f"element id={eid:#x} pos=({x},{y})")
    return lines


def play(F):
    con = F.cons[0]
    out = []
    seen = set()
    original = F.run

    def run(frames):
        for _ in range(frames):
            original(1)
            groups, elements, group_count, element_count = header(con)
            key = (groups, elements, group_count, element_count)
            if groups and elements and 0 < group_count < 0x100 and 0 < element_count < 0x400 and key not in seen:
                seen.add(key)
                out.extend(dump(con))
            if con.frames >= STOP_FRAME:
                raise StopIteration

    F.run = run
    try:
        F.run(30)
        for index in range(6):
            F.hold(0, ["X"], 4)
            F.run(40)
            for _ in range(index):
                F.hold(0, ["Down"], 3)
                F.run(15)
            F.hold(0, ["A"], 3)
            F.run(60)
            F.hold(0, ["A"], 3)
            F.run(60)
            for _ in range(5):
                F.hold(0, ["B"], 3)
                F.run(25)
    except StopIteration:
        pass
    finally:
        F.run = original
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "menu_layout.log"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
