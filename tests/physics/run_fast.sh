#!/bin/bash
# Fast physics checks (TASK-272): run before every physics commit. Node only, no browser, ~1 min on an 8-core host.
#   tests/physics/run_fast.sh [outdir]
# Runs energy.mjs (two-sided energy, no portals), stuck.mjs (not stuck in textures), portal_fast.mjs (stuck / rule T /
# energy around portals) and edge_cases.mjs (line-end cases), one after another (the first three fan out to child
# processes themselves). Each suite's stdout goes to <outdir>/<suite>.log, its JSON to <outdir>/<suite>.json
# (default outdir: a temp dir, removed at the end). Prints one summary line per suite:
#   <suite> PASS|FAIL exit=N seconds=S <verdict line> [failing: <names>]
# and a final 'RUN_FAST PASS' / 'RUN_FAST FAIL: <suites>'. Exit 0 only when every suite exits 0.
set -u
cd "$(dirname "$0")/../.."
if [ -n "${1:-}" ]; then D=$(realpath -m "$1"); mkdir -p "$D"; KEEP=1; else D=$(mktemp -d); KEEP=0; fi
FAILED=()
T0=$(date +%s.%N)
for s in energy stuck portal_fast edge_cases; do
    t=$(date +%s.%N)
    node "tests/physics/$s.mjs" --out "$D/$s.json" > "$D/$s.log" 2>&1
    rc=$?
    sec=$(echo "$(date +%s.%N) - $t" | bc)
    # verdict = the suite's last line (ENERGY PASS / STUCK FAIL: names / PORTAL_FAST PASS / ALL PASS / FAILING: names)
    v=$(grep -v '^\s*$' "$D/$s.log" | tail -1)
    if [ $rc -eq 0 ]; then st=PASS; else st=FAIL; FAILED+=("$s"); fi
    printf '%-11s %s exit=%d seconds=%.1f %s\n' "$s" "$st" "$rc" "$sec" "$v"
    [ $rc -ne 0 ] && grep -E '^\s*FAIL ' "$D/$s.log" | head -20 | sed "s/^\s*/  $s: /"
done
printf 'wall seconds=%.1f\n' "$(echo "$(date +%s.%N) - $T0" | bc)"
[ $KEEP = 0 ] && rm -rf "$D"
if [ ${#FAILED[@]} -eq 0 ]; then echo 'RUN_FAST PASS'; exit 0; fi
echo "RUN_FAST FAIL: ${FAILED[*]}"; exit 1
