#!/usr/bin/env python3
"""Writes tests/stats/fixture/*.jsonl (TASK-195): hand-written tap records for tools/stats_report.py.

3 users (user-a: 1 session over 2 batches + a re-sent batch; user-b: 2 sessions; user-c (TASK-216): 1 session sc1
across UTC midnight, split over the 2026-11-20 and 2026-11-21 per-key files), 3 levels (srcId 1, 2, 3),
wins, restarts, off-map, abandon, all 15 buttons, every line event; one test record, one unparsable line,
one bodiless OPTIONS record and one other-game record in an old combined file, one other-game per-key file.
Expected report: tests/stats/fixture_expected.json (written by hand, not by this script).
"""
import json, os

KEY, OTHER = '6254c0dd9e9a91ef0e680ee697f8c1a8', '30115570bdc7d2fb17f377c6e7961d24'
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixture')
n = [0]


def ev(uid, sid, build, spec):
    """spec: 'user' | ('end', length) | 'Start:L1' | ('design id', value) | 'design id'."""
    n[0] += 1
    e = {'v': 2, 'event_uuid': f'uuid-{n[0]:04d}', 'user_id': uid, 'session_id': sid, 'build': build, 'client_ts': 1795000000 + n[0]}
    if spec == 'user':
        e['category'] = 'user'
    elif isinstance(spec, tuple) and spec[0] == 'end':
        e.update(category='session_end', length=spec[1])
    elif isinstance(spec, str) and spec.split(':')[0] in ('Start', 'Complete', 'Fail'):
        e.update(category='progression', event_id=spec)
    elif isinstance(spec, tuple):
        e.update(category='design', event_id=spec[0], value=spec[1])
    else:
        e.update(category='design', event_id=spec)
    return e


def rec(ts, path, body, test=False):
    return json.dumps({'ts': ts, 'test': test, 'ip': '198.51.100.7', 'ua': 'fixture', 'path': path, 'status': 200,
                       'body': body}, separators=(',', ':'))


EV = f'/v2/{KEY}/events'
A = lambda specs: [ev('user-a', 'sa1', '1.0.0', s) for s in specs]
B1 = lambda specs: [ev('user-b', 'sb1', '1.0.0', s) for s in specs]
B2 = lambda specs: [ev('user-b', 'sb2', '1.0.1', s) for s in specs]

a1 = A(['user', 'Start:L1', ('level:1:attempt', 1), 'ui:run:L1', ('lines:1:place', 1), ('lines:1:place', 2),
        ('lines:1:used', 2), 'ui:restart:L1', 'level:1:restart', 'Fail:L1', 'Start:L1', ('level:1:attempt', 2),
        ('lines:1:place', 1), ('lines:1:drag', 1), ('lines:1:drag', 0), 'ui:line_delete_bin:L1', 'lines:1:delete',
        'lines:1:reject_limit', ('lines:1:used', 1), 'ui:run:L1', 'Complete:L1', ('level:1:win', 12),
        ('level:1:win_attempt', 2), 'level:1:first_win', 'ui:next_level:L1', 'Start:L2', ('level:2:attempt', 1),
        'level:2:fail:offmap', 'Fail:L2', 'Start:L2', ('level:2:attempt', 2), 'ui:speed_on:L2', 'ui:speed_off:L2',
        'ui:pause:L2', 'ui:menu_open:L2', 'ui:map_open:L2', 'ui:menu_close:L2', 'level:2:abandon', 'Fail:L2',
        ('ui:map_level:map', 3), ('ui:preview_play:map', 3), 'ui:map_close:map', 'Start:L3', ('level:3:attempt', 1),
        ('session:play_seconds', 30), ('session:play_seconds', 60), 'session:hide'])
a2 = A(['ui:menu_open:L3', 'ui:resume:L3', 'ui:menu_close:L3', 'ui:menu_open:L3', 'ui:editor_open:L3',
        'ui:menu_close:L3', ('session:levels_seen', 3), ('end', 300)])
b1 = B1(['user', 'Start:L1', ('level:1:attempt', 1), 'ui:restart:L1', 'level:1:restart', 'Fail:L1', 'Start:L1',
         ('level:1:attempt', 2), 'ui:restart:L1', 'level:1:restart', 'Fail:L1', 'Start:L1', ('level:1:attempt', 3),
         ('lines:1:place', 1), ('lines:1:used', 1), 'ui:run:L1', 'Complete:L1', ('level:1:win', 40),
         ('level:1:win_attempt', 3), 'level:1:first_win', ('session:play_seconds', 30), ('end', 50)])
b2 = B2(['user', 'Start:L1', ('level:1:attempt', 4), ('lines:1:place', 1), ('lines:1:used', 1), 'ui:run:L1',
         'Complete:L1', ('level:1:win', 5), ('level:1:win_attempt', 4), ('session:play_seconds', 30),
         ('session:play_seconds', 60), ('session:play_seconds', 120), ('end', 130)])
t1 = [ev('user-test', 'st1', 'test-live-20261121', s) for s in ['user', 'Start:L1', ('level:1:attempt', 1)]]
g1 = [ev('user-g', 'sg1', '1.0.0', s) for s in ['user', ('level:1:attempt', 1)]]
C = lambda specs: [ev('user-c', 'sc1', '1.0.0', s) for s in specs]
c1 = C(['user', 'Start:L1', ('level:1:attempt', 1), ('session:play_seconds', 30)])  # 2026-11-20 23:59:30Z
c2 = C([('level:1:win', 50), ('level:1:win_attempt', 1), 'level:1:first_win', 'Complete:L1',
        ('session:play_seconds', 60), ('end', 90)])  # 2026-11-21 00:00:40Z, next day's file

files = {
    'events-2026-11-19.jsonl': [  # old combined file: only lines whose path holds KEY count
        rec('2026-11-19T09:00:00.000Z', f'/remote_configs/v1/init?game_key={KEY}&interval_seconds=0',
            {'user_id': 'user-a', 'build': '1.0.0', 'platform': 'linux'}),
        rec('2026-11-19T09:00:00.100Z', f'/remote_configs/v1/init?game_key={KEY}&interval_seconds=0', None),
        rec('2026-11-19T09:30:00.000Z', f'/v2/{OTHER}/events', g1)],
    f'events-{KEY}-2026-11-20.jsonl': [
        rec('2026-11-20T09:00:00.000Z', f'/v2/{KEY}/init', {'user_id': 'user-b', 'build': '1.0.0', 'platform': 'webgl'}),
        rec('2026-11-20T10:00:00.000Z', EV, a1),
        rec('2026-11-20T10:05:00.000Z', EV, a2),
        rec('2026-11-20T10:06:00.000Z', EV, a2),  # SDK re-send of the same batch: duplicates by event_uuid
        rec('2026-11-20T12:00:00.000Z', EV, b1),
        rec('2026-11-20T13:00:00.000Z', EV, b2),
        rec('2026-11-20T23:59:30.000Z', EV, c1)],
    f'events-{KEY}-2026-11-21.jsonl': [
        rec('2026-11-21T00:00:40.000Z', EV, c2),
        rec('2026-11-21T08:00:00.000Z', EV, t1, test=True),
        '{"ts":"2026-11-21T08:01:00.000Z","test":false,"path":"/v2/' + KEY + '/events","body":[{"v":2,'],  # cut line
    f'events-{OTHER}-2026-11-20.jsonl': [rec('2026-11-20T11:00:00.000Z', f'/v2/{OTHER}/events', g1)],
}
os.makedirs(D, exist_ok=True)
for name, lines in files.items():
    with open(os.path.join(D, name), 'w') as f:
        f.write('\n'.join(lines) + '\n')
print('\n'.join(f'{k}: {len(v)} lines' for k, v in files.items()))
