#!/usr/bin/env python3
# Rolling-physics pass/fail check (ported from the TASK-213 tool). Compares the metrics of rolling.mjs runs with
# the accepted values in tests/physics/rolling_accepted.json (byte copy of the TASK-199 contact-model baseline).
# Rule (TASK-199): a metric passes when the min/max over all runs lies in [min - tol, max + tol] of the accepted
# new_min/new_max, tol = max(2*range, 1% of |value|). Exit 0 when every metric passes, 1 otherwise.
#
#   node tests/physics/rolling.mjs --out r1.json   (x3)
#   python3 tests/physics/rolling_compare.py [--accepted FILE] [--out FILE] r1.json r2.json r3.json
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('runs', nargs='+', help='rolling.mjs output JSON files')
    ap.add_argument('--accepted', default=os.path.join(HERE, 'rolling_accepted.json'))
    ap.add_argument('--out', help='write the comparison as compact JSON')
    a = ap.parse_args()
    runs = [json.load(open(f)) for f in a.runs]
    acc = json.load(open(a.accepted))['rows']
    rows, outside = {}, []
    for name, ref in acc.items():
        vals = [r['metrics'][name] for r in runs]
        lo, hi = min(vals), max(vals)
        bmin, bmax = ref['new_min'], ref['new_max']
        tol = max(2 * (bmax - bmin), 0.01 * max(abs(bmin), abs(bmax)))
        ok = lo >= bmin - tol and hi <= bmax + tol
        rows[name] = {'min': lo, 'max': hi, 'acc': [bmin, bmax], 'tol': tol, 'within': ok}
        if not ok:
            outside.append(name)
    out = {'reference': os.path.relpath(a.accepted), 'runs': len(runs), 'metrics': len(rows),
           'within': len(rows) - len(outside), 'outside': outside, 'pass': not outside, 'rows': rows}
    if a.out:
        open(a.out, 'w').write(json.dumps(out, separators=(',', ':')) + '\n')
    for name in outside:
        r = rows[name]
        print(f"outside: {name} runs [{r['min']}, {r['max']}] accepted {r['acc']} tol {r['tol']}")
    print('rolling metrics', out['metrics'], 'within', out['within'], 'outside', outside, 'pass', out['pass'])
    return 0 if out['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
