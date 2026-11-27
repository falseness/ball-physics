#!/usr/bin/env python3
"""TASK-195: compare a stats_report.py report.json with tests/stats/fixture_expected.json.

    python3 tests/stats/check_fixture.py REPORT_JSON [--out check.json]
Exit 0 when equal (JSON value equality); prints a unified diff of the canonical (sorted-key) dumps otherwise.
"""
import difflib, json, os, sys

here = os.path.dirname(os.path.abspath(__file__))
got = json.load(open(sys.argv[1]))
exp = json.load(open(os.path.join(here, 'fixture_expected.json')))
dump = lambda o: json.dumps(o, sort_keys=True, indent=1).splitlines()
diff = list(difflib.unified_diff(dump(exp), dump(got), 'expected', 'report', lineterm=''))
res = {'equal': got == exp, 'diff_lines': len(diff), 'unparsed': got.get('unparsed'),
       'excluded_test_records': got.get('excluded_test_records'), 'test_user_in_report': 'user-test' in got.get('users', {}),
       'users': sorted(got.get('users', {})), 'levels': list(got.get('levels', {})), 'events': got.get('events'),
       # TASK-261: pause-menu 'skip level' counts (per level / per user totals) as reported
       'skips': {'levels': {k: [v.get('skips'), v.get('users_skipped')] for k, v in got.get('levels', {}).items()},
                 'users': {k: u['totals'].get('skips') for k, u in got.get('users', {}).items()}}}
print('\n'.join(diff))
print(json.dumps(res, separators=(',', ':')))
if '--out' in sys.argv:
    with open(sys.argv[sys.argv.index('--out') + 1], 'w') as f:
        json.dump(res, f, separators=(',', ':'))
sys.exit(0 if res['equal'] else 1)
