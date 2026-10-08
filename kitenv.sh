#!/bin/sh
# Resolve how to run python, and the kit's own paths. Source this, do not execute it.
#
#   . "$KIT/kitenv.sh"
#   "$PY" "$KIT/claim.py" 017 --peek 5
#
# WHY THIS EXISTS. Every kit script, and every doc in it, invokes `python`. That name exists on
# Windows and on a macOS with a python.org installer, and it is NOT on a stock Debian, Ubuntu or
# MX Linux: those ship `python3` and nothing named `python`, so `python x.py` fails with
# "command not found" before any of this project's logic runs. Fixing that by editing the 159
# call sites would be a huge diff to code that is otherwise correct, and would break every
# reader's muscle memory besides; `sudo apt install python-is-python3` fixes it at the system
# level but cannot be assumed on a machine you do not administer. So the new Unix scripts
# resolve it themselves, and `setup_unix.sh` offers the package as the tidier option.
#
# DQIX_PY overrides everything, for a venv, a pyenv shim or a wrapper of your own.
if [ -z "${PY:-}" ]; then
  if [ -n "${DQIX_PY:-}" ]; then
    PY="$DQIX_PY"
  elif command -v python >/dev/null 2>&1; then
    PY=python
  elif command -v python3 >/dev/null 2>&1; then
    PY=python3
  else
    echo "kitenv: no python and no python3 on PATH. Install one, or set DQIX_PY=/path/to/python." >&2
    return 1 2>/dev/null || exit 1
  fi
fi

# KIT is the checkout holding this file, without relying on `pwd -W` (a Git Bash extension that
# does not exist elsewhere) or on BASH_SOURCE (unset under `sh`).
_kitdir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd -P)
KIT="$_kitdir"
SP=$("$PY" "$KIT/kitpaths.py" state 2>/dev/null)
REPO=$("$PY" "$KIT/kitpaths.py" repo 2>/dev/null)
export KIT SP REPO PY