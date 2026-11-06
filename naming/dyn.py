"""Dynamic evidence for the naming pass: play a scenario in headless melonDS and count the calls into
every function.

    python naming/dyn.py run <scenario>...           writes $SP/names/dyn/<scenario>.json
    python naming/dyn.py list
    python naming/dyn.py only <scenario> <other>...  functions the first scenario calls and the others do not

A scenario is naming/scenarios/<name>.py: START = {"save": <.sav>, "state": <.mst>} (paths relative to
$DQIX_PLAY; state optional) and play(F), driving the console through dqix_auto.Field. A .sav is copied
first, since the game writes it. Call counts are taken after every 60 frames, with the overlays loaded
at that moment, so an overlay function is credited to the overlay that held it.
Environment: DQIX_PLAY (default ../dqix-play), DQIX_MELONDS_MCP (default ../melonDS/tools/melonds-mcp).
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import kitpaths
from graph import Graph

ROOT = os.path.dirname(kitpaths.KIT)
PLAY = os.environ.get("DQIX_PLAY") or os.path.join(ROOT, "dqix-play")
MCP = os.environ.get("DQIX_MELONDS_MCP") or os.path.join(ROOT, "melonDS", "tools", "melonds-mcp")
OUT = os.path.join(kitpaths.SP, "names", "dyn")
CHUNK = 60


def scenario(name):
    path = os.path.join(HERE, "scenarios", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"scenario_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Recorder:
    def __init__(self, con, graph, table):
        self.con, self.g, self.table = con, graph, table
        self.calls, self.unmapped, self.frames = {}, {}, 0

    def starts(self, modules, entry):
        found = []
        for module in modules:
            if module in self.g.tables:
                sym = self.g.owner(module, entry)
                if sym and sym.addr == entry:
                    found.append(sym)
        return found

    def function(self, entry, loaded):
        for group in (["main", "itcm", "dtcm"], [f"ov{i:03d}" for i in loaded]):
            found = self.starts(group, entry)
            if found:
                return found[0]
        found = self.starts([m for m in self.g.tables if m.startswith("ov")], entry)
        return found[0] if len(found) == 1 else None

    def sample(self):
        counts = self.con.take_call_counts(9)
        loaded = self.table.loaded_overlays(self.con)
        for entry, hits in counts.items():
            sym = self.function(entry & ~1, loaded)
            if sym is None:
                self.unmapped[entry] = self.unmapped.get(entry, 0) + hits
                continue
            key = f"{sym.module}:{sym.addr:08x}"
            self.calls[key] = self.calls.get(key, 0) + hits


def run(name):
    sys.path.insert(0, MCP)
    sys.path.insert(0, PLAY)
    from melonds_mcp.native import Console
    from melonds_mcp.symbols import SymbolTable
    import dqix_auto

    sc = scenario(name)
    g = Graph("usa")
    table = SymbolTable()
    table.load(os.path.join(kitpaths.REPO, "config", "usa", "arm9", "config.yaml"))
    rom = os.path.join(kitpaths.REPO, "extract", "baserom_dqix_usa.nds")
    work = tempfile.mkdtemp(prefix="dyn_")
    con = Console(nickname="Naming")
    try:
        save = os.path.join(work, "game.sav")
        shutil.copyfile(os.path.join(PLAY, sc.START["save"]), save)
        con.load_rom(rom, save=save)
        if sc.START.get("state"):
            con.load_state(os.path.join(PLAY, sc.START["state"]))
        con.track_calls(True)
        rec = Recorder(con, g, table)

        class Field(dqix_auto.Field):
            def run(self, frames):
                result = (True, [])
                while frames > 0:
                    step = min(frames, CHUNK)
                    result = super().run(step)
                    frames -= step
                    rec.frames += step
                    rec.sample()
                return result

        started = time.time()
        sc.play(Field([con]))
        rec.sample()
    finally:
        con.close()
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    lost = sorted(rec.unmapped.items(), key=lambda x: -x[1])
    data = {"scenario": name, "frames": rec.frames, "unmapped": {f"{a:08x}": n for a, n in lost[:40]},
            "functions": {k: {"calls": v} for k, v in sorted(rec.calls.items())}}
    with open(os.path.join(OUT, f"{name}.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=0)
    print(f"{name}: {len(rec.calls)} functions, {rec.frames} frames, {sum(rec.unmapped.values())} unmapped calls, "
          f"{time.time() - started:.0f}s")


def load(name):
    with open(os.path.join(OUT, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "run" and len(args) > 1:
        for name in args[1:]:
            run(name)
    elif args[0] == "list":
        for f in sorted(os.listdir(os.path.join(HERE, "scenarios"))):
            if f.endswith(".py"):
                name = f[:-3]
                done = os.path.isfile(os.path.join(OUT, f"{name}.json"))
                print(f"{name}{'' if done else '  (not run)'}")
    elif args[0] == "only" and len(args) > 2:
        g = Graph("usa")
        mine = load(args[1])["functions"]
        others = set().union(*(load(n)["functions"] for n in args[2:]))
        for key in sorted(set(mine) - others, key=lambda k: -mine[k]["calls"]):
            module, addr = key.split(":")
            sym = g.by_key.get((module, int(addr, 16)))
            print(f"{mine[key]['calls']:8} {sym.name if sym else key}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
