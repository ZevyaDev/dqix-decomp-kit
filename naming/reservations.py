"""Naming keys other people hold: every key listed in an open kit issue or an open decomp pull request.

    python naming/reservations.py               every reserved key, its issue or pull request, its owner
    python naming/reservations.py take KEY...   reserve KEYs in your open "Naming:" kit issue (opened if none)
    python naming/reservations.py drop KEY...   release them from it

A listed function reserves its parameters and locals too. `rank.py` leaves out keys someone else holds,
`names.py import` refuses them, and `namesland.sh` refuses to land them.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kitpaths

KEY = re.compile(r"(?<![\w:])((?:func|data|inline|Struct|Enum|Type)_\w+(?:::\w+)?)")
TITLE = "Naming:"


def repo(url):
    return re.search(r"github\.com[:/]([^/]+/[^/.]+)", url).group(1)


def gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {r.stderr.strip()[:200]}")
    return r.stdout


def me():
    return gh("api", "user", "-q", ".login").strip()


def keys_in(text):
    return set(KEY.findall(text or ""))


def holders(items):
    out = {}
    for item in items:
        for key in keys_in(item["body"]):
            out.setdefault(key, (item["ref"], item["login"]))
    return out


def open_items():
    items = []
    for number, body, login in json.loads(gh("issue", "list", "-R", repo(kitpaths.KIT_URL), "--state", "open",
                                              "--limit", "500", "--json", "number,body,author",
                                              "-q", "[.[] | [.number, .body, .author.login]]")):
        items.append({"ref": f"kit#{number}", "body": body, "login": login})
    for number, body, login in json.loads(gh("pr", "list", "-R", repo(kitpaths.DECOMP_URL), "--state", "open",
                                              "--limit", "200", "--json", "number,body,author",
                                              "-q", "[.[] | [.number, .body, .author.login]]")):
        items.append({"ref": f"decomp#{number}", "body": body, "login": login})
    return items


def held(key, table):
    return table.get(key) or table.get(key.partition("::")[0])


def foreign(keys, table, login):
    out = {}
    for key in keys:
        owner = held(key, table)
        if owner and owner[1] != login:
            out[key] = owner
    return out


def taken_by_others(keys):
    return foreign(keys, holders(open_items()), me())


def my_issue(login):
    found = json.loads(gh("issue", "list", "-R", repo(kitpaths.KIT_URL), "--state", "open", "--author", login,
                          "--limit", "100", "--json", "number,title,body"))
    return next((i for i in found if i["title"].startswith(TITLE)), None)


def take(keys):
    login = me()
    clash = foreign(keys, holders(open_items()), login)
    for key, (ref, owner) in sorted(clash.items()):
        print(f"HELD {key}: {ref} ({owner})")
    if clash:
        return 1
    issue = my_issue(login)
    kit = repo(kitpaths.KIT_URL)
    if issue is None:
        body = "\n".join(sorted(keys))
        print(gh("issue", "create", "-R", kit, "--title", f"{TITLE} {len(keys)} keys", "--body", body).strip())
        return 0
    have = keys_in(issue["body"])
    new = sorted(set(keys) - have)
    if new:
        body = issue["body"].rstrip() + "\n\n" + "\n".join(new)
        gh("issue", "edit", str(issue["number"]), "-R", kit, "--body", body,
           "--title", f"{TITLE} {len(have) + len(new)} keys")
    print(f"kit#{issue['number']}: {len(new)} key(s) added, {len(have) + len(new)} held")
    return 0


def drop(keys):
    issue = my_issue(me())
    if issue is None:
        print("no open Naming: issue of yours")
        return 1
    body = issue["body"]
    for key in keys:
        body = re.sub(rf"(?<![\w:])`?{re.escape(key)}`?(?![\w:])[ \t]*", "", body)
    left = keys_in(body)
    gh("issue", "edit", str(issue["number"]), "-R", repo(kitpaths.KIT_URL), "--body", body.strip() or "(none)",
       "--title", f"{TITLE} {len(left)} keys")
    print(f"kit#{issue['number']}: {len(left)} held")
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        for key, (ref, login) in sorted(holders(open_items()).items()):
            print(f"{key}\t{ref}\t{login}")
        return 0
    if args[0] == "take" and args[1:]:
        return take(args[1:])
    if args[0] == "drop" and args[1:]:
        return drop(args[1:])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
