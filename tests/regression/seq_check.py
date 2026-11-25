# Independent telemetry sequence check (TASK-242: + telemetry_first30) (ported from the TASK-213 tools): shoot's recorded debugLog vs tests/visual/telemetry_expected_*.json.
# Placeholder 'time>0' in an expected event = any number > 0; every other field must be exactly equal.
#   python3 tests/regression/seq_check.py <outdir>   (outdir of run_checks.sh; exit 0 = equal, 1 otherwise)
import json, os, sys, glob
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
d = sys.argv[1]
def eq(exp, got):
    if len(exp) != len(got): return False
    for e, g in zip(exp, got):
        if len(e) != len(g): return False
        for a, b in zip(e, g):
            if a == 'time>0':
                if not (isinstance(b, (int, float)) and b > 0): return False
            elif a != b: return False
    return True
lv = json.load(open(glob.glob(f'{d}/shoot_s*/sequence_levels.json')[0]))
ui = json.load(open(glob.glob(f'{d}/shoot_s*/sequence.json')[0]))
el = json.load(open(f'{ROOT}/tests/visual/telemetry_expected_levels.json')); eu = json.load(open(f'{ROOT}/tests/visual/telemetry_expected_ui.json'))
r = {'levels_events_equal': eq(el['events'], lv['debugLog']), 'levels_n': [len(lv['debugLog']), len(el['events'])],
     'levels_afterReload_equal': eq(el['afterReload'], lv['debugLogAfterReload']),
     'ui_events_equal': eq(eu['events'], ui['debugLog']), 'ui_n': [len(ui['debugLog']), len(eu['events'])],
     'shoot_verdicts': {'levels': lv.get('pass'), 'ui': ui.get('pass')}}
ed = glob.glob(f'{d}/shoot_s*/sequence_editor.json')  # TASK-232: telemetry_editor (shard 2 in preview and full)
plan = os.path.join(d, 'logs', 'plan.json')  # TASK-237: required when the run's shards list it
r['editor_required'] = os.path.exists(plan) and 'telemetry_editor' in ','.join(json.load(open(plan))['shards']).split(',')
if r['editor_required'] and not ed:
    r['editor_events_equal'] = False
elif ed:
    se = json.load(open(ed[0])); ee = json.load(open(f'{ROOT}/tests/visual/telemetry_expected_editor.json'))
    r['editor_events_equal'] = eq(ee['events'], se['debugLog']); r['editor_n'] = [len(se['debugLog']), len(ee['events'])]
    r['shoot_verdicts']['editor'] = se.get('pass')
# TASK-242: telemetry_first30 (shard 3 in preview and full): load:/ctx: ids of both loads and every visitor's f30
# funnel / press / heartbeat [id, value] pairs vs telemetry_expected_first30.json, exact
f3 = glob.glob(f'{d}/shoot_s*/sequence_first30.json')
r['first30_required'] = os.path.exists(plan) and 'telemetry_first30' in ','.join(json.load(open(plan))['shards']).split(',')
if r['first30_required'] and not f3:
    r['first30_equal'] = False
elif f3:
    s3 = json.load(open(f3[0])); e3 = json.load(open(f'{ROOT}/tests/visual/telemetry_expected_first30.json'))
    r['first30_load_equal'] = s3.get('ids') == e3['events'] and s3.get('idsAfterReload') == e3['afterReload']
    v3 = s3.get('visitors', {})
    r['first30_visitors'] = {n: [v3.get(n, {}).get(k) == e3[w].get(n) for k, w in
                                 (('actual', 'visitors'), ('presses', 'presses'), ('heartbeats', 'heartbeats'))]
                             for n in sorted(e3['visitors'])}
    r['first30_n'] = [sum(len(v3.get(n, {}).get(k) or []) for n in e3['visitors'] for k in ('actual', 'presses', 'heartbeats')),
                      sum(len(e3[w][n]) for n in e3['visitors'] for w in ('visitors', 'presses', 'heartbeats'))]
    r['first30_equal'] = r['first30_load_equal'] and all(all(x) for x in r['first30_visitors'].values())
    r['shoot_verdicts']['first30'] = s3.get('pass')
r['pass'] = r['first30_equal'] if 'first30_equal' in r else True
r['pass'] = r['pass'] and r['levels_events_equal'] and r['levels_afterReload_equal'] and r['ui_events_equal'] and r.get('editor_events_equal', True)
print('telemetry sequences equal:', r['pass'], json.dumps(r, separators=(',', ':')))
sys.exit(0 if r['pass'] else 1)
