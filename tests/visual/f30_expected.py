#!/usr/bin/env python3
"""TASK-240: extend tests/visual/telemetry_expected_first30.json from a telemetry_first30 run.

  python3 tests/visual/shoot.py --task <dir> --scenarios telemetry_first30   (fails until the file is extended)
  python3 tests/visual/f30_expected.py artifacts/<dir>/sequence_first30.json [--replace-steps]

Writes 'presses' and 'heartbeats' (f30:press / f30:hb [id, value] pairs per visitor) and adds visitors missing from
'visitors' (f30:<k>: step ids). 'events' and 'afterReload' are never changed. A visitor whose recorded steps differ
from 'visitors' is reported and the script exits 1, unless --replace-steps: then only step VALUES may change (same
ids in the same order) and every changed [id, old, new] is printed (TASK-240: visitors boot under a paused clock, so
frame-detected steps moved onto the fake frame grid, e.g. offmap 3823 -> 3824).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPECTED = os.path.join(ROOT, 'tests', 'visual', 'telemetry_expected_first30.json')


def main(seq_path, replace_steps=False):
    with open(seq_path) as f:
        seq = json.load(f)
    with open(EXPECTED) as f:
        want = json.load(f)
    runs = seq['visitors']
    bad = [n for n, r in runs.items() if n in want['visitors'] and want['visitors'][n] != r['actual']]
    if bad and not replace_steps:
        print('step sequences differ from the expected file (not rewritten): %s' % bad)
        return 1
    for n in bad:
        old, new = want['visitors'][n], runs[n]['actual']
        if [e[0] for e in old] != [e[0] for e in new]:
            print('visitor %s: step ids differ (only values may be replaced): %s / %s' % (n, old, new))
            return 1
        for a, b in zip(old, new):
            if a != b:
                print('replace %s %s: %r -> %r' % (n, a[0], a[1], b[1]))
        want['visitors'][n] = new
    for n, r in runs.items():
        if n not in want['visitors']:
            want['visitors'][n] = r['actual']
    want['visitorsNote'] = ('TASK-239 f30: ids of visitors A-D, TASK-240 visitor E ([id, value], value = ms since t0; '
                            'end = furthest funnel index; leave_step has no value), each in a clean context with '
                            'touch; page.clock installed and paused before navigation, stepped in 16 ms to t0, every '
                            'action at an exact fake time (shoot.py f30_visitor_a..e)')
    want['pressesNote'] = ('TASK-240 f30:press:<target>:<gx>_<gy> per visitor ([id, value], value = ms since t0; '
                           'cell = floor(x / 40)_floor(y / 40) on the logical 1280x800 field); visitor E adds touch '
                           'presses at the logical points other visitors press with the mouse (shoot.py f30_visitor_e)')
    want['presses'] = {n: r['presses'] for n, r in runs.items()}
    want['heartbeatsNote'] = ('TASK-240 f30:hb:<s>:moved|idle|visible|step per visitor at 5..30 s while the page is '
                              'open (moved = logical px since the previous beat, idle = ms since the last input at '
                              'the nominal beat time, step = furthest funnel index)')
    want['heartbeats'] = {n: r['heartbeats'] for n, r in runs.items()}
    with open(EXPECTED, 'w') as f:
        json.dump(want, f, indent=1)
        f.write('\n')
    print('wrote %s: visitors %s, presses %s, heartbeats %s' % (
        os.path.relpath(EXPECTED, ROOT), list(want['visitors']), {n: len(v) for n, v in want['presses'].items()},
        {n: len(v) for n, v in want['heartbeats'].items()}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], '--replace-steps' in sys.argv[2:]))
