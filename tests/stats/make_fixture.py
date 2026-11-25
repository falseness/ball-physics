#!/usr/bin/env python3
"""Writes tests/stats/fixture/*.jsonl (TASK-195): hand-written tap records for tools/stats_report.py.

3 users (user-a: 1 session over 2 batches + a re-sent batch; user-b: 2 sessions; user-c (TASK-216): 1 session sc1
across UTC midnight, split over the 2026-11-20 and 2026-11-21 per-key files), 3 levels (srcId 1, 2, 3),
wins, restarts, off-map, abandon, all 15 buttons, every line event; TASK-236: editor + play-test events for user-a
(2 editor sessions: L3 from the menu with every object / toolbar event and 2 play-tested hashes, L1 from the win window
abandoned) and user-b (1 session on L1 from the win window, 1 play-tested hash, one malformed edit: id); one test record, one unparsable line,
one bodiless OPTIONS record and one other-game record in an old combined file, one other-game per-key file.
TASK-241: first-30 sessions (load: / ctx: / f30: rows only) on 2026-11-21, after the cut line: user-d sd1 (new, mouse,
wins at 9 s, next level, ends at 30 s), user-e se1 (new, touch, iframe, onload -1, opens the menu, leaves at 12.5 s),
user-f sf1 (new, one point, idle to the end) + sf2 (ret, reload, places a line, off-map, reject_limit, restart),
user-h sh1 (ret, back_forward, html/dom/onload -1, two field presses without point1, leaves at 3 s, one malformed f30: id).
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
# TASK-236: editor sessions. user-a: L3 (menu) -> exit, L1 (win) -> abandon; user-b: L1 (win) -> exit
HA, HB, HC = '0a1b2c3d', 'ffee0011', 'deadbeef'
summ = lambda ctx, h, ln, po, lk, ch: [(f'editor:sum:{ctx}:{h}:lines', ln), (f'editor:sum:{ctx}:{h}:portals', po),
                                       (f'editor:sum:{ctx}:{h}:linek', lk), (f'editor:sum:{ctx}:{h}:changed', ch)]
a3 = A(['editor:open:L3:menu', 'editor:tool:L3:line', ('editor:line:L3:add', 4), 'editor:line:L3:cancel',
        ('editor:line:L3:add', 5), 'editor:tool:L3:select', 'editor:line_move:L3:ok',
        'editor:error:L3:line_would_leave_the_field', 'editor:line_end:L3:refused', 'editor:line_end:L3:ok',
        'editor:line_end:L3:degenerate', 'editor:move:L3:ball', 'editor:move:L3:flag', 'editor:snap:L3:off',
        'editor:rotate:L3:cw:flag', 'editor:tool:L3:portal', 'editor:portal:L3:a', 'editor:portal:L3:b',
        ('editor:portal_size:L3:bigger', 120), ('editor:portal_size:L3:smaller', 0), 'editor:error:L3:portals_overlap',
        'editor:portal_move:L3:refused', 'editor:portal_move:L3:ok', ('editor:linek:L3:inc', 3), 'editor:btn:L3:play']
       + summ('L3', HA, 5, 2, 3, 1)
       + [(f'edit:{HA}:attempt', 1), (f'edit:{HA}:line_place', 1), (f'edit:{HA}:line_place', 2), (f'edit:{HA}:line_drag', 0),
          f'edit:{HA}:line_delete', f'edit:{HA}:run', f'edit:{HA}:speed_on', f'edit:{HA}:speed_off', f'edit:{HA}:offmap',
          (f'edit:{HA}:attempt', 2), (f'edit:{HA}:line_place', 1), f'edit:{HA}:run', (f'edit:{HA}:win', 7), f'edit:{HA}:back',
          'editor:tool:L3:delete', 'editor:line_del:L3:tool', 'editor:portal_del:L3', 'editor:line_del:L3:key',
          'editor:btn:L3:export'] + summ('L3', HB, 4, 0, 3, 1)
       + ['editor:btn:L3:import', 'editor:import:L3:invalid', 'editor:error:L3:invalid_level_file',
          'editor:btn:L3:import', 'editor:import:L3:ok', 'editor:bar_move:L3', 'editor:btn:L3:exit']
       + summ('L3', HB, 4, 0, 3, 1) + [('editor:actions:L3', 33), ('editor:exit:L3', 95),
          'editor:open:L1:win', 'editor:tool:L1:line', ('editor:linek:L1:dec', 0), ('editor:actions:L1', 2),
          ('editor:abandon:L1', 20)])
b3 = B1(['editor:open:L1:win', 'editor:btn:L1:new', 'editor:snap:L1:on', 'editor:rotate:L1:ccw:portal',
         'editor:btn:L1:import', 'editor:import:L1:old_format', 'editor:error:L1:old_portal_format', 'editor:btn:L1:play']
        + summ('L1', HC, 2, 0, 1, 1)
        + [(f'edit:{HC}:attempt', 1), (f'edit:{HC}:line_place', 1), f'edit:{HC}:run', f'edit:{HC}:restart',
           (f'edit:{HC}:attempt', 2), (f'edit:{HC}:line_place', 1), (f'edit:{HC}:line_drag', 1), f'edit:{HC}:run',
           (f'edit:{HC}:win', 3), f'edit:{HC}:back', 'edit:zzzz:attempt', 'editor:btn:L1:exit']
        + summ('L1', HC, 2, 0, 1, 1) + [('editor:actions:L1', 7), ('editor:exit:L1', 40)])
t1 = [ev('user-test', 'st1', 'test-live-20261121', s) for s in ['user', 'Start:L1', ('level:1:attempt', 1)]]
g1 = [ev('user-g', 'sg1', '1.0.0', s) for s in ['user', ('level:1:attempt', 1)]]
C = lambda specs: [ev('user-c', 'sc1', '1.0.0', s) for s in specs]
c1 = C(['user', 'Start:L1', ('level:1:attempt', 1), ('session:play_seconds', 30)])  # 2026-11-20 23:59:30Z
c2 = C([('level:1:win', 50), ('level:1:win_attempt', 1), 'level:1:first_win', 'Complete:L1',
        ('session:play_seconds', 60), ('end', 90)])  # 2026-11-21 00:00:40Z, next day's file

# TASK-241: first-30 sessions. load stages html, dom, onload, boot, platform, storage, fonts, first_frame, transfer_kb, resources
STAGES = ['html', 'dom', 'onload', 'boot', 'platform', 'storage', 'fonts', 'first_frame', 'transfer_kb', 'resources']
boot30 = lambda vals, nav, inp, emb, plat, vw, k: ([(f'load:{st}', v) for st, v in zip(STAGES, vals)]
                                                    + [f'load:nav:{nav}', f'ctx:input:{inp}', f'ctx:embed:{emb}',
                                                       f'ctx:platform:{plat}', f'ctx:vw:{vw}', f'ctx:visitor:{k}'])
hb = lambda s, moved, idle, step, vis=1: [(f'f30:hb:{s}:moved', moved), (f'f30:hb:{s}:idle', idle),
                                         (f'f30:hb:{s}:visible', vis), (f'f30:hb:{s}:step', step)]
D1 = lambda specs: [ev('user-d', 'sd1', '1.0.2', s) for s in specs]
E1 = lambda specs: [ev('user-e', 'se1', '1.0.2', s) for s in specs]
F1 = lambda specs: [ev('user-f', 'sf1', '1.0.2', s) for s in specs]
F2 = lambda specs: [ev('user-f', 'sf2', '1.0.2', s) for s in specs]
H1 = lambda specs: [ev('user-h', 'sh1', '1.0.2', s) for s in specs]
d30 = D1(boot30([120, 300, 450, 310, 330, 340, 400, 420, 900, 30], 'navigate', 'mouse', 'top', 'local', 'lt1440', 'new')
         + [('f30:new:first_move', 800), ('f30:press:field:10_12', 1500), ('f30:new:first_press', 1500),
            ('f30:new:point1', 1500), ('f30:press:field:14_12', 2600), ('f30:new:point2', 2600), ('f30:new:run', 2650)]
         + hb(5, 640, 2400, 8) + [('f30:new:win', 9000)] + hb(10, 0, 7400, 12)
         + [('f30:press:other:16_10', 11000), ('f30:new:level_change', 11000)] + hb(15, 120, 4000, 15)
         + [('f30:press:field:10_12', 18000)] + hb(20, 300, 2000, 15) + hb(25, 0, 7000, 15) + hb(30, 0, 12000, 15)
         + [('f30:new:end', 15)])
e30 = E1(boot30([800, 2500, -1, 2510, 2900, 2950, 3600, 3700, 1000, 31], 'navigate', 'touch', 'iframe', 'yandex', 'lt480', 'new')
         + [('f30:press:hud_menu:31_0', 4000), ('f30:new:first_press', 4000), ('f30:new:menu_open', 4000)]
         + hb(5, 0, 1000, 13) + hb(10, 0, 6000, 13)
         + [('f30:new:leave', 12500), 'f30:new:leave_step:menu_open', ('f30:new:hidden', 12500)])
f30a = F1(boot30([200, 500, 700, 510, 520, 530, 600, 640, 950, 30], 'navigate', 'mouse', 'top', 'local', 'lt1024', 'new')
          + [('f30:new:first_move', 2000), ('f30:press:field:12_9', 3000), ('f30:new:first_press', 3000),
             ('f30:new:point1', 3000)] + hb(5, 450, 2000, 3) + hb(10, 0, 7000, 3) + hb(15, 0, 12000, 3)
          + hb(20, 0, 17000, 3) + hb(25, 0, 22000, 3) + hb(30, 0, 27000, 3) + [('f30:new:end', 3)])
f30b = F2(boot30([50, 150, 260, 160, 170, 175, 200, 220, 12, 30], 'reload', 'mouse', 'top', 'local', 'lt1024', 'ret')
          + [('f30:ret:first_move', 300), ('f30:press:field:8_15', 500), ('f30:ret:first_press', 500), ('f30:ret:point1', 500),
             ('f30:press:field:12_15', 1200), ('f30:ret:point2', 1200), ('f30:ret:run', 1250)] + hb(5, 900, 3800, 8)
          + [('f30:ret:offmap', 5100), ('f30:press:field:9_16', 7000), ('f30:ret:reject_limit', 7000),
             ('f30:press:hud_restart:1_0', 7500), ('f30:ret:restart', 7500)] + hb(10, 200, 2500, 11)
          + hb(15, 0, 7500, 11) + hb(20, 0, 12500, 11) + hb(25, 0, 17500, 11) + hb(30, 0, 22500, 11)
          + [('f30:ret:end', 11)])
h30 = H1(boot30([-1, -1, -1, 90, 100, 110, 130, 150, 0, 0], 'back_forward', 'touch', 'top', 'yandex', 'lt768', 'ret')
         + [('f30:press:field:20_10', 1000), ('f30:ret:first_press', 1000), ('f30:ret:bogus', 1500),
            ('f30:press:field:20_10', 2500), ('f30:ret:leave', 3000), 'f30:ret:leave_step:first_press',
            ('f30:ret:hidden', 3000)])

files = {
    'events-2026-11-19.jsonl': [  # old combined file: only lines whose path holds KEY count
        rec('2026-11-19T09:00:00.000Z', f'/remote_configs/v1/init?game_key={KEY}&interval_seconds=0',
            {'user_id': 'user-a', 'build': '1.0.0', 'platform': 'linux'}),
        rec('2026-11-19T09:00:00.100Z', f'/remote_configs/v1/init?game_key={KEY}&interval_seconds=0', None),
        rec('2026-11-19T09:30:00.000Z', f'/v2/{OTHER}/events', g1)],
    f'events-{KEY}-2026-11-20.jsonl': [
        rec('2026-11-20T09:00:00.000Z', f'/v2/{KEY}/init', {'user_id': 'user-b', 'build': '1.0.0', 'platform': 'webgl'}),
        rec('2026-11-20T10:00:00.000Z', EV, a1),
        rec('2026-11-20T10:04:30.000Z', EV, a3),
        rec('2026-11-20T10:05:00.000Z', EV, a2),
        rec('2026-11-20T10:06:00.000Z', EV, a2),  # SDK re-send of the same batch: duplicates by event_uuid
        rec('2026-11-20T12:00:00.000Z', EV, b1),
        rec('2026-11-20T12:30:00.000Z', EV, b3),
        rec('2026-11-20T13:00:00.000Z', EV, b2),
        rec('2026-11-20T23:59:30.000Z', EV, c1)],
    f'events-{KEY}-2026-11-21.jsonl': [
        rec('2026-11-21T00:00:40.000Z', EV, c2),
        rec('2026-11-21T08:00:00.000Z', EV, t1, test=True),
        '{"ts":"2026-11-21T08:01:00.000Z","test":false,"path":"/v2/' + KEY + '/events","body":[{"v":2,',  # cut line
        rec('2026-11-21T09:00:00.000Z', EV, d30),  # TASK-241: first-30 sessions
        rec('2026-11-21T09:10:00.000Z', EV, e30),
        rec('2026-11-21T09:20:00.000Z', EV, f30a),
        rec('2026-11-21T10:20:00.000Z', EV, f30b),
        rec('2026-11-21T11:00:00.000Z', EV, h30)],
    f'events-{OTHER}-2026-11-20.jsonl': [rec('2026-11-20T11:00:00.000Z', f'/v2/{OTHER}/events', g1)],
}
os.makedirs(D, exist_ok=True)
for name, lines in files.items():
    with open(os.path.join(D, name), 'w') as f:
        f.write('\n'.join(lines) + '\n')
print('\n'.join(f'{k}: {len(v)} lines' for k, v in files.items()))
