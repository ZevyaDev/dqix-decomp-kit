import importlib.util
import os

import kitpaths

_spec = importlib.util.spec_from_file_location("confess", os.path.join(os.path.dirname(__file__), "C6_confess.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

START = C.START
MUSIC_MANAGER = 0x02109BF4
LOG = os.path.join(kitpaths.SP, "names", "b11", "M7", "confess_music.log")


def play(F):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    con = F.cons[0]
    log = open(LOG, "w", encoding="utf-8")
    last = [None]

    def note():
        raw = con.read(MUSIC_MANAGER + 0xB0, 0x20)
        state = (raw[0], raw[0x19], int.from_bytes(raw[0x1A:0x1C], "little"), int.from_bytes(raw[0x1E:0x20], "little", signed=True))
        if state != last[0]:
            last[0] = state
            log.write(f"f{con.frames} musicState {state[0]} jingleState {state[1]} +0xca {state[2]} jingleIndex {state[3]}\n")

    hold = F.hold
    run = F.run

    def held(*args, **kwargs):
        result = hold(*args, **kwargs)
        note()
        return result

    def stepped(frames, *args, **kwargs):
        while frames > 0:
            run(min(2, frames), *args, **kwargs)
            frames -= 2
            note()

    F.hold = held
    F.run = stepped
    try:
        C.play(F)
    finally:
        log.close()
