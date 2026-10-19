#!/bin/bash
# Integrate every module that has staged work, one at a time, then report. Run with the fleet STOPPED.
#
# finish_wave serialises on wave.lock anyway, but running these sequentially and only with zero
# workers alive is the condition the whole integration path assumes: its preflight reverts tracked
# files and moves untracked ones around, so a worker writing during it loses work (four matched
# ov017 functions were swept into quarantine that way).
#
# Each module costs a full rebuild, so this is slow by nature -- the point is to clear the backlog
# completely before a measurement window, not to be quick.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && { pwd -W 2>/dev/null || pwd; })"
SP="$(python "$KIT/kitpaths.py" state)"
REPO="$(python "$(cd "$(dirname "${BASH_SOURCE[0]}")" && { pwd -W 2>/dev/null || pwd; })/kitpaths.py" repo)"
LOG="$SP/wlog/integrate_all.log"
SRC_EXTS="$(python "$KIT/buildcfg.py" --source-exts)" || exit 2
shopt -s extglob
SRC_GLOB="@($SRC_EXTS)"

echo "=== integrate_all $(date '+%m-%d %H:%M') ===" >> "$LOG"
BRANCH="${DQIX_BRANCH:-decomp-matching}"
H0=$(git -C "$REPO" rev-parse "$BRANCH" 2>/dev/null)

# Biggest backlog first: each wave costs the same rebuild whether it lands 1 function or 37.
set -- $(ls -d "$SP"/staging/*/ 2>/dev/null \
         | while read -r x; do echo "$(compgen -G "$x*.$SRC_GLOB" | wc -l) $x"; done \
         | sort -rn | awk '$1>0{print $2}')
last_moved=0
while [ $# -gt 0 ]; do
  d="$1"; shift
  tag=$(basename "$d")                 # main | ovNNN
  mod=${tag#ov}                        # finish_wave takes main | NNN
  n=$(compgen -G "$d*.$SRC_GLOB" | wc -l)
  defer=defer; [ $# -eq 0 ] && defer=""
  echo "$(date '+%H:%M') --- $tag: $n staged ---" >> "$LOG"
  _before=$(git -C "$REPO" rev-parse "$BRANCH" 2>/dev/null)
  DQIX_REGIONSYNC=$defer bash "$KIT/finish_wave.sh" "$mod" >> "$SP/wlog/int_${tag}.log" 2>&1
  last_moved=0; [ "$(git -C "$REPO" rev-parse "$BRANCH" 2>/dev/null)" != "$_before" ] && last_moved=1
  tail -1 "$SP/wlog/int_${tag}.log" >> "$LOG"
done

if [ "$(git -C "$REPO" rev-parse "$BRANCH" 2>/dev/null)" != "$H0" ] && [ "$last_moved" = 0 ]; then
  bash "$KIT/regionsync.sh" >> "$LOG" 2>&1
fi
echo "$(date '+%H:%M') === done ===" >> "$LOG"
python "$KIT/cov.py" >> "$LOG" 2>&1
tail -3 "$LOG"
