#!/bin/bash
# Full physics/visual regression (ported from the TASK-213 tools). Usage:
#   tests/regression/run_checks.sh <preview|full> <outdir>
# preview (~3.5 min): a subset of every check. full (~17 min): all 74 shoot scenarios (shard0..3.txt; TASK-248: 79 before srcId 8, 11, 14, 27, 29 were removed), 24 sim
# scenarios, 12 portal fuzz runs, full invariants/rimtrap/embed. Everything is written under <outdir> (logs/*.log,
# per-check JSON, shoot PNGs); <outdir>/regression.log is assembled at the end (tests/regression/assemble.py) and
# ends with '# SUMMARY', 'failed rows: N [...]' and 'ALL PASS' when N = 0. Exit 0 = ALL PASS, 1 otherwise.
set -u
M=${1:-}; OUT=${2:-}
if [ "$M" != preview ] && [ "$M" != full ] || [ -z "$OUT" ]; then echo "usage: $0 <preview|full> <outdir>" >&2; exit 2; fi
TL=$(cd "$(dirname "$0")" && pwd)
cd "$TL/../.."
D=$(realpath -m "$OUT"); L=$D/logs; mkdir -p "$L"
H="head=$(git rev-parse HEAD) dirty=$(git status --porcelain | grep -v '^?? artifacts' | tr '\n' ' ') ball.js=$(sha256sum js/ball.js | cut -c1-16) portal.js=$(sha256sum js/portal.js | cut -c1-16) levels.js=$(sha256sum js/levels.js | cut -c1-16) date=$(date -Is)"
echo "$H" > "$L/head.txt"
T0=$(date +%s)
if [ "$M" = preview ]; then FC="--cases 40"; SC=S1,W1; RP=--preview; IS="--scenes 50"; PC="--portal-cases 50"; TS="--runs 1 --fills 1"; SEEDS=1
  SH0=level1,level16,map,speed_on; SH1=level32,telemetry_levels; SH2=telemetry_ui,progress_reload,telemetry_editor; SH3=l19_rim_backside,next_level_order,lines_passed_restore,lines_storage_blocked,telemetry_first30
else FC=""; SC=S1,S2,S3,S4,S6,S7,S8,S9,S10,S11,S12,S13,S14,W1,W2,W3,W4,W5,W6,W7,W8,W9,W10,W11; RP=""; IS=""; PC=""; TS=""; SEEDS="1 2 3"
  SH0=$(cat "$TL/shard0.txt"); SH1=$(cat "$TL/shard1.txt"); SH2=$(cat "$TL/shard2.txt"); SH3=$(cat "$TL/shard3.txt"); fi
# what this run checks, read by assemble.py
printf '{"mode":"%s","shards":["%s","%s","%s","%s"],"sim":"%s","seeds":"%s"}\n' "$M" "$SH0" "$SH1" "$SH2" "$SH3" "$SC" "$SEEDS" > "$L/plan.json"
run() { local n=$1; shift; { echo "$H"; echo "\$ $*"; local t=$(date +%s); "$@"; echo "exit=$? seconds=$(( $(date +%s) - t ))"; } > "$L/$n.log" 2>&1; }
# trail_speed base: git archive 7bf1d25 + fonts/ + img/ + this tree's js/ball.js, js/portal.js, js/levels.js
TB=$D/tsbase; rm -rf "$TB"; mkdir -p "$TB"; git archive 7bf1d25 | tar -x -C "$TB"; cp -r fonts img "$TB/"; cp js/ball.js js/portal.js js/levels.js "$TB/js/"
# group A: shoot shards (browser heavy); --task/--out given as absolute paths so nothing goes to ./artifacts
for i in 0 1 2 3; do eval "S=\$SH$i"; run shoot_s$i python3 -u tests/visual/shoot.py --task "$D/shoot_s$i" --scenarios "$S" & done
# group B: headless node (run_fast.sh = energy/stuck/portal_fast/edge_cases fast physics checks, TASK-272; both modes)
( run edge node tests/physics/edge_cases.mjs --out "$D/edge.json"
  run run_fast tests/physics/run_fast.sh "$D/run_fast"
  for r in 1 2 3; do run rolling_$r node tests/physics/rolling.mjs --out "$D/rolling_$r.json"; done
  run rolling_compare python3 tests/physics/rolling_compare.py --out "$D/rolling.json" "$D/rolling_1.json" "$D/rolling_2.json" "$D/rolling_3.json"
  run inv_fuzz_chains node tests/physics/invariants.mjs --fuzz 1-5 --chains 1-5 $IS --out "$D/invariants_fuzz_chains.json" ) &
wait
# group C: portal fuzz modes (seeds 1-3 full, seed 1 preview)
for m in default crossing backside touching; do for s in $SEEDS; do
  F=""; [ $m != default ] && F="--$m"
  run fuzz_${m}_s$s python3 tests/portal/fuzz.py $F --seed $s $FC --task "$D/fuzz" --out fuzz_${m}_s$s.json & done; done
( run sim python3 tests/portal/sim.py --task "$D/sim" --scenarios $SC --out "$D/sim/sim.json"
  run map_check node tests/visual/map_check.mjs
  run frozen_check node tests/levels/frozen_check.mjs
  run speed_check python3 tests/visual/speed_check.py --out "$D/speed_check.json" ) &
wait
( run preview_check python3 tests/visual/preview_check.py --out "$D/preview_check.json"
  run trail_check python3 tests/visual/trail_check.py --out "$D/trail_check.json"
  run trail_speed python3 tests/visual/trail_speed.py --base "$TB" $TS --out "$D/trail_speed.json" ) &
( run inv_levels node tests/physics/invariants.mjs --levels --out "$D/invariants_levels.json"
  run inv_portal node tests/physics/invariants.mjs --browser --portal-fuzz 1-3 $PC --out "$D/invariants_portal.json" ) &
wait
run rimtrap python3 tests/portal/rimtrap.py --task "$D/rimtrap" --jobs 8 $RP
run embed python3 tests/portal/embed.py --task "$D/embed" --jobs 8 $RP
rm -rf "$TB"
echo "elapsed_s=$(( $(date +%s) - T0 ))" > "$L/run_checks.done"
python3 "$TL/assemble.py" "$D" "$D/regression.log"
