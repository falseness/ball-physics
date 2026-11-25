#!/usr/bin/env python3
"""Ball-physics stats report from the GA relay tap's raw copy (TASK-195).

    python3 tools/stats_report.py [--root /var/lib/ga-tap] [--out DIR] [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                                  [--include-test] [--key GAME_KEY]

Reads every tap file found by glob in --root:
  events-<key>-<day>.jsonl   per-key files (tap split, TASK-194), every line counts;
  events-<day>.jsonl         older combined files, only lines whose request path holds <key>.
--since / --until filter on the file's day (inclusive). Test traffic (the record's 'test' flag, or an event
build starting with 'test-') is left out unless --include-test. Lines that are not JSON records, and records
whose body is not a GA body, are counted as 'unparsed' and listed (file:line) - never dropped silently.
Records without a body (GET / OPTIONS preflights) are counted as 'no_body_records'. Events are de-duplicated by event_uuid (an SDK retry can send a batch twice).

Writes DIR/report.json (compact) and DIR/report.md. Event ids: docs/telemetry.md.
"""
import argparse, glob, json, os, re, statistics, sys

BP_KEY = '6254c0dd9e9a91ef0e680ee697f8c1a8'
DAY = r'(\d{4}-\d{2}-\d{2})'
LEVEL_RE = re.compile(r'^level:(\d+):(attempt|win|win_attempt|first_win|fail:offmap|restart|abandon)$')
LINES_RE = re.compile(r'^lines:(\d+):(place|delete|drag|reject_limit|used)$')
UI_RE = re.compile(r'^ui:([a-z_]+):(L\d+|map)$')
SESSION_RE = re.compile(r'^session:(play_seconds|hide|levels_seen)$')
PROG_RE = re.compile(r'^(Start|Complete|Fail):L(\d+)$')
# TASK-236: editor (TASK-232..234) and play-test (TASK-235) events, docs/telemetry.md 'Editor events'
EDITOR_RE = re.compile(r'^editor:([a-z_]+):(L\d+)(?::(.+))?$')
EDITOR_REST = {  # name -> pattern of the parts after <ctx> (None = no more parts)
    'open': r'(menu|win)', 'sum': r'([0-9a-f]{8}):(lines|portals|linek|changed)', 'actions': None, 'exit': None,
    'abandon': None, 'tool': r'(select|line|portal|delete)', 'snap': r'(on|off)', 'rotate': r'(cw|ccw):(flag|portal|line)',
    'portal_size': r'(bigger|smaller)', 'linek': r'(inc|dec)', 'btn': r'(new|play|export|import|exit)',
    'import': r'(ok|invalid|old_format)', 'bar_move': None, 'line': r'(add|cancel)', 'line_move': r'(ok|refused)',
    'line_end': r'(ok|refused|degenerate)', 'line_del': r'(tool|key)', 'portal': r'(a|b)', 'portal_move': r'(ok|refused)',
    'portal_del': None, 'move': r'(ball|flag)', 'error': r'([a-z0-9_]{1,64})'}
EDITOR_NOT_ACTION = ('open', 'sum', 'actions', 'exit', 'abandon', 'error')  # every other editor: event is one action
# TASK-241: first-30-seconds rows (TASK-238..240), docs/telemetry.md 'First 30 seconds'
F30_STEPS = ['first_move', 'first_press', 'point1', 'point2', 'line_drag', 'line_delete', 'reject_limit', 'run', 'pause',
             'offmap', 'restart', 'win', 'menu_open', 'map_open', 'level_change', 'hidden']
F30_TARGETS = ['hud_play', 'hud_menu', 'hud_restart', 'hud_speed', 'bin', 'line_end', 'line', 'ball', 'flag', 'field',
               'menu', 'map', 'other']
LOAD_STAGES = ['html', 'dom', 'onload', 'boot', 'platform', 'storage', 'fonts', 'first_frame', 'transfer_kb', 'resources']
F30_BEATS = [5, 10, 15, 20, 25, 30]
F30_KINDS = ('new', 'ret', 'all')
CTX_KEYS = {'nav': None, 'input': r'(touch|mouse)', 'embed': r'(top|iframe)', 'platform': r'([A-Za-z0-9_.\-]{1,64})',
            'vw': r'(lt480|lt768|lt1024|lt1440|ge1440)', 'visitor': r'(new|ret)'}
LOAD_RE = re.compile(r'^load:(' + '|'.join(LOAD_STAGES) + r')$')
LOAD_NAV_RE = re.compile(r'^load:nav:(navigate|reload|back_forward|prerender)$')
CTX_RE = re.compile(r'^ctx:(input|embed|platform|vw|visitor):(.+)$')
F30_RE = re.compile(r'^f30:(new|ret):(' + '|'.join(F30_STEPS) + r'|end|leave|leave_step:(?:' + '|'.join(F30_STEPS) + r'|none))$')
F30_PRESS_RE = re.compile(r'^f30:press:(' + '|'.join(F30_TARGETS) + r'):(\d{1,2})_(\d{1,2})$')
F30_HB_RE = re.compile(r'^f30:hb:(5|10|15|20|25|30):(moved|idle|visible|step)$')
EDIT_RE = re.compile(r'^edit:([0-9a-f]{8}):(attempt|run|restart|offmap|win|line_place|line_delete|line_drag|speed_on|speed_off|back)$')


def tap_files(root, key, since, until):
    """[(path, day, combined)] sorted by day, per-key before combined on the same day."""
    out = []
    for path in glob.glob(os.path.join(root, 'events-*.jsonl')):
        name = os.path.basename(path)
        m = re.fullmatch(rf'events-{re.escape(key)}-{DAY}\.jsonl', name)
        c = re.fullmatch(rf'events-{DAY}\.jsonl', name)
        if not (m or c):
            continue  # other game keys, 'unknown'
        day = (m or c).group(1)
        if (since and day < since) or (until and day > until):
            continue
        out.append((path, day, bool(c)))
    return sorted(out, key=lambda f: (f[1], f[2], f[0]))


def new_level():
    return {'attempts': 0, 'max_attempt': 0, 'wins': 0, 'first_win_attempt': None, 'first_win_events': 0,
            'win_seconds': [], 'restarts': 0, 'abandons': 0, 'offmap': 0,
            'progression': {'Start': 0, 'Complete': 0, 'Fail': 0},
            'lines': {'place': 0, 'delete': 0, 'drag': 0, 'drag_rejected': 0, 'reject_limit': 0,
                      'runs': 0, 'used_max': 0}}


def new_editor():
    z = lambda *ks: {k: 0 for k in ks}
    return {'sessions': 0, 'opens': z('menu', 'win'), 'exits': 0, 'abandons': 0, 'seconds': 0, 'actions': 0,
            'actions_reported': 0, 'events': {}, 'tools': z('select', 'line', 'portal', 'delete'), 'tool_switches': 0,
            'snap': z('on', 'off'), 'rotate': {}, 'portal_size': z('bigger', 'smaller', 'refused'),
            'linek': z('inc', 'dec'), 'buttons': z('new', 'play', 'export', 'import', 'exit'),
            'imports': z('ok', 'invalid', 'old_format'), 'exports': 0, 'bar_moves': 0,
            'lines': z('added', 'cancelled', 'moved', 'move_refused', 'ends_moved', 'end_refused', 'end_degenerate',
                       'deleted', 'deleted_tool', 'deleted_key'),
            'portals': z('a_placed', 'placed', 'moved', 'move_refused', 'deleted'), 'moves': z('ball', 'flag'),
            'errors': {}, 'hashes_summarised': 0, 'hashes': {},
            'playtest': z('hashes', 'attempts', 'runs', 'wins', 'restarts', 'offmap', 'lines_placed', 'backs')}


def new_hash():
    return {'ctx': [], 'summaries': 0, 'lines': None, 'portals': None, 'linek': None, 'changed': None,
            'playtest': {'attempts': 0, 'max_attempt': 0, 'runs': 0, 'wins': 0, 'win_seconds': [], 'restarts': 0,
                         'offmap': 0, 'lines_placed': 0, 'lines_deleted': 0, 'lines_dragged': 0,
                         'lines_drag_rejected': 0, 'speed_on': 0, 'speed_off': 0, 'backs': 0}}


def editor_event(ed, eid, val, elevels):
    """One editor: / edit: design event into the user's editor record ed; False if the id is not in the catalogue."""
    m = EDIT_RE.match(eid)
    if m:
        h, kind = m.groups()
        pt = ed['hashes'].setdefault(h, new_hash())['playtest']
        if kind == 'attempt':
            pt['attempts'] += 1
            pt['max_attempt'] = max(pt['max_attempt'], int(val or 0))
        elif kind == 'run':
            pt['runs'] += 1
        elif kind == 'restart':
            pt['restarts'] += 1
        elif kind == 'offmap':
            pt['offmap'] += 1
        elif kind == 'win':
            pt['wins'] += 1
            pt['win_seconds'].append(val)
        elif kind == 'line_place':
            pt['lines_placed'] += 1
        elif kind == 'line_delete':
            pt['lines_deleted'] += 1
        elif kind == 'line_drag':
            pt['lines_dragged' if val else 'lines_drag_rejected'] += 1
        elif kind == 'back':
            pt['backs'] += 1
        else:
            pt[kind] += 1  # speed_on / speed_off
        return True
    m = EDITOR_RE.match(eid)
    if not m or m.group(1) not in EDITOR_REST:
        return False
    name, ctx, rest = m.groups()
    pat = EDITOR_REST[name]
    r = None
    if pat is None:
        if rest is not None:
            return False
    else:
        r = re.fullmatch(pat, rest or '')
        if not r:
            return False
    ed['events'][name] = ed['events'].get(name, 0) + 1
    if name not in EDITOR_NOT_ACTION:
        ed['actions'] += 1
    a = r.group(1) if r else None
    if name == 'open':
        ed['sessions'] += 1
        ed['opens'][a] += 1
        lv = elevels.setdefault(ctx, {'opens': 0, 'from': {'menu': 0, 'win': 0}, 'exits': 0, 'abandons': 0, '_users': set()})
        lv['opens'] += 1
        lv['from'][a] += 1
    elif name == 'sum':
        hs = ed['hashes'].setdefault(a, new_hash())
        if ctx not in hs['ctx']:
            hs['ctx'].append(ctx)
        part = r.group(2)
        hs['summaries'] += part == 'lines'
        hs[part] = int(val or 0)  # the latest summary of this hash
    elif name == 'actions':
        ed['actions_reported'] += int(val or 0)
    elif name in ('exit', 'abandon'):
        ed['exits' if name == 'exit' else 'abandons'] += 1
        ed['seconds'] += val or 0
        if ctx in elevels:
            elevels[ctx]['exits' if name == 'exit' else 'abandons'] += 1
    elif name == 'tool':
        ed['tools'][a] += 1
        ed['tool_switches'] += 1
    elif name == 'snap':
        ed['snap'][a] += 1
    elif name == 'rotate':
        ed['rotate'][rest] = ed['rotate'].get(rest, 0) + 1
    elif name == 'portal_size':
        ed['portal_size'][a if val else 'refused'] += 1
    elif name == 'linek':
        ed['linek'][a] += 1
    elif name == 'btn':
        ed['buttons'][a] += 1
        ed['exports'] += a == 'export'
    elif name == 'import':
        ed['imports'][a] += 1
    elif name == 'bar_move':
        ed['bar_moves'] += 1
    elif name == 'line':
        ed['lines']['added' if a == 'add' else 'cancelled'] += 1
    elif name == 'line_move':
        ed['lines']['moved' if a == 'ok' else 'move_refused'] += 1
    elif name == 'line_end':
        ed['lines'][{'ok': 'ends_moved', 'refused': 'end_refused', 'degenerate': 'end_degenerate'}[a]] += 1
    elif name == 'line_del':
        ed['lines']['deleted'] += 1
        ed['lines']['deleted_' + a] += 1
    elif name == 'portal':
        ed['portals']['a_placed' if a == 'a' else 'placed'] += 1
    elif name == 'portal_move':
        ed['portals']['moved' if a == 'ok' else 'move_refused'] += 1
    elif name == 'portal_del':
        ed['portals']['deleted'] += 1
    elif name == 'move':
        ed['moves'][a] += 1
    elif name == 'error':
        ed['errors'][a] = ed['errors'].get(a, 0) + 1
    return True


def new_user():
    return {'first_seen': None, 'last_seen': None, 'inits': 0, 'builds': [], 'sessions': 0, 'session_list': [],
            'levels_tried': [], 'levels': {}, 'buttons': {}, 'button_ctx': {}, 'play_seconds': 0,
            'session_seconds': 0, 'hides': 0, 'levels_seen_max': 0, 'totals': {}}


def is_test(rec, events):
    return bool(rec.get('test')) or any(str(e.get('build', '')).startswith('test-') for e in events)


def build_report(root, key, since=None, until=None, include_test=False):
    files = tap_files(root, key, since, until)
    rep = {'key': key, 'root': root, 'since': since, 'until': until, 'include_test': include_test,
           'files': [os.path.basename(f[0]) for f in files], 'lines': 0, 'records': 0, 'other_key_records': 0, 'no_body_records': 0,
           'excluded_test_records': 0, 'unparsed': 0, 'unparsed_lines': [], 'events': 0, 'duplicate_events': 0,
           'unknown_events': {}, 'users': {}, 'levels': {}}
    users, seen_uuid = {}, set()
    editors, elevels = {}, {}  # TASK-236: user -> editor record; ctx -> editor opens
    sess = {}  # (user, session_id) -> {'build', 'first_ts', 'events', 'play_max', 'length'}
    f30s = {}  # TASK-241: (user, session_id) -> first-30 record (new_f30)

    def user(uid, ts):
        u = users.setdefault(uid, new_user())
        u['first_seen'] = ts if u['first_seen'] is None or ts < u['first_seen'] else u['first_seen']
        u['last_seen'] = ts if u['last_seen'] is None or ts > u['last_seen'] else u['last_seen']
        return u

    def unknown(eid):
        rep['unknown_events'][eid] = rep['unknown_events'].get(eid, 0) + 1

    for path, day, combined in files:
        with open(path, encoding='utf-8', errors='replace') as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                rep['lines'] += 1
                where = f'{os.path.basename(path)}:{n}'
                try:
                    rec = json.loads(line)
                    if not isinstance(rec, dict) or 'path' not in rec:
                        raise ValueError('not a tap record')
                except ValueError:
                    rep['unparsed'] += 1
                    rep['unparsed_lines'].append(where)
                    continue
                if combined and key not in str(rec.get('path', '')):
                    rep['other_key_records'] += 1
                    continue
                body = rec.get('body')
                if body is None:  # GET / OPTIONS (remote_configs preflight): no body to read
                    rep['no_body_records'] += 1
                    continue
                events = body if isinstance(body, list) else []
                if not (isinstance(body, list) and all(isinstance(e, dict) for e in body)) and not (
                        isinstance(body, dict) and 'user_id' in body):
                    rep['unparsed'] += 1  # undecoded / foreign body
                    rep['unparsed_lines'].append(where)
                    continue
                rep['records'] += 1
                if not include_test and is_test(rec, events if events else [body]):
                    rep['excluded_test_records'] += 1
                    continue
                ts = str(rec.get('ts', ''))
                if isinstance(body, dict):  # init (v2 init or remote_configs init)
                    u = user(str(body['user_id']), ts)
                    u['inits'] += 1
                    if body.get('build') and body['build'] not in u['builds']:
                        u['builds'].append(body['build'])
                    continue
                for e in events:
                    uuid = e.get('event_uuid')
                    if uuid:
                        if uuid in seen_uuid:
                            rep['duplicate_events'] += 1
                            continue
                        seen_uuid.add(uuid)
                    if 'user_id' not in e:
                        unknown('<no user_id>')
                        continue
                    rep['events'] += 1
                    uid = str(e['user_id'])
                    u = user(uid, ts)
                    build = str(e.get('build', ''))
                    if build and build not in u['builds']:
                        u['builds'].append(build)
                    sid = str(e.get('session_id', ''))
                    s = sess.setdefault((uid, sid), {'session_id': sid, 'build': build, 'first_ts': ts,
                                                      'events': 0, 'play_max': 0, 'length': 0})
                    s['events'] += 1
                    cat, eid, val = e.get('category'), str(e.get('event_id', '')), e.get('value')
                    if cat == 'user':
                        continue
                    if cat == 'session_end':
                        s['length'] = max(s['length'], int(e.get('length') or 0))
                        continue
                    if cat == 'progression':
                        m = PROG_RE.match(eid)
                        if not m:
                            unknown(eid)
                            continue
                        lv = u['levels'].setdefault(m.group(2), new_level())
                        lv['progression'][m.group(1)] += 1
                        continue
                    if cat != 'design':
                        unknown(f'{cat}:{eid}')
                        continue
                    m = LEVEL_RE.match(eid)
                    if m:
                        lv = u['levels'].setdefault(m.group(1), new_level())
                        kind = m.group(2)
                        if kind == 'attempt':
                            lv['attempts'] += 1
                            lv['max_attempt'] = max(lv['max_attempt'], int(val or 0))
                        elif kind == 'win':
                            lv['wins'] += 1
                            lv['win_seconds'].append(val)
                        elif kind == 'win_attempt':
                            v = int(val or 0)
                            lv['first_win_attempt'] = v if lv['first_win_attempt'] is None else min(lv['first_win_attempt'], v)
                        elif kind == 'first_win':
                            lv['first_win_events'] += 1
                        elif kind == 'fail:offmap':
                            lv['offmap'] += 1
                        elif kind == 'restart':
                            lv['restarts'] += 1
                        elif kind == 'abandon':
                            lv['abandons'] += 1
                        continue
                    m = LINES_RE.match(eid)
                    if m:
                        ln = u['levels'].setdefault(m.group(1), new_level())['lines']
                        kind = m.group(2)
                        if kind == 'drag':
                            ln['drag' if val else 'drag_rejected'] += 1
                        elif kind == 'used':
                            ln['runs'] += 1
                            ln['used_max'] = max(ln['used_max'], int(val or 0))
                        else:
                            ln[kind] += 1
                        continue
                    m = UI_RE.match(eid)
                    if m:
                        u['buttons'][m.group(1)] = u['buttons'].get(m.group(1), 0) + 1
                        bc = u['button_ctx'].setdefault(m.group(1), {})
                        bc[m.group(2)] = bc.get(m.group(2), 0) + 1
                        continue
                    m = SESSION_RE.match(eid)
                    if m:
                        if m.group(1) == 'play_seconds':
                            s['play_max'] = max(s['play_max'], int(val or 0))
                        elif m.group(1) == 'hide':
                            u['hides'] += 1
                        else:
                            u['levels_seen_max'] = max(u['levels_seen_max'], int(val or 0))
                        continue
                    if eid.startswith(('load:', 'ctx:', 'f30:')):  # TASK-241
                        if first30_event(f30s.setdefault((uid, sid), new_f30()), eid, val):
                            continue
                    if eid.startswith(('editor:', 'edit:')):
                        ed = editors.get(uid) or new_editor()
                        if editor_event(ed, eid, val, elevels):
                            editors[uid] = ed
                            if eid.startswith('editor:open:'):
                                elevels[eid.split(':')[2]]['_users'].add(uid)
                            continue
                    unknown(eid)

    for (uid, sid), s in sess.items():
        u = users[uid]
        u['session_list'].append({'session_id': s['session_id'], 'build': s['build'], 'first_ts': s['first_ts'],
                                  'events': s['events'], 'play_seconds': s['play_max'], 'length': s['length']})
        u['play_seconds'] += s['play_max']
        u['session_seconds'] += s['length']
    num = lambda k: (int(k) if k.isdigit() else 1 << 30, k)
    levels = {}
    for uid, u in users.items():
        u['session_list'].sort(key=lambda s: (s['first_ts'], s['session_id']))
        u['sessions'] = len(u['session_list'])
        u['levels'] = {k: u['levels'][k] for k in sorted(u['levels'], key=num)}
        u['levels_tried'] = [int(k) for k, lv in u['levels'].items() if lv['attempts'] > 0]
        u['buttons'] = dict(sorted(u['buttons'].items()))
        u['button_ctx'] = {b: dict(sorted(c.items())) for b, c in sorted(u['button_ctx'].items())}
        t = {k: 0 for k in ('attempts', 'wins', 'restarts', 'abandons', 'offmap', 'lines_place', 'lines_delete',
                            'lines_drag', 'lines_drag_rejected', 'lines_reject_limit', 'buttons')}
        for k, lv in u['levels'].items():
            for f in ('attempts', 'wins', 'restarts', 'abandons', 'offmap'):
                t[f] += lv[f]
            for f in ('place', 'delete', 'drag', 'drag_rejected', 'reject_limit'):
                t['lines_' + f] += lv['lines'][f]
            agg = levels.setdefault(k, {'users_tried': 0, 'users_won': 0, 'attempts': 0, 'wins': 0, 'restarts': 0,
                                        'abandons': 0, 'offmap': 0, 'lines_place': 0, '_first': []})
            agg['users_tried'] += lv['attempts'] > 0
            agg['users_won'] += lv['wins'] > 0
            for f in ('attempts', 'wins', 'restarts', 'abandons', 'offmap'):
                agg[f] += lv[f]
            agg['lines_place'] += lv['lines']['place']
            if lv['first_win_attempt'] is not None:
                agg['_first'].append(lv['first_win_attempt'])
        t['buttons'] = sum(u['buttons'].values())
        u['totals'] = t
    for k, agg in levels.items():
        first = agg.pop('_first')
        agg['win_rate'] = round(agg['wins'] / agg['attempts'], 4) if agg['attempts'] else None
        agg['median_attempts_to_first_win'] = statistics.median(first) if first else None
    rep['users'] = {uid: users[uid] for uid in sorted(users, key=lambda i: (users[i]['first_seen'] or '', i))}
    rep['levels'] = {k: levels[k] for k in sorted(levels, key=num)}
    rep['unknown_events'] = dict(sorted(rep['unknown_events'].items()))
    rep['editor'] = editor_section(editors, elevels, list(rep['users']))
    rep['first30'] = first30_section([f for f in f30s.values() if f['any']])
    return rep


def new_f30():
    return {'any': False, 'kind': None, 'load': {}, 'ctx': {}, 'steps': {}, 'end': None, 'leave': None,
            'leave_step': None, 'presses': [], 'hb': {}}


def first30_event(f, eid, val):
    """TASK-241: one load: / ctx: / f30: design event into the session's first-30 record; False if not in the catalogue.
    A page load sends each id once; a repeated id in the same session keeps its first value (presses are all kept)."""
    num = val if isinstance(val, (int, float)) and not isinstance(val, bool) else None
    m = LOAD_RE.match(eid)
    if m:
        if num is None:
            return False
        f['load'].setdefault(m.group(1), num)
    elif LOAD_NAV_RE.match(eid):
        f['ctx'].setdefault('nav', eid.split(':')[2])
    elif CTX_RE.match(eid):
        key, v = CTX_RE.match(eid).groups()
        if not re.fullmatch(CTX_KEYS[key], v):
            return False
        f['ctx'].setdefault(key, v)
        if key == 'visitor':
            f['kind'] = v
    elif F30_PRESS_RE.match(eid):
        t, gx, gy = F30_PRESS_RE.match(eid).groups()
        if num is None:
            return False
        f['presses'].append((t, f'{int(gx)}_{int(gy)}', num))
    elif F30_HB_RE.match(eid):
        s, part = F30_HB_RE.match(eid).groups()
        if num is None:
            return False
        f['hb'].setdefault(int(s), {}).setdefault(part, num)
    elif F30_RE.match(eid):
        k, what = F30_RE.match(eid).groups()
        if what.startswith('leave_step:'):
            if f['leave_step'] is None:
                f['leave_step'] = what.split(':')[1]
        else:
            if num is None:
                return False
            if what in ('end', 'leave'):
                f[what] = num if f[what] is None else f[what]
            else:
                f['steps'].setdefault(what, num)
        f['kind'] = f['kind'] or k  # ctx:visitor wins (sent first, at t0)
    else:
        return False
    f['any'] = True
    return True


def pct(n, d):
    return round(n / d, 4) if d else None


def rank_pct(vals, q):
    """Nearest-rank percentile of a sorted list: the value at rank ceil(q * n) (1-based); None for no values."""
    if not vals:
        return None
    r = -(-q * len(vals) // 1)  # ceil
    return vals[max(1, int(r)) - 1]


def med(vals):
    """statistics.median; a whole number as an int (1900, not 1900.0); None for no values"""
    if not vals:
        return None
    m = statistics.median(vals)
    return int(m) if m == int(m) else m


def first30_section(recs):
    """TASK-241: report['first30'] = {'steps', 'targets', 'kinds': {new, ret, all}} over sessions with a first-30 row."""
    out = {'steps': F30_STEPS, 'targets': F30_TARGETS, 'kinds': {}}
    for kind in F30_KINDS:
        rs = [f for f in recs if kind == 'all' or f['kind'] == kind]
        ff = sum(1 for f in rs if 'first_frame' in f['load'])
        k = {'sessions': len(rs), 'first_frame_sessions': ff}
        # load stages: -1 (not measurable) counted as missing, left out of the statistics
        k['load'] = {}
        for st in LOAD_STAGES:
            v = sorted(f['load'][st] for f in rs if st in f['load'] and f['load'][st] >= 0)
            k['load'][st] = {'count': len(v), 'missing': sum(1 for f in rs if st in f['load'] and f['load'][st] < 0),
                             'median': med(v), 'p75': rank_pct(v, 0.75), 'p90': rank_pct(v, 0.9)}
        k['context'] = {}
        for key in CTX_KEYS:
            c = {}
            for f in rs:
                if key in f['ctx']:
                    c[f['ctx'][key]] = c.get(f['ctx'][key], 0) + 1
            k['context'][key] = dict(sorted(c.items()))
        # funnel: sessions that reached each step, share of the first-frame sessions, conversion from the previous
        # step (first step: from the first-frame sessions), median ms since t0
        k['funnel'], prev = [], ff
        for i, st in enumerate(F30_STEPS, 1):
            v = sorted(f['steps'][st] for f in rs if st in f['steps'])
            k['funnel'].append({'index': i, 'step': st, 'sessions': len(v), 'pct': pct(len(v), ff),
                                'conversion': pct(len(v), prev), 'median_ms': med(v)})
            prev = len(v)
        ends = {}
        for f in rs:
            if f['end'] is not None:
                ends[f['end']] = ends.get(f['end'], 0) + 1
        k['end'] = {'sessions': sum(ends.values()), 'furthest': {str(e): n for e, n in sorted(ends.items())}}
        lv = [f for f in rs if f['leave'] is not None]
        by_step = {}
        for f in lv:
            by_step[f['leave_step'] or 'none'] = by_step.get(f['leave_step'] or 'none', 0) + 1
        buckets = {f'{b}_{b + 5}': 0 for b in range(0, 30, 5)}
        for f in lv:
            b = min(25, max(0, int(f['leave'] // 5000) * 5))
            buckets[f'{b}_{b + 5}'] += 1
        k['leaves'] = {'count': len(lv), 'by_step': dict(sorted(by_step.items())), 'by_bucket': buckets}
        # presses: per target the total and the top 20 cells (count desc, then cell); field presses made before the
        # session's point1 (or with no point1) and whether point1 followed within 2 s
        by_t, cells = {}, {}
        field = {'presses': 0, 'before_point1': 0, 'no_point1_2s': 0}
        for f in rs:
            p1 = f['steps'].get('point1')
            for t, cell, ms in f['presses']:
                by_t[t] = by_t.get(t, 0) + 1
                cells.setdefault(t, {})[cell] = cells.setdefault(t, {}).get(cell, 0) + 1
                if t == 'field':
                    field['presses'] += 1
                    if p1 is None or ms <= p1:
                        field['before_point1'] += 1
                        field['no_point1_2s'] += not (p1 is not None and p1 - ms <= 2000)
        k['presses'] = {'total': sum(by_t.values()), 'by_target': dict(sorted(by_t.items())),
                        'top_cells': {t: [[c, n] for c, n in sorted(cells[t].items(), key=lambda x: (-x[1], x[0]))[:20]]
                                      for t in sorted(cells)},
                        'field': field}
        k['heartbeat'] = {}
        for b in F30_BEATS:
            hs = [f['hb'][b] for f in rs if b in f['hb']]
            idle = sorted(h['idle'] for h in hs if 'idle' in h)
            over = sum(1 for x in idle if x > 10000)
            k['heartbeat'][str(b)] = {'sessions': len(hs), 'moved_median': med(sorted(h['moved'] for h in hs if 'moved' in h)),
                                      'idle_median': med(idle), 'idle_over_10s': over, 'idle_over_10s_share': pct(over, len(idle)),
                                      'not_visible': sum(1 for h in hs if h.get('visible') == 0)}
        out['kinds'][kind] = k
    return out


def editor_section(editors, elevels, order):
    """TASK-236: per user (users with an editor: / edit: event, in report order) and per base level (ctx)."""
    out = {}
    for uid in [u for u in order if u in editors]:
        ed = editors[uid]
        ed['events'] = dict(sorted(ed['events'].items()))
        ed['rotate'] = dict(sorted(ed['rotate'].items()))
        ed['errors'] = dict(sorted(ed['errors'].items()))
        ed['hashes'] = dict(sorted(ed['hashes'].items()))
        ed['hashes_summarised'] = sum(1 for h in ed['hashes'].values() if h['summaries'])
        t = ed['playtest']
        for h in ed['hashes'].values():
            pt = h['playtest']
            t['hashes'] += pt['attempts'] > 0
            for k in ('attempts', 'runs', 'wins', 'restarts', 'offmap', 'lines_placed', 'backs'):
                t[k] += pt[k]
        out[uid] = ed
    levels = {}
    for ctx in sorted(elevels, key=lambda c: int(c[1:])):
        lv = elevels[ctx]
        levels[ctx] = {'opens': lv['opens'], 'from': lv['from'], 'users': len(lv['_users']), 'exits': lv['exits'],
                       'abandons': lv['abandons']}
    return {'users': out, 'levels': levels}


def markdown(rep):
    o = [f"# Ball-physics stats", '',
         f"key `{rep['key']}`, days {rep['since'] or 'all'} .. {rep['until'] or 'all'}, "
         f"test traffic {'included' if rep['include_test'] else 'excluded'}", '',
         f"files {len(rep['files'])}, lines {rep['lines']}, records {rep['records']} "
         f"(other key {rep['other_key_records']}, no body {rep['no_body_records']}, excluded test {rep['excluded_test_records']}), "
         f"events {rep['events']}, duplicates {rep['duplicate_events']}, **unparsed {rep['unparsed']}**", '']
    if rep['unparsed_lines']:
        o += ['Unparsed lines: ' + ', '.join(rep['unparsed_lines'][:50]) +
              (' ...' if len(rep['unparsed_lines']) > 50 else ''), '']
    if rep['unknown_events']:
        o += ['Unknown events: ' + ', '.join(f'`{k}` {v}' for k, v in rep['unknown_events'].items()), '']
    o += ['## Levels', '', '| srcId | users tried | users won | attempts | wins | win rate | median attempts to first win '
          '| restarts | abandons | off-map | lines placed |', '|' + '---|' * 11]
    for k, a in rep['levels'].items():
        o.append(f"| {k} | {a['users_tried']} | {a['users_won']} | {a['attempts']} | {a['wins']} | {a['win_rate']} | "
                 f"{a['median_attempts_to_first_win']} | {a['restarts']} | {a['abandons']} | {a['offmap']} | {a['lines_place']} |")
    o += ['', f"## Users ({len(rep['users'])})", '']
    for uid, u in rep['users'].items():
        t = u['totals']
        o += [f"### `{uid}`", '',
              f"seen {u['first_seen']} .. {u['last_seen']}, builds {', '.join(u['builds']) or '-'}, inits {u['inits']}, "
              f"sessions {u['sessions']}, play seconds {u['play_seconds']} (milestones), session seconds "
              f"{u['session_seconds']}, hides {u['hides']}, levels seen max {u['levels_seen_max']}", '',
              f"levels tried {u['levels_tried']}; attempts {t['attempts']}, wins {t['wins']}, restarts {t['restarts']}, "
              f"abandons {t['abandons']}, off-map {t['offmap']}; lines placed {t['lines_place']}, deleted "
              f"{t['lines_delete']}, dragged {t['lines_drag']} (+{t['lines_drag_rejected']} rejected), over limit "
              f"{t['lines_reject_limit']}; button clicks {t['buttons']}", '']
        if u['session_list']:
            o += ['| session | build | first ts | events | play s | length s |', '|---|---|---|---|---|---|']
            o += [f"| `{s['session_id']}` | {s['build']} | {s['first_ts']} | {s['events']} | {s['play_seconds']} | {s['length']} |"
                  for s in u['session_list']] + ['']
        if u['levels']:
            o += ['| srcId | attempts | max attempt # | wins | first win attempt | win s | restarts | abandons | off-map '
                  '| Start/Complete/Fail | placed | deleted | dragged | drag rejected | over limit | runs | max used |',
                  '|' + '---|' * 17]
            for k, lv in u['levels'].items():
                p, ln = lv['progression'], lv['lines']
                o.append(f"| {k} | {lv['attempts']} | {lv['max_attempt']} | {lv['wins']} | {lv['first_win_attempt']} | "
                         f"{lv['win_seconds']} | {lv['restarts']} | {lv['abandons']} | {lv['offmap']} | "
                         f"{p['Start']}/{p['Complete']}/{p['Fail']} | {ln['place']} | {ln['delete']} | {ln['drag']} | "
                         f"{ln['drag_rejected']} | {ln['reject_limit']} | {ln['runs']} | {ln['used_max']} |")
            o.append('')
        if u['buttons']:
            o += ['Buttons: ' + ', '.join(f"{b} {c}" for b, c in u['buttons'].items()), '']
    o += editor_markdown(rep.get('editor') or {'users': {}, 'levels': {}})
    o += first30_markdown(rep.get('first30') or first30_section([]))
    return '\n'.join(o) + '\n'


def editor_markdown(ed):
    kv = lambda d: ', '.join(f'{k} {v}' for k, v in d.items()) or '-'
    o = ['## Editor', '', f"users {len(ed['users'])}, editor sessions {sum(e['sessions'] for e in ed['users'].values())}", '',
         '| base level | opens | from menu | from win | users | exits | abandons |', '|' + '---|' * 7]
    for ctx, lv in ed['levels'].items():
        o.append(f"| {ctx} | {lv['opens']} | {lv['from']['menu']} | {lv['from']['win']} | {lv['users']} | {lv['exits']} | "
                 f"{lv['abandons']} |")
    o.append('')
    for uid, e in ed['users'].items():
        ln, pr, pt = e['lines'], e['portals'], e['playtest']
        o += [f"### Editor `{uid}`", '',
              f"sessions {e['sessions']} (menu {e['opens']['menu']}, win {e['opens']['win']}), exits {e['exits']}, "
              f"abandons {e['abandons']}, seconds {e['seconds']}, actions {e['actions']} (reported {e['actions_reported']})", '',
              f"- events: {kv(e['events'])}",
              f"- tools: {kv(e['tools'])} (switches {e['tool_switches']}); snap {kv(e['snap'])}; rotate {kv(e['rotate'])}; "
              f"portal size {kv(e['portal_size'])}; lines limit {kv(e['linek'])}; toolbar moves {e['bar_moves']}",
              f"- buttons: {kv(e['buttons'])}; imports {kv(e['imports'])}; exports {e['exports']}",
              f"- lines: added {ln['added']} (cancelled {ln['cancelled']}), moved {ln['moved']} (refused {ln['move_refused']}), "
              f"ends moved {ln['ends_moved']} (refused {ln['end_refused']}, degenerate {ln['end_degenerate']}), deleted "
              f"{ln['deleted']} (tool {ln['deleted_tool']}, key {ln['deleted_key']})",
              f"- portals: placed {pr['placed']} (A only {pr['a_placed']}), moved {pr['moved']} (refused {pr['move_refused']}), "
              f"deleted {pr['deleted']}; ball moved {e['moves']['ball']}, flag moved {e['moves']['flag']}",
              f"- errors: {kv(e['errors'])}",
              f"- level hashes summarised {e['hashes_summarised']}; play-tests: {kv(pt)}", '']
        if e['hashes']:
            o += ['| hash | ctx | summaries | lines | portals | lineK | changed | attempts | max attempt # | runs | wins | win s '
                  '| restarts | off-map | placed | deleted | dragged | drag rejected | speed on/off | back |', '|' + '---|' * 20]
            for h, x in e['hashes'].items():
                p = x['playtest']
                o.append(f"| `{h}` | {','.join(x['ctx']) or '-'} | {x['summaries']} | {x['lines']} | {x['portals']} | "
                         f"{x['linek']} | {x['changed']} | {p['attempts']} | {p['max_attempt']} | {p['runs']} | {p['wins']} | "
                         f"{p['win_seconds']} | {p['restarts']} | {p['offmap']} | {p['lines_placed']} | {p['lines_deleted']} | "
                         f"{p['lines_dragged']} | {p['lines_drag_rejected']} | {p['speed_on']}/{p['speed_off']} | {p['backs']} |")
            o.append('')
    return o


def first30_markdown(f3):
    """TASK-241: '## First 30 seconds', one subsection per kind (new / ret / all)."""
    kv = lambda d: ', '.join(f'{k} {v}' for k, v in d.items()) or '-'
    na = lambda v: '-' if v is None else v
    pc = lambda v: '-' if v is None else f'{v * 100:.1f}%'
    o = ['## First 30 seconds', '', 'Sessions with a load: / ctx: / f30: event, split by visitor kind (`new` = first-ever '
         'session). Times in ms (load stages since navigation start, steps since t0). Funnel: % of the sessions with a '
         'first frame; conversion = sessions at this step / sessions at the previous step (steps are not nested, so it '
         'can exceed 1). Percentiles: nearest rank.', '']
    for kind, k in f3['kinds'].items():
        o += [f'### First 30 s: {kind}', '', f"sessions {k['sessions']}, with a first frame {k['first_frame_sessions']}", '',
              '| load stage | count | missing (-1) | median | p75 | p90 |', '|' + '---|' * 6]
        o += [f"| {st} | {x['count']} | {x['missing']} | {na(x['median'])} | {na(x['p75'])} | {na(x['p90'])} |"
              for st, x in k['load'].items()]
        o += [''] + [f'- {key}: {kv(c)}' for key, c in k['context'].items()] + [
            '', '| # | step | sessions | % of first-frame sessions | conversion from previous | median ms |', '|' + '---|' * 6]
        o += [f"| {x['index']} | {x['step']} | {x['sessions']} | {pc(x['pct'])} | {pc(x['conversion'])} | {na(x['median_ms'])} |"
              for x in k['funnel']]
        lv, pr = k['leaves'], k['presses']
        o += ['', f"end at 30 s: {k['end']['sessions']} sessions, furthest index {kv(k['end']['furthest'])}",
              f"leaves: {lv['count']}; by last step: {kv(lv['by_step'])}; by 5 s bucket: {kv(lv['by_bucket'])}",
              f"presses: {pr['total']}; by target: {kv(pr['by_target'])}; field presses {pr['field']['presses']}, before "
              f"point1 {pr['field']['before_point1']}, not followed by point1 within 2 s {pr['field']['no_point1_2s']}"]
        o += [f"- top cells {t}: " + ', '.join(f'{c} ({n})' for c, n in cells) for t, cells in pr['top_cells'].items()]
        o += ['', '| beat s | sessions | median moved px | median idle ms | idle > 10 s | share idle > 10 s | hidden |',
              '|' + '---|' * 7]
        o += [f"| {b} | {x['sessions']} | {na(x['moved_median'])} | {na(x['idle_median'])} | {x['idle_over_10s']} | "
              f"{pc(x['idle_over_10s_share'])} | {x['not_visible']} |" for b, x in k['heartbeat'].items()]
        o.append('')
    return o


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default='/var/lib/ga-tap')
    ap.add_argument('--key', default=BP_KEY)
    ap.add_argument('--out', default='stats_report')
    ap.add_argument('--since')
    ap.add_argument('--until')
    ap.add_argument('--include-test', action='store_true')
    a = ap.parse_args(argv)
    for d in (a.since, a.until):
        if d and not re.fullmatch(DAY, d):
            ap.error(f'day must be YYYY-MM-DD: {d}')
    rep = build_report(a.root, a.key, a.since, a.until, a.include_test)
    if not rep['files']:
        print(f'no tap files for key {a.key} in {a.root}', file=sys.stderr)
        return 1
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'report.json'), 'w') as f:
        json.dump(rep, f, separators=(',', ':'))
    with open(os.path.join(a.out, 'report.md'), 'w') as f:
        f.write(markdown(rep))
    print(f"files {len(rep['files'])} records {rep['records']} events {rep['events']} users {len(rep['users'])} "
          f"levels {len(rep['levels'])} excluded_test {rep['excluded_test_records']} unparsed {rep['unparsed']} "
          f"-> {a.out}/report.json, report.md")
    return 0


if __name__ == '__main__':
    sys.exit(main())
