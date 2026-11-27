import importlib.util
import os

import kitpaths

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


E = load("event")
START = E.START
MUSIC_MANAGER = 0x02109BF4
LOG = os.path.join(kitpaths.SP, "names", "b11", "M7", "event_music.log")


def play(F):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    sound = load("C_sound")
    con = F.cons[0]
    log = open(LOG, "w", encoding="utf-8")
    last = [None]

    def note():
        raw = con.read(MUSIC_MANAGER + 0xB0, 0x20)
        state = (raw[0], int.from_bytes(raw[8:10], "little", signed=True), int.from_bytes(raw[0xC:0x10], "little"),
                 int.from_bytes(raw[0x10:0x14], "little"))
        if state != last[0]:
            last[0] = state
            log.write(f"f{con.frames} musicState {state[0]} musicIndex {state[1]} +0xbc {state[2]:#x} +0xc0 {state[3]:#x}\n")

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
        with sound.channel_log(F, "b11M7_event"):
            E.play(F)
    finally:
        log.close()
