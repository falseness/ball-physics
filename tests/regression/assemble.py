#!/usr/bin/env python3
# Builds <outdir>/regression.log from <outdir>/logs/*.log (written by tests/regression/run_checks.sh), quoting each
# check's own summary lines. The expected counts (shoot levelNN scenarios, sim scenarios, fuzz seeds) come from
# <outdir>/logs/plan.json, so preview and full runs are judged on what they ran. Ported from the TASK-213 tools.
#   python3 tests/regression/assemble.py <outdir> <outdir>/regression.log      exit 0 = ALL PASS, 1 otherwise
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
D = os.path.abspath(sys.argv[1]); L = f'{D}/logs'; out = []; fails = []
def lines(n): return open(f'{L}/{n}.log').read().splitlines() if os.path.exists(f'{L}/{n}.log') else ['MISSING LOG ' + n]
def ex(n):
    e = [l for l in lines(n) if l.startswith('exit=')]; return e[-1] if e else 'exit=MISSING'
def ok0(n): return ex(n).startswith('exit=0 ')
def sec(title): out.append(''); out.append('# ' + title)
def chk(ok, what):
    out.append(('PASS ' if ok else 'FAIL ') + what)
    if not ok: fails.append(what)
plan = json.load(open(f'{L}/plan.json'))
mode = plan['mode']; seeds = [int(s) for s in plan['seeds'].split()]
shard_sc = [s.split(',') for s in plan['shards']]
levels = [s for sh in shard_sc for s in sh if re.fullmatch(r'level\d+', s)]
sims = plan['sim'].split(',')
out.append(f'physics/visual regression (tests/regression/run_checks.sh {mode})')
out.append(open(f'{L}/head.txt').read().strip())
out.append(open(f'{L}/run_checks.done').read().strip() if os.path.exists(f'{L}/run_checks.done') else 'run_checks.done MISSING')
sec('shoot.py, %d scenarios in 4 shards (%s)' % (sum(map(len, shard_sc)), 'tests/regression/shard0..3.txt' if mode == 'full' else 'preview subset'))
lv = {}
for i in range(4):
    ls = lines(f'shoot_s{i}')
    for l in ls:
        if l.startswith(('OK:', 'FAILED', 'exit=')): out.append(f'  shoot_s{i}: ' + l)
        m = re.match(r'^(level\d+)\s+errors=(\d+)', l)
        if m: lv[m.group(1)] = {'errors': int(m.group(2))}
        m = re.search(r'levelCompleted=(\w+) winFrame=(\w+)', l)
        if m and lv:
            last = list(lv)[-1]; lv[last].update(won=m.group(1) == 'True', frame=m.group(2))
    chk(ok0(f'shoot_s{i}') and any(l.startswith('OK:') for l in ls), f'shoot shard {i} {ex(f"shoot_s{i}")}')
if mode == 'full':  # TASK-276: every shoot.py SCENARIOS key is in exactly the shard files, and the run ran them all
    import ast
    tree = ast.parse(open(os.path.join(ROOT, 'tests/visual/shoot.py')).read())
    known = next([k.value for k in n.value.keys] for n in tree.body if isinstance(n, ast.Assign)
                 and any(getattr(t, 'id', None) == 'SCENARIOS' for t in n.targets))
    files = [s for i in range(4) for s in open(f'{HERE}/shard{i}.txt').read().strip().split(',') if s]
    ran = [s for sh in shard_sc for s in sh if s]
    miss = [s for s in known if s not in files]; unk = sorted(set(files) - set(known))
    dup = sorted({s for s in files if files.count(s) > 1}); not_run = [s for s in known if s not in ran]
    out.append(f'  SCENARIOS {len(known)} in shard files {len(files)} not_in_any_shard {miss} unknown {unk} duplicates {dup} not_run {not_run}')
    chk(not miss and not unk and not dup and not not_run, f'shoot coverage: {len(known)} SCENARIOS, not_in_any_shard {miss}, unknown {unk}, duplicates {dup}, not_run {not_run}')
wins = sorted([k for k, v in lv.items() if v.get('won') and v['errors'] == 0], key=lambda s: int(s[5:]))
out.append('  levelNN wins: ' + ' '.join(f'{k}@{lv[k]["frame"]}' for k in wins))
chk(sorted(wins) == sorted(levels) and len(lv) == len(levels), f'every levelNN wins: {len(wins)}/{len(levels)} (scenarios seen {len(lv)})')
sec(f'tests/portal/sim.py, {len(sims)} scenarios ({plan["sim"]})')
s = lines('sim'); out += ['  ' + l for l in s if l.startswith('OK') or ' FAIL' in l]
np_ = sum(1 for l in s if re.match(r'^[SW]\d+ PASS', l)); nf = sum(1 for l in s if re.match(r'^[SW]\d+ FAIL', l))
chk(ok0('sim') and np_ == len(sims) and nf == 0, f'sim PASS lines {np_}/{len(sims)}, FAIL lines {nf}, {ex("sim")}')
sec('tests/portal/fuzz.py default / --crossing / --backside / --touching, seeds ' + ','.join(map(str, seeds)))
for m in ('default', 'crossing', 'backside', 'touching'):
    for sd in seeds:
        n = f'fuzz_{m}_s{sd}'; j = [l for l in lines(n) if l.startswith('{"cases"')]
        r = json.loads(j[-1]) if j else {}
        out.append(f'  {n}: cases={r.get("cases")} teleports={r.get("teleports")} traps={r.get("traps")} embedded={r.get("embedded")} nan={r.get("nanCount")} tunnels={r.get("tunnels")} traceHash={r.get("traceHash","")[:16]} | ' + ' '.join(l for l in lines(n) if l.startswith('PASS') or l.startswith('FAIL')))
        chk(ok0(n) and r.get('traps') == 0 and r.get('embedded') == 0, f'{n} trapped 0 embedded 0 {ex(n)}')
for n in ('rimtrap', 'embed'):
    sec(f'tests/portal/{n}.py (committed baseline in tests/portal/baselines + hash-pinned allowlist)')
    out += ['  ' + l for l in lines(n) if re.match(r'^(front_diff|repro\.|baseline=|EXIT)', l)]
    chk(ok0(n) and 'EXIT 0' in lines(n), f'{n} {ex(n)}')
sec('node tests/physics/portal_parity.mjs (TASK-278: node harness vs browser, bit for bit, incl. the glibc sin/cos port)')
pl = lines('portal_parity'); out += ['  ' + l[:400] for l in pl if l.startswith(('math check:', 'portal parity:', 'fresh-scope', 'MISSING'))]
pp = [l for l in pl if re.match(r'^portal parity: scenes \d+, .*mismatching scenes 0,.* pass true$', l)]
mc = [l for l in pl if l.startswith('math check: ')]
try: mok = bool(mc) and json.loads(mc[-1][len('math check: '):]).get('ok') is True
except ValueError: mok = False
chk(ok0('portal_parity') and bool(pp) and mok, f'portal_parity mismatching scenes 0 pass true {bool(pp)}, math ok {mok}, {ex("portal_parity")}')
sec('tests/platform/test_backends.py, test_analytics.py --backend none, stats_report.py fixture (TASK-280)')
bl = lines('backends'); out += ['  backends: ' + l[:200] for l in bl if re.match(r'^(\w+\s+platformId=|index:|OK:|FAILED|MISSING)', l)]
chk(ok0('backends') and 'OK: 5 backends' in bl, f'backends OK: 5 backends {"OK: 5 backends" in bl}, {ex("backends")}')
al = lines('analytics'); out += ['  analytics: ' + l[:200] for l in al if re.match(r'^(none\s|OK$|FAILED|MISSING)', l)]
anone = any(re.match(r'^none\s.*\sPASS$', l) for l in al); afin = [l for l in al if not l.startswith('exit=')]
chk(ok0('analytics') and anone and bool(afin) and afin[-1] == 'OK', f'analytics none PASS {anone}, final OK {bool(afin) and afin[-1] == "OK"}, {ex("analytics")}')
sl = lines('stats_fixture'); sj = [l for l in sl if l.startswith('{"equal":')]
try: seq = bool(sj) and json.loads(sj[-1]).get('equal') is True
except ValueError: seq = False
out += ['  stats_fixture: ' + l[:200] for l in sj or [l for l in sl if l.startswith('MISSING')]]
chk(ok0('stats_fixture') and seq, f'stats_fixture check_fixture "equal":true {seq}, {ex("stats_fixture")}')
sec('node tests/physics/edge_cases.mjs')
out += ['  ' + l for l in lines('edge') if l.startswith(('PASS', 'FAIL', 'ALL'))]
chk(ok0('edge') and 'ALL PASS' in lines('edge'), f'edge_cases {ex("edge")}')
sec('tests/physics/run_fast.sh (energy, stuck, portal_fast, edge_cases)')
out += ['  ' + l for l in lines('run_fast') if re.match(r'^(energy|stuck|portal_fast|edge_cases|wall|RUN_FAST)', l)]
chk(ok0('run_fast') and 'RUN_FAST PASS' in lines('run_fast'), f'run_fast {ex("run_fast")}')
sec('invariants: --fuzz 1-5 --chains 1-5 (headless), --levels, --browser --portal-fuzz 1-3')
for n in ('inv_fuzz_chains', 'inv_levels', 'inv_portal'):
    t = [l for l in lines(n) if 'total:' in l or l.startswith('TOTAL')]; out += [f'  {n}: ' + l for l in t]
    tot = [l for l in t if l.startswith('TOTAL')]
    chk(ok0(n) and bool(tot) and re.search(r'I1 0 I2 0 I3 0 T 0', tot[-1]) is not None, f'{n} 0 violations {ex(n)}')
sec('rolling.mjs x3 vs tests/physics/rolling_accepted.json (tests/physics/rolling_compare.py, TASK-199 rule)')
for i in (1, 2, 3): chk(ok0(f'rolling_{i}'), f'rolling run {i} {ex(f"rolling_{i}")}')
out += ['  ' + l for l in lines('rolling_compare') if l.startswith(('rolling metrics', 'outside:'))]
rj = f'{D}/rolling.json'
chk(ok0('rolling_compare') and os.path.exists(rj) and json.load(open(rj)).get('pass') is True, f'rolling within tolerance {ex("rolling_compare")}')
for n, key in (('preview_check', 'allPass True'), ('trail_check', 'allPass True'), ('trail_speed', 'allPass True'), ('speed_check', 'allPass')):
    sec(n + (' (base: git archive 7bf1d25 + fonts/img + this tree\'s js/ball.js, js/portal.js, js/levels.js)' if n == 'trail_speed' else ''))
    out += ['  ' + l for l in lines(n) if l.startswith(('allPass', 'PASS identity', 'FAIL', 'PASS fill', 'PASS srcId', 'points', 'shared'))]
    chk(ok0(n) and any(l.startswith(key) for l in lines(n)), f'{n} {ex(n)}')
if os.path.exists(f'{D}/trail_speed.json'):
    ts = json.load(open(f'{D}/trail_speed.json')); mm = json.dumps(ts.get('mismatches', ts.get('mismatchTotal')))
    out.append('  trail_speed.json mismatches: ' + mm)
sec('node tests/visual/map_check.mjs')
out += ['  ' + l[:160] for l in lines('map_check') if l.startswith('{"pass"')]
chk(ok0('map_check'), f'map_check {ex("map_check")}')
sec('node tests/levels/frozen_check.mjs (TASK-243 frozen layouts vs tests/levels/frozen.json)')
out += ['  ' + l for l in lines('frozen_check') if l.startswith(('FAIL', 'FROZEN', 'ERROR'))]
chk(ok0('frozen_check') and any(l.startswith('FROZEN OK') for l in lines('frozen_check')), f'frozen_check {ex("frozen_check")}')
sec('telemetry sequences (tests/regression/seq_check.py, independent of shoot.py verdicts)')
r = subprocess.run([sys.executable, os.path.join(HERE, 'seq_check.py'), D], capture_output=True, text=True, cwd=ROOT)
out.append('  ' + (r.stdout.strip() or r.stderr.strip().splitlines()[-1] if (r.stdout or r.stderr) else 'no output'))
chk(r.returncode == 0 and 'equal: True' in r.stdout, 'telemetry sequences equal')
sec('SUMMARY'); out.append(f'failed rows: {len(fails)} {fails}'); out.append('ALL PASS' if not fails else 'NOT ALL PASS')
open(sys.argv[2], 'w').write('\n'.join(out) + '\n'); print('\n'.join(out[-3:]))
sys.exit(0 if not fails else 1)
