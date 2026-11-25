# Independent telemetry sequence check (ported from the TASK-213 tools): shoot's recorded debugLog vs tests/visual/telemetry_expected_*.json.
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
r['pass'] = r['levels_events_equal'] and r['levels_afterReload_equal'] and r['ui_events_equal'] and r.get('editor_events_equal', True)
print('telemetry sequences equal:', r['pass'], json.dumps(r, separators=(',', ':')))
sys.exit(0 if r['pass'] else 1)
