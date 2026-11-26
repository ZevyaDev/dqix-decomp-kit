import re
import struct
import time

from melonds_mcp.native import run_group

POS_ADDR = 0x0210A134
DIALOG_RANGE = (0x02116000, 0x6000)


class Field:
    def __init__(self, consoles, live=False):
        self.cons = consoles
        self.live = live

    def run(self, frames):
        if self.live:
            time.sleep(frames / 60)
            return False, [1] * len(self.cons)
        return run_group(self.cons, frames, 120000)

    def hold(self, i, keys, frames):
        self.cons[i].set_keys(keys)
        if not self.live:
            for j, c in enumerate(self.cons):
                if j != i:
                    c.set_keys([])
        self.run(frames)
        self.cons[i].set_keys([])

    def pos3(self, i):
        return tuple(v / 4096 for v in struct.unpack("<3i", self.cons[i].read(POS_ADDR, 12)))

    def pos(self, i):
        x, _, z = self.pos3(i)
        return x, z

    def move_to(self, i, tx=None, tz=None, tol=0.35, max_steps=80):
        stuck = 0
        for _ in range(max_steps):
            x, z = self.pos(i)
            keys = []
            if tx is not None and abs(x - tx) > tol:
                keys.append("Right" if x < tx else "Left")
            if tz is not None and abs(z - tz) > tol:
                keys.append("Down" if z < tz else "Up")
            if not keys:
                break
            self.hold(i, keys, 3)
            nx, nz = self.pos(i)
            stuck = stuck + 1 if abs(nx - x) + abs(nz - z) < 0.05 else 0
            if stuck >= 3:
                break
        self.run(4)
        return self.pos(i)

    def align(self, i, tx=None, tz=None, tol=0.1, max_taps=30):
        for _ in range(max_taps):
            x, z = self.pos(i)
            if tx is not None and abs(x - tx) > tol:
                self.hold(i, ["Right" if x < tx else "Left"], 1)
            elif tz is not None and abs(z - tz) > tol:
                self.hold(i, ["Down" if z < tz else "Up"], 1)
            else:
                break
            self.run(2)
        return self.pos(i)

    def walk(self, i, keys, until=lambda p: False, max_steps=60):
        last, stuck = self.pos(i), 0
        for _ in range(max_steps):
            if until(self.pos(i)):
                break
            self.hold(i, keys, 6)
            p = self.pos(i)
            stuck = stuck + 1 if abs(p[0] - last[0]) + abs(p[1] - last[1]) < 0.2 else 0
            if stuck >= 2:
                break
            last = p
        self.run(4)
        return self.pos(i)

    def speakers_since(self, i, before):
        after = self.cons[i].read(*DIALOG_RANGE)
        names = set()
        for m in re.finditer(rb"//([A-Za-z ]+)//", after):
            s, e = m.span()
            if after[s:e + 20] != before[s:e + 20]:
                names.add(m.group(1).decode())
        return sorted(names)

    def talk(self, i, face=None, close=True):
        if face:
            self.hold(i, [face], 2)
            self.run(4)
        before = self.cons[i].read(*DIALOG_RANGE)
        self.hold(i, ["A"], 3)
        self.run(45)
        names = self.speakers_since(i, before)
        if close:
            self.close(i)
        return names

    def free(self, i):
        x, z = self.pos(i)
        self.hold(i, ["Down"], 4)
        self.run(2)
        moved = abs(self.pos(i)[1] - z) > 0.05
        if moved:
            self.hold(i, ["Up"], 4)
            self.run(2)
        return moved

    def close(self, i, presses=8):
        for _ in range(presses):
            if self.free(i):
                return True
            self.hold(i, ["B"], 3)
            self.run(40)
        return self.free(i)

    def script(self, i, speaker):
        raw = self.cons[i].read(0x02000000, 0x400000)
        seen, out = set(), []
        for m in re.finditer(rb"//" + speaker.encode() + rb"//[^\x00]{0,400}", raw):
            s = m.group().decode("latin-1")
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def go_npc(self, i, spot):
        x, z = spot["stand"]
        self.move_to(i, tz=z + 1.2)
        self.move_to(i, tx=x)
        self.move_to(i, tz=z)
        return self.talk(i, spot["face"], close=False)
