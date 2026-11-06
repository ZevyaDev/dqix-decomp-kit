"""Dynamic evidence for the naming pass: play a scenario in headless melonDS and count the calls into
every function.

    python naming/dyn.py run <scenario>...           writes $SP/names/dyn/<scenario>.json
    python naming/dyn.py list
    python naming/dyn.py only <scenario> <other>...  functions the first scenario calls and the others do not
    python naming/dyn.py probe <scenario> <key>... [--hits N]
                                                     each function's arguments, caller chain, return value,
                                                     pointed-to memory and screenshots while the scenario plays
    python naming/dyn.py show <key> [scenario]       print what probes recorded

A probe samples a function in bursts of BURST hits at least GAP frames apart, up to --hits (default
HITS), so the samples spread over the whole scenario. It writes
$SP/names/dyn/probe/<scenario>/<module>_<addr>.json and PNGs of both screens beside it, one at the
hit and one AFTER frames later (`_<n>after.png`); `dossier.py` shows them. Several probes may run at once, each in its own process.

A scenario is naming/scenarios/<name>.py: START = {"save": <.sav>, "state": <.mst>} (paths relative to
$DQIX_PLAY; state optional) and play(F), driving the console through dqix_auto.Field. A .sav is copied
first, since the game writes it. Call counts are taken after every 60 frames, with the overlays loaded
at that moment, so an overlay function is credited to the overlay that held it.
Environment: DQIX_PLAY (default ../dqix-play), DQIX_MELONDS_MCP (default ../melonDS/tools/melonds-mcp).
"""
import glob
import importlib.util
import json
import os
import shutil
import struct
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
PROBES = os.path.join(OUT, "probe")
CHUNK = 60
HITS = 40
BURST = 4
GAP = 240
SHOT_EVERY = 10
AFTER = 120
MAX_RETURN_MISSES = 4000
RAM = (0x02000000, 0x02400000)


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


def peek(con, table, value):
    if not RAM[0] <= value < RAM[1]:
        return None
    raw = con.read(value, 32)
    text = raw.split(b"\0", 1)[0]
    out = {"hex": raw.hex(), "sym": table.describe(value, con)}
    if len(text) >= 4 and all(32 <= b < 127 or b in (9, 10) for b in text):
        out["text"] = text.decode("ascii")
    return out


class Probe:
    def __init__(self, con, rec, keys, hits, name):
        self.con, self.rec, self.hits = con, rec, hits
        self.dir = os.path.join(PROBES, name)
        self.watch, self.data, self.points = {}, {}, {}
        self.returns, self.return_points, self.misses = {}, {}, {}
        self.later = []
        for key in keys:
            sym = rec.g.lookup(key)
            if sym is None or sym.kind != "func":
                sys.exit(f"{key}: no such function")
            self.watch.setdefault(sym.addr, []).append(sym)
            self.data[sym.key] = {"scenario": name, "function": sym.name, "module": sym.module,
                                  "addr": f"{sym.addr:08x}", "sites": {}, "rows": [], "shots": [],
                                  "burst": 0, "resume": 0}
        for addr in self.watch:
            self.points[addr] = con.add_breakpoint(addr)

    def tick(self):
        due = [x for x in self.later if self.con.frames >= x[2]]
        for sym, n, _ in due:
            self.data[sym.key]["shots"].append(self.shot(sym, f"{n}after"))
        self.later = [x for x in self.later if x not in due]
        for addr, syms in self.watch.items():
            if any(self.ready(self.data[s.key]) for s in syms):
                self.con.enable_point(self.points[addr], True)

    def ready(self, d):
        return len(d["rows"]) < self.hits and self.con.frames >= d["resume"]

    def hit(self, brk):
        pc = brk.pc & ~1
        regs = self.con.regs()
        if pc in self.returns:
            self.returned(pc, regs)
        if pc not in self.watch:
            return
        sym = self.rec.function(pc, self.rec.table.loaded_overlays(self.con))
        if sym is None or sym.key not in self.data:
            return
        d = self.data[sym.key]
        stack = self.con.callstack(9) or []
        chain = [self.rec.table.describe(f["site"], self.con) for f in stack[:5]]
        if chain:
            d["sites"][chain[0]] = d["sites"].get(chain[0], 0) + 1
        if not self.ready(d):
            if all(not self.ready(self.data[s.key]) for s in self.watch[pc]):
                self.con.enable_point(self.points[pc], False)
            return
        args = [regs[f"r{i}"] for i in range(4)]
        row = {"frame": self.con.frames, "callers": chain, "args": args,
               "stack": list(struct.unpack("<4I", self.con.read(regs["sp"], 16))),
               "mem": {f"r{i}": m for i, a in enumerate(args) if (m := peek(self.con, self.rec.table, a))}}
        d["rows"].append(row)
        d["burst"] += 1
        if len(d["rows"]) % SHOT_EVERY == 1:
            d["shots"].append(self.shot(sym, len(d["rows"])))
            self.later.append((sym, len(d["rows"]), self.con.frames + AFTER))
        if d["burst"] >= BURST:
            d["burst"], d["resume"] = 0, self.con.frames + GAP
        lr = regs["lr"] & ~1
        self.returns.setdefault(lr, []).append((regs["sp"], row))
        if lr not in self.return_points:
            self.return_points[lr] = self.con.add_breakpoint(lr)
            self.misses[lr] = 0

    def returned(self, pc, regs):
        pending = self.returns[pc]
        for i, (sp, row) in enumerate(pending):
            if sp == regs["sp"]:
                row["ret"] = regs["r0"]
                if m := peek(self.con, self.rec.table, regs["r0"]):
                    row["mem"]["ret"] = m
                del pending[i]
                break
        else:
            self.misses[pc] += 1
        if not pending or self.misses[pc] > MAX_RETURN_MISSES:
            self.con.remove_point(self.return_points.pop(pc))
            del self.returns[pc]

    def shot(self, sym, n):
        from PIL import Image
        os.makedirs(self.dir, exist_ok=True)
        path = os.path.join(self.dir, f"{sym.module}_{sym.addr:08x}_{n}.png")
        px = bytes(self.con.screen())
        Image.frombuffer("RGBA", (256, 384), px, "raw", "BGRA", 0, 1).convert("RGB").save(path)
        return path

    def save(self):
        os.makedirs(self.dir, exist_ok=True)
        for (module, addr), d in self.data.items():
            d["calls"] = self.rec.calls.get(f"{module}:{addr:08x}", 0)
            for k in ("burst", "resume"):
                d.pop(k)
            with open(os.path.join(self.dir, f"{module}_{addr:08x}.json"), "w", encoding="utf-8", newline="\n") as fh:
                json.dump(d, fh, indent=0)
            print(f"{d['function']}: {len(d['rows'])} sampled of {d['calls']} calls, "
                  f"{len(d['sites'])} call sites, {len(d['shots'])} shots")


def run(name, keys=(), hits=HITS):
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
        probe = Probe(con, rec, keys, hits, name) if keys else None

        class Field(dqix_auto.Field):
            def run(self, frames):
                result = (True, [])
                while frames > 0:
                    step = min(frames, CHUNK)
                    end = con.frames + step
                    result = super().run(step)
                    while probe and (brk := con.take_break()):
                        probe.hit(brk)
                        if con.frames >= end:
                            break
                        result = super().run(end - con.frames)
                    frames -= step
                    rec.frames += step
                    rec.sample()
                    if probe:
                        probe.tick()
                return result

        started = time.time()
        sc.play(Field([con]))
        rec.sample()
    finally:
        con.close()
        shutil.rmtree(work, ignore_errors=True)
    if probe:
        probe.save()
        print(f"{name}: probe {rec.frames} frames, {time.time() - started:.0f}s")
        return
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


def probes(sym, scenario_name="*"):
    pattern = os.path.join(PROBES, scenario_name, f"{sym.module}_{sym.addr:08x}.json")
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            yield json.load(fh)


def describe(value, mem):
    if mem is None:
        return f"{value:x}"
    if "text" in mem:
        return f'{value:x}="{mem["text"][:40]}"'
    return f"{value:x}({mem['sym']})" if not mem["sym"].startswith(f"{value:08x}") else f"{value:x}"


def probe_lines(sym, scenario_name="*", rows=6):
    out = []
    for d in probes(sym, scenario_name):
        sites = sorted(d["sites"].items(), key=lambda x: -x[1])
        out.append(f"{d['scenario']} probe: {len(d['rows'])} sampled of {d['calls']} calls; "
                   f"call sites {', '.join(f'{s} x{n}' for s, n in sites[:6])}"
                   + (f" (+{len(sites) - 6})" if len(sites) > 6 else ""))
        step = max(1, len(d["rows"]) // rows)
        for row in d["rows"][::step][:rows]:
            mem = row.get("mem", {})
            args = " ".join(describe(a, mem.get(f"r{i}")) for i, a in enumerate(row["args"]))
            ret = f" -> {describe(row['ret'], mem.get('ret'))}" if "ret" in row else ""
            out.append(f"  f{row['frame']} {' < '.join(row['callers'][:3])}: {args}{ret}")
        if d["shots"]:
            out.append("  shots " + " ".join(d["shots"]))
    return out


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "run" and len(args) > 1:
        for name in args[1:]:
            run(name)
    elif args[0] == "probe" and len(args) > 2:
        hits = HITS
        if "--hits" in args:
            i = args.index("--hits")
            hits = int(args[i + 1])
            del args[i:i + 2]
        run(args[1], args[2:], hits)
    elif args[0] == "show" and len(args) > 1:
        sym = Graph("usa").lookup(args[1])
        if sym is None:
            sys.exit(f"{args[1]}: no such symbol")
        print("\n".join(probe_lines(sym, args[2] if len(args) > 2 else "*", rows=40)) or "no probe")
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
