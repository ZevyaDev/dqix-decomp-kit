import os

import kitpaths

START = {"save": "D:/Downloads/dqvc/work/saves/github_playinful_dq9-tools/066 - Lt. Hootingham-Gore.sav",
         "state": os.path.join(kitpaths.SP, "names", "b8", "R3", os.environ.get("B10M6_STATE", "q66c.mst"))}
PHASE = 0x02114E05


def play(F):
    for _ in range(40):
        if F.cons[0].read(PHASE, 1)[0] == 0x22:
            break
        F.hold(0, ["A"], 4)
        F.run(86)
    F.run(400)
