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
    sess = {}  # (user, session_id) -> {'build', 'first_ts', 'events', 'play_max', 'length'}

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
    return rep


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
    return '\n'.join(o) + '\n'


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
