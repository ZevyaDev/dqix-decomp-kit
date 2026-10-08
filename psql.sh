#!/bin/bash
# How many DQIX jobs are actually alive. Prints a count, or `--list` for pid + command line.
#
#   bash psq.sh                # count of integration/sweep/worker processes
#   bash psq.sh --list         # one line each
#   bash psq.sh --kind work    # workers only (dispatchers, not integrations)
#   bash psq.sh --kind job     # integrations and sweeps only
#
# UNIX EDITION. This is `procs.py` with the fleet's patterns on it. The Windows psq.sh runs
# `powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process ..."` and cannot run
# anywhere else; procs.py reads /proc directly on Linux, `ps -axo` on the BSDs and macOS, and
# CIM on Windows, so one implementation answers the same question on all three. Every check in
# the fleet asks "is the fleet up?" and must get the SAME answer everywhere, or a stop procedure
# verified on one platform is unknown on another.
#
# The self-match guard in procs.py is load-bearing, not decoration. The old query put its own
# pattern text on its own command line, so the powershell process and both bash shells wrapping
# it matched: a check for "is anything running" answered "4" against a completely idle machine,
# which read as a live integration for 36 minutes on 2026-09-09. procs.py excludes the querying
# process and every ancestor BY PID, so it cannot match itself whatever the pattern says.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
. "$KIT/kitenv.sh"
MODE="${1:---count}"
KIND="${3:-all}"
[ "$1" = "--kind" ] && { KIND="$2"; MODE="--count"; }

args=(--kind "$KIND")
case "$MODE" in
  --list) args+=(--list) ;;
  --verbose) args+=(--verbose) ;;
esac

"$PY" "$KIT/procs.py" "${args[@]}" 2>/dev/null