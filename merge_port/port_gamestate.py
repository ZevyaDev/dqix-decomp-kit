import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.dirname(_kpos.path.abspath(__file__))))
import kitpaths as _kp
import buildcfg
import collections
import os
import re
import subprocess
import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else _kp.REPO
os.chdir(REPO)

METHODS = {
    "GetCombatantUnchecked": "GetGameObjectByIndex",
    "GetCombatantWithFlag0x2": "GetMaybeWanderingMonsterByIndex",
    "GetCombatantAtField0x3ac": "GetProtagonist",
    "GetCombatantAtField0x397c": "GetUnknownGameObject",
    "GetCombatantWithFlag0x800": "GetPartyMemberByIndex",
    "GetCombatantWithFlag0x20": "GetMaybeFieldMonsterByIndex",
    "GetCombatantFromList": "GetCombatantByIndex",
    "GetField0x3b4Value": "GetEffectiveDeltaTime",
    "GetBattleTimerDelta": "GetTrueDeltaTime",
    "GetFieldAt0x3c0": "GetAnimationDeltaTime",
    "GetBattleScaleCount": "GetTickCount",
    "SetField0x3bcValue": "SetGameSpeed",
    "GetField0x3bcValue": "GetGameSpeed",
    "GetAccumulatedValue": "GetDayTimer",
    "SetActiveFlag": "SetDayTimerRunning",
    "GetSelectedTableIndex": "GetTimeOfDay",
    "GetTreasureMapLanguageData": "GetTreasureMapLanguageData",
    "SetTreasureMapLanguageDataPtr": "SetTreasureMapLanguageDataPtr",
    "GetGrottoStruct": "GetGrottoStruct",
}
INSTANCE = {"GetBattleStruct"}

MANGLED = re.compile(r"^_Z(\d+)(\w+)$")
head_syms = "".join(
    subprocess.run(["git", "show", "HEAD:" + root + "/symbols.txt"],
                   capture_output=True, text=True).stdout
    for root in buildcfg.config_roots())
for line in head_syms.splitlines():
    parts = line.split()
    if not parts:
        continue
    m = MANGLED.match(parts[0])
    if not m:
        continue
    plain = m.group(2)[:int(m.group(1))]
    if plain in METHODS:
        METHODS[parts[0]] = METHODS[plain]
    elif plain in INSTANCE:
        INSTANCE.add(parts[0])

NAMES = sorted(set(METHODS) | INSTANCE, key=len, reverse=True)
NAME_ALT = "|".join(map(re.escape, NAMES))

DECL = re.compile(
    r"^[ \t]*(?:(?:ARM|THUMB|extern|\"C\"|static|inline)\s+)*"
    r"(?P<ret>(?:(?:const|volatile|unsigned|signed|struct|class|enum)\s+)*"
    r"(?!return\b|else\b|case\b|goto\b|delete\b|new\b|throw\b|do\b)[A-Za-z_]\w*(?:\s*\*+\s*|\s+)(?:\*\s*)*)"
    r"(?P<name>" + NAME_ALT + r")\s*\((?P<params>[^()]*)\)\s*;[ \t]*(?://[^\r\n]*)?\r?\n",
    re.M)
FWD = re.compile(r"^[ \t]*(?:struct|class)\s+(?:BattleStruct|CombatantStruct)\s*;[ \t]*(?://[^\r\n]*)?\r?\n", re.M)
CALL = re.compile(r"(?<![\w.>:])(" + NAME_ALT + r")\s*\(")
SIMPLE = re.compile(r"^[A-Za-z_]\w*(?:::\w+)*(?:\(\))?(?:(?:->|\.)[A-Za-z_]\w*(?:\(\))?|\[[^\[\]]+\])*$")
TYPEISH = re.compile(r"^(?:const\s+)?(?:struct\s+|class\s+|unsigned\s+|signed\s+)*[A-Za-z_]\w*(?:\s*\*+\s*|\s+)[A-Za-z_]?\w*$")
BATTLELIST_INC = re.compile(r'^[ \t]*#\s*include\s*["<][^">]*Combat/Main/BattleList\.h[">][^\r\n]*', re.M)
ANY_INC = re.compile(r'^[ \t]*#\s*include\b[^\r\n]*', re.M)
OWN_MEMBER = re.compile(r"\b(?:currentStats|baseStats|combatantList)\s*(?:\[[^\]]*\])?\s*;")
GAMESTATE_INC = '#include "GameState/GameState.h"'

stats = collections.Counter()
decl_types = collections.Counter()
unhandled = []


def find_close(text, i):
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1


def split_args(inner):
    args, depth, cur = [], 0, []
    for ch in inner:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail or args:
        args.append(tail)
    return args


def rewrite_calls(text, path):
    pos = 0
    while True:
        m = CALL.search(text, pos)
        if not m:
            return text
        name = m.group(1)
        open_i = m.end() - 1
        close_i = find_close(text, open_i)
        if close_i < 0:
            unhandled.append("%s: unbalanced call to %s" % (path, name))
            pos = m.end()
            continue
        args = split_args(text[open_i + 1:close_i])
        if args == ["void"]:
            args = []
        if name in INSTANCE:
            if args:
                unhandled.append("%s: %s called with arguments" % (path, name))
                pos = m.end()
                continue
            new = "GameState::GetInstance()"
            stats["instance-call"] += 1
        else:
            if not args:
                unhandled.append("%s: %s called without a receiver" % (path, name))
                pos = m.end()
                continue
            recv = args[0]
            if TYPEISH.match(recv) and not SIMPLE.match(recv):
                unhandled.append("%s: %s(%s ...) looks like a declaration" % (path, name, recv))
                pos = m.end()
                continue
            if not SIMPLE.match(recv):
                recv = "(" + recv + ")"
            new = "%s->%s(%s)" % (recv, METHODS[name], ", ".join(args[1:]))
            stats["member-call"] += 1
        text = text[:m.start()] + new + text[close_i + 1:]
        pos = m.start()


def drop_decl(m):
    decl_types[(m.group("name"), " ".join(m.group("ret").split()))] += 1
    stats["prototype-deleted"] += 1
    return ""


def ensure_include(text):
    if GAMESTATE_INC in text or not re.search(r"\bGame(?:State|Object)\b", text):
        return text
    if BATTLELIST_INC.search(text):
        stats["include-replaced"] += 1
        return BATTLELIST_INC.sub(GAMESTATE_INC, text, count=1)
    stats["include-added"] += 1
    nl = "\r\n" if "\r\n" in text else "\n"
    incs = list(ANY_INC.finditer(text))
    if incs:
        at = incs[-1].end()
        return text[:at] + nl + GAMESTATE_INC + text[at:]
    once = re.search(r"^[ \t]*#\s*pragma\s+once[^\r\n]*", text, re.M)
    if once:
        return text[:once.end()] + nl + GAMESTATE_INC + text[once.end():]
    return GAMESTATE_INC + nl + text


def port(path):
    text = open(path, encoding="utf-8", errors="surrogateescape", newline="").read()
    orig = text
    if not re.search(r"BattleStruct|CombatantStruct|" + NAME_ALT, text):
        return False
    text = DECL.sub(drop_decl, text)
    n_fwd = len(FWD.findall(text))
    text = FWD.sub("", text)
    stats["forward-decl-deleted"] += n_fwd
    text = rewrite_calls(text, path)
    text = re.sub(r"\b(?:struct|class)\s+BattleStruct\b", "GameState", text)
    text = re.sub(r"\bBattleStruct\b", "GameState", text)
    text = re.sub(r"\b(?:struct|class)\s+CombatantStruct\b", "GameObject", text)
    text = re.sub(r"\bCombatantStruct\b", "GameObject", text)
    text = re.sub(r"(?<=[A-Z])12BattleStruct", "9GameState", text)
    text = re.sub(r"(?<=[A-Z])15CombatantStruct", "10GameObject", text)
    if not OWN_MEMBER.search(text):
        text = re.sub(r"->currentStats\b", "->currentStats_", text)
        text = re.sub(r"->baseStats\b", "->baseStats_", text)
        text = re.sub(r"->combatantList\b", "->objects_", text)
    text = ensure_include(text)
    if text != orig:
        open(path, "w", encoding="utf-8", errors="surrogateescape", newline="").write(text)
        return True
    return False


def port_symbols(path):
    text = open(path, encoding="utf-8", newline="").read()
    new = re.sub(r"(?<=[A-Z])12BattleStruct", "9GameState", text)
    new = re.sub(r"(?<=[A-Z])15CombatantStruct", "10GameObject", new)
    if new != text:
        open(path, "w", encoding="utf-8", newline="").write(new)
        stats["symbols-files"] += 1
        stats["symbols-renamed"] += sum(1 for a, b in zip(text.splitlines(), new.splitlines()) if a != b)


def main():
    changed = 0
    for top in ("src", "include"):
        for root, _, files in os.walk(top):
            for f in files:
                if f.endswith((".c", ".cpp", ".h", ".hpp")):
                    if port(os.path.join(root, f)):
                        changed += 1
    for root, _, files in os.walk("config/" + buildcfg.REGION):
        for f in files:
            if f == "symbols.txt":
                port_symbols(os.path.join(root, f))

    print("files changed: %d" % changed)
    for k, v in sorted(stats.items()):
        print("  %-22s %d" % (k, v))
    print("deleted prototypes by (name, declared return type):")
    for (name, ret), n in sorted(decl_types.items()):
        print("  %4d  %-45s %s" % (n, name, ret))
    print("unhandled: %d" % len(unhandled))
    for u in unhandled:
        print("  " + u)


if __name__ == "__main__":
    main()
