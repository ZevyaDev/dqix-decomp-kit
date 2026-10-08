#!/bin/bash
# One-shot bootstrap for Linux, the BSDs and macOS. Checks what is missing, installs what it can
# only with your say-so, then hands over to kit_init.py.
#
#   bash setup_unix.sh              check everything, install nothing, print what to run
#   bash setup_unix.sh --install    also `apt-get install` the packages it needs (needs sudo)
#   bash setup_unix.sh --fast       skip the slow end-to-end regress.py --slow pass
#
# SAFE TO RUN TWICE. Nothing here overwrites your config or your work; every step is a check
# first and a suggestion second. The state directory is never touched except to create it.
#
# WHAT THIS INSTALLS AND WHY
#
#   python3, python3-venv, python3-pip   the kit itself
#   build-essential, ninja-build        ninja builds the decomp; the mwccarm compiler is a
#                                       downloaded Windows binary, so no gcc cross-toolchain
#   git, ca-certificates                 both repos
#   python-is-python3                    gives you `python`, which every kit script and doc
#                                       invokes by name. Optional: kitenv.sh resolves `python3`
#                                       without it, and that is what the new Unix scripts use.
#   wine                                 FALLBACK ONLY. The decomp downloads `wibo`, a small
#                                       Win32 loader with no prefix and no daemon, and uses it by
#                                       default; wibo is what linuxenv.py looks for first. Wine
#                                       works and is more widely packaged, but it is far slower
#                                       per compiler invocation and needs a prefix initialised.
#
# WHAT THIS DOES NOT DO, and cannot: supply the base ROM. That is yours to provide and place as
# the decomp README says. No script here can create it, and a ROM is not something to fetch for
# you.
set -u
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
. "$KIT/kitenv.sh" 2>/dev/null || true
INSTALL=0
FAST=0
for a in "$@"; do
  case "$a" in
    --install) INSTALL=1 ;;
    --fast) FAST=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

fails=0
warn() { echo "WARN  $*"; }
fail() { echo "FAIL  $*"; fails=$((fails+1)); }
have() { command -v "$1" >/dev/null 2>&1; }

PKGS=""
need_pkg() { have "$1" || { warn "$1 missing"; PKGS="$PKGS $2"; }; }

echo "setup: platform $(uname -s) $(uname -m)"
echo

# 1. Python. The kit needs 3.10+; a distro python3 is usually newer, but a venv on an old base
# may not be, and the decomp README asks for 3.11.
if have python3; then
  _v=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  echo "ok    python3 $_v"
  case "$_v" in
    3.[0-9]|3.10) warn "python3 $_v is older than the kit's 3.10 floor for some features" ;;
  esac
else
  fail "no python3; install it (Debian/Ubuntu/MX: sudo apt install python3 python3-venv python3-pip)"
  PKGS="$PKGS python3 python3-venv python3-pip"
fi

# 2. The `python` NAME. Every existing script and every doc calls `python`. A stock Debian,
# Ubuntu or MX Linux has no such binary, so those scripts fail before any logic runs. This is
# the single most common reason "it doesn't work on Linux".
if have python; then
  echo "ok    python $(python -V 2>&1 | awk '{print $2}')"
else
  warn "no 'python' on PATH; the kit's existing scripts call it by that name."
  echo "      fix:  sudo apt install python-is-python3   (or use kitenv.sh's \$PY, which the"
  echo "            new *_linux scripts and all .py tools do)"
  PKGS="$PKGS python-is-python3"
fi

# 3. Build and fetch tools.
need_pkg git git
need_pkg ninja ninja-build
need_pkg curl curl
if have gcc; then echo "ok    gcc $(gcc -dumpversion)"; else warn "gcc missing (ninja needs it for host tools)"; PKGS="$PKGS build-essential"; fi

# 4. The Python packages every gate, listing and diff imports. Checked, never installed: pip
# into a system python is refused on current Debian and MX and is the wrong move anyway.
echo
echo "python packages:"
for m in capstone elftools; do
  if python3 -c "import $m" 2>/dev/null; then echo "ok    $m"; else
    warn "$m not importable"
  fi
done
for m in frida yaml; do
  python3 -c "import $m" 2>/dev/null || echo "note  optional: $m not installed (frida tools only)"
done

# 5. THE COMPILER RUNNER, the one thing that actually blocks a Unix port. mwccarm.exe is a
# Windows PE binary; the decomp already runs it on Linux through wibo, and the kit follows the
# decomp's own choice rather than inventing a second policy.
echo
echo "compiler runner:"
WINE_OK=0
if have wibo; then echo "ok    wibo on PATH"; WINE_OK=1
elif [ -x "$REPO/wibo" ]; then echo "ok    wibo in the decomp ($REPO/wibo)"; WINE_OK=1
elif have wine || have wine64; then echo "ok    wine on PATH (slower than wibo)"; WINE_OK=1
else
  fail "no Win32 runner, so mwccarm.exe cannot run here"
  echo "      the decomp fetches wibo itself:"
  echo "        cd $REPO && python3 tools/configure.py usa && ninja min"
  echo "      or install wine: sudo apt install wine   (needs a prefix; slower per compile)"
fi

# 6. The decomp checkout: present, and actually configured and built.
echo
echo "decomp checkout:"
if [ ! -d "$REPO" ]; then
  fail "not found: $REPO"
  echo "      git clone -b decomp-matching https://github.com/<you>/dqix-decomp.git $REPO"
else
  echo "ok    $REPO"
  for f in tools/configure.py build.ninja config/usa/arm9/symbols.txt extract/usa/arm9/arm9.bin; do
    [ -e "$REPO/$f" ] || fail "$f missing -- run: cd $REPO && python3 tools/configure.py usa && ninja min"
  done
  if [ -f "$REPO/extract/baserom_dqix_usa.nds" ]; then
    echo "ok    base ROM in place"
  else
    fail "no extract/baserom_dqix_usa.nds -- supply your own ROM; no script can fetch it"
  fi
  if [ -f "$REPO/arm7_bios.bin" ]; then
    echo "ok    arm7_bios.bin present (ninja sha1 can pass)"
  else
    warn "no arm7_bios.bin at the repo root; integrations commit locally but will not push"
  fi
fi

# 7. Hand over. kit_init.py is the real check and it is the one that gates work, so this ends
# there rather than duplicating its verdict.
echo
if [ "$INSTALL" = "1" ] && [ -n "$PKGS" ]; then
  if have apt-get; then
    echo "installing:$PKGS"
    sudo apt-get update && sudo apt-get install -y $PKGS
  else
    warn "--install only knows apt-get; install these yourself:$PKGS"
  fi
  echo
  echo "re-run this script to confirm, then: bash $KIT/kit_init.py"
  exit $fails
fi
[ -n "$PKGS" ] && echo "to install everything at once: sudo apt-get install -y$PKGS"

echo
if [ "$fails" -gt 0 ]; then
  echo "not ready: $fails problem(s) above"
  exit 1
fi
echo "platform checks passed. next:"
echo "  python3 -m pip install --user capstone pyelftools"
echo "  python3 $KIT/kit_init.py$( [ "$FAST" = 1 ] && echo "" || echo " --slow" )"
echo "  python3 $KIT/selfcheck.py"