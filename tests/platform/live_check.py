"""Live delivery check through the GameAnalytics relay (TASK-193).

Plays the telemetry_ui (default) or telemetry_editor (--scenario, TASK-237) script of tests/visual/shoot.py headless with the committed gameanalytics backend (index.html
as committed; js/buildinfo.js served stamped with 'live-<YYYYMMDD>', so an automated browser sends build
'test-live-<YYYYMMDD>'), waits for every relay answer, then reads the relay tap's raw copy
(/var/lib/ga-tap/events-<game key>-<UTC day>.jsonl, split per key since TASK-194; the tap names a file by its own
UTC write time, so every day file from the day at start through the day after the run is read - a run that crosses
UTC midnight finds its later events in the next day's file, TASK-230): lines whose path holds the ball-physics game key and whose body events carry
this build. The design + progression events in the tap must equal the ones the browser sent (ANALYTICS.debugLog).

With --scenario telemetry_first30 (TASK-242) a real-clock first-30 session is played instead of shoot's page.clock
script (the SDK's send timer needs real time): visitor 1 (new) presses / moves / draws a line by mouse and taps by touch
and stays past t0 + 30 s (heartbeats + end), then pagehide; visitor 2 (ret, visitor 1's localStorage carried over) presses once and
leaves at ~4 s (leave + leave_step). live.json 'first30' = the load:/ctx:/f30: design ids sent vs found in the tap
(ids and counts, not values: the clock is real).

Usage: python3 tests/platform/live_check.py --out DIR [--scenario telemetry_ui|telemetry_editor|telemetry_first30] [--build NAME] [--tap-dir DIR]
  --build  stamped build (default 'live-<YYYYMMDD>' UTC); a preview uses e.g. 'livepre-<YYYYMMDD>' so its events
           stay out of the proof build's count
Writes DIR/live.json and DIR/live_excerpt.jsonl (5 tap lines as recorded), DIR/sequence.json (telemetry_ui) or
DIR/sequence_editor.json + the other telemetry_editor files (telemetry_editor). With telemetry_editor live.json also
holds 'editor': the editor:/edit: design ids the browser sent vs the ones found in the tap (counted from the tap file).
Exit 0 only when every check passes.
"""
import argparse
import datetime
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tests', 'visual'))
import shoot  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

RELAY = 'stats.playdiplomacy.online'
KEYS = '/root/credentials/ball-physics/gameanalytics.json'
GAME_CATEGORIES = ('design', 'progression')
WAIT_STEPS = {'telemetry_ui': ('touch menu_open', 'map_close'),
              # editor open, nothing running: the SDK's timer sends the batch so far
              'telemetry_editor': ('export', 'import x3', 'portals'),
              'telemetry_first30': ()}  # the first visitor's 30 s window already spans several SDK send timers
EDITOR_PREFIXES = ('editor:', 'edit:')
FIRST30_PREFIXES = ('load:', 'ctx:', 'f30:')


def sc_first30_live(page, info):
    """TASK-242: real-clock first-30 session (two visitors) for the live relay check; writes sequence_first30_live.json."""
    errors, logs, vis = [], [], {}
    since = "TELEMETRY.sinceT0()"

    def wait_t(p, ms):
        p.wait_for_function("t => TELEMETRY.sinceT0() !== null && TELEMETRY.sinceT0() >= t", arg=ms, timeout=ms + 30000, polling=100)

    (x1, y1), (x2, y2) = shoot.LINE_X
    with shoot.telemetry_page(page, errors, has_touch=True) as p:
        wait_t(p, 0)
        shoot.move(p, 300, 650)
        wait_t(p, 1000)
        shoot.click(p, *p.evaluate("[ball.posX, ball.posY]"))  # press on the ball
        wait_t(p, 2000)
        shoot.click(p, x1, y1)  # point 1
        wait_t(p, 3000)
        shoot.move(p, x2, y2)
        shoot.click(p, x2, y2)  # point 2: the line is placed, auto-run
        cdp = p.context.new_cdp_session(p)
        cx, cy = shoot.to_client(p, 300, 700)
        wait_t(p, 4000)
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': cx, 'y': cy}]})
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        wait_t(p, 31500)  # past the 30 s beat and 'end'
        p.evaluate(shoot.F30_PAGEHIDE_JS)
        vis['1'] = {'visitor': p.evaluate("TELEMETRY.firstVisitor()"), 'sinceT0': p.evaluate(since)}
        logs.append(p.evaluate(shoot.FULL_LOG_JS))
        # each telemetry_page serves on its own port (own origin): carry visitor 1's localStorage (bp.first.v1 via
        # PLATFORM.storage, the SDK's user id) into visitor 2's origin before its first load
        stored = p.evaluate("() => Object.fromEntries(Object.keys(localStorage).map(k => [k, localStorage.getItem(k)]))")

    def carry(p):
        p.add_init_script("(s => { if (!sessionStorage.getItem('__carried')) { for (const k in s) localStorage.setItem(k, s[k]);"
                          " sessionStorage.setItem('__carried', '1') } })(%s)" % json.dumps(stored))
    with shoot.telemetry_page(page, errors, has_touch=True, init=carry) as p:
        wait_t(p, 1000)
        shoot.click(p, 300, 700)  # field press
        wait_t(p, 4000)
        p.evaluate(shoot.F30_PAGEHIDE_JS)  # leave inside the window
        vis['2'] = {'visitor': p.evaluate("TELEMETRY.firstVisitor()"), 'sinceT0': p.evaluate(since)}
        logs.append(p.evaluate(shoot.FULL_LOG_JS))
    shoot.TELEMETRY_LOGS['telemetry_first30'] = logs[0] + logs[1]
    ids = [[str(e[1]) for e in lg if e[0] == 'addDesignEvent' and str(e[1]).startswith(FIRST30_PREFIXES)] for lg in logs]
    seq = {'visitors': vis, 'ids': ids, 'errors': errors, 'clock': 'real'}
    need = {'1': ['ctx:visitor:new', 'f30:new:first_press', 'f30:new:point1', 'f30:new:point2', 'f30:new:run', 'f30:new:end',
                  'f30:hb:30:step'],
            '2': ['ctx:visitor:ret', 'f30:ret:first_press', 'f30:ret:leave']}
    seq['checks'] = {'visitors': vis['1']['visitor'] == 'new' and vis['2']['visitor'] == 'ret',
                     'steps': all(i in ids[int(n) - 1] for n, l in need.items() for i in l),
                     'touchPress': any(i.startswith('f30:press:field:') for i in ids[0][ids[0].index('f30:new:run'):])
                     if 'f30:new:run' in ids[0] else False,
                     'leaveStep': any(i.startswith('f30:ret:leave_step:') for i in ids[1]),
                     'noConsoleErrors': not errors}
    seq['pass'] = all(seq['checks'].values())
    with open(os.path.join(shoot.OUT_DIR, 'sequence_first30_live.json'), 'w') as f:
        json.dump(seq, f, separators=(',', ':'))
    if not seq['pass']:
        raise RuntimeError('first30 live session: %s' % [k for k, v in seq['checks'].items() if not v])


SCENARIOS = {'telemetry_ui': shoot.sc_telemetry_ui, 'telemetry_editor': shoot.sc_telemetry_editor,
             'telemetry_first30': sc_first30_live}
SEQ_FILES = {'telemetry_ui': 'sequence.json', 'telemetry_editor': 'sequence_editor.json',
             'telemetry_first30': 'sequence_first30_live.json'}


def tap_lines(tap_file, key, build):
    out = []
    if not os.path.exists(tap_file):
        return out
    with open(tap_file) as f:
        for raw in f:
            if key not in raw or build not in raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            body = rec.get('body')
            if key in rec.get('path', '') and isinstance(body, list) and any(
                    isinstance(e, dict) and e.get('build') == build for e in body):
                out.append((raw.rstrip('\n'), rec))
    return out


def tap_files(tap_dir, key, start, end):
    """Tap files of every UTC day from start's day through end's day, and at least the day after start."""
    d, last = start.date(), max(end.date(), start.date() + datetime.timedelta(days=1))
    out = []
    while d <= last:
        out.append(os.path.join(tap_dir, 'events-%s-%s.jsonl' % (key, d.strftime('%Y-%m-%d'))))
        d += datetime.timedelta(days=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    day = datetime.datetime.now(datetime.timezone.utc)
    ap.add_argument('--build', default='live-' + day.strftime('%Y%m%d'))
    ap.add_argument('--tap-dir', default='/var/lib/ga-tap')
    ap.add_argument('--scenario', default='telemetry_ui', choices=sorted(SCENARIOS))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    key = json.load(open(KEYS))['gameKey']
    with open(os.path.join(ROOT, 'analytics', 'backends', 'gameanalytics.js')) as f:
        committed_key = key in f.read()
    want_build = 'test-' + args.build
    before_counts = {f: len(tap_lines(f, key, want_build)) for f in tap_files(args.tap_dir, key, day, day)}
    before = sum(before_counts.values())

    requests, responses = [], []

    def opened(p):
        p.on('request', lambda r: RELAY in r.url and requests.append({'method': r.method, 'url': r.url}))
        p.on('response', lambda r: RELAY in r.url and responses.append({'url': r.url, 'status': r.status}))
        p.on('requestfailed', lambda r: RELAY in r.url and responses.append(
            {'url': r.url, 'status': 0, 'failure': r.failure}))

    def closing(p):
        # every relay request answered and quiet for 3 s (keepalive /e POSTs of the pagehide flush), 60 s at most
        t0 = time.time()
        last = (len(requests), len(responses))
        quiet = time.time()
        while time.time() - t0 < 60:
            p.wait_for_timeout(250)
            now = (len(requests), len(responses))
            if now != last:
                last, quiet = now, time.time()
            if now[0] == now[1] and time.time() - quiet >= 3:
                break

    def step(p, name):
        # menu / map open (no active play time): wait past the SDK's 8 s send timer so the events of the run
        # reach the relay in several batches, not only in the pagehide flush
        if name in WAIT_STEPS[args.scenario]:
            p.wait_for_timeout(9000)

    shoot.TELEMETRY_STEP_HOOK = step
    shoot.TELEMETRY_BACKEND = 'gameanalytics'
    shoot.TELEMETRY_BUILD = args.build
    shoot.TELEMETRY_PAGE_HOOK = opened
    shoot.TELEMETRY_CLOSE_HOOK = closing
    shoot.OUT_DIR = args.out
    info, error = {}, None
    t0 = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=shoot.VIEWPORT)
        try:
            SCENARIOS[args.scenario](page, info)
        except Exception as e:
            error = '%s: %s' % (type(e).__name__, e)
        browser.close()
    run_seconds = round(time.time() - t0, 1)

    full = shoot.TELEMETRY_LOGS.get(args.scenario, [])
    sent = [e for e in full if e[0] in ('addDesignEvent', 'addProgressionEvent')]
    sent_counts = {'design': sum(e[0] == 'addDesignEvent' for e in sent),
                   'progression': sum(e[0] == 'addProgressionEvent' for e in sent)}

    # the tap writes as the relay answers; give it a moment, then read
    time.sleep(2)
    files = tap_files(args.tap_dir, key, day, datetime.datetime.now(datetime.timezone.utc))
    new_lines = [ln for f in files for ln in tap_lines(f, key, want_build)[before_counts.get(f, 0):]]
    events = [e for _, rec in new_lines for e in rec['body'] if isinstance(e, dict) and e.get('build') == want_build]
    game = [e for e in events if e.get('category') in GAME_CATEGORIES]
    uuids = [e.get('event_uuid') for e in game]
    tap_counts = {c: sum(e.get('category') == c for e in game) for c in GAME_CATEGORIES}
    # the tap's design ids in order vs the browser's (progression ids are 'Start:L1' etc.)
    tap_design = sorted(e.get('event_id') for e in game if e.get('category') == 'design')
    sent_design = sorted(str(e[1]) for e in sent if e[0] == 'addDesignEvent')
    statuses = sorted({r['status'] for r in responses})
    tap_statuses = sorted({rec.get('status') for _, rec in new_lines})
    builds = sorted({e.get('build') for e in events})
    users = sorted({e.get('user_id') for e in events})
    with open(os.path.join(args.out, 'live_excerpt.jsonl'), 'w') as f:
        for raw, _ in new_lines[:5]:
            f.write(raw + '\n')
    checks = {
        'scenarioOk': error is None,
        'committedKey': committed_key,
        'relayOnly': bool(requests) and all(RELAY in r['url'] for r in requests),
        'responsesAll200or201': bool(responses) and all(r['status'] in (200, 201) for r in responses),
        'requestsAnswered': len(requests) == len(responses),
        'tapLinesFound': len(new_lines) > 0,
        'tapStatusesAll200or201': bool(new_lines) and all(s in (200, 201) for s in tap_statuses),
        'tapCountEqualsSent': len(game) == len(sent) and tap_counts == sent_counts,
        'tapNoDuplicateUuid': len(set(uuids)) == len(uuids),
        'tapDesignIdsEqualSent': tap_design == sent_design,
        'tapMarkedTest': bool(new_lines) and all(rec.get('test') is True for _, rec in new_lines),
        'buildOnly': builds == [want_build],
        'excerpt5': min(5, len(new_lines)) == 5,
    }
    editor = None
    if args.scenario == 'telemetry_editor':
        # TASK-237: the editor:/edit: design ids, counted from the tap file (not from debugLog)
        sent_ed = sorted(i for i in sent_design if i.startswith(EDITOR_PREFIXES))
        tap_ed = sorted(i for i in tap_design if i.startswith(EDITOR_PREFIXES))
        editor = {'sent': len(sent_ed), 'tap': len(tap_ed), 'sentEditor': sum(i.startswith('editor:') for i in sent_ed),
                  'sentEdit': sum(i.startswith('edit:') for i in sent_ed),
                  'tapEditor': sum(i.startswith('editor:') for i in tap_ed), 'tapEdit': sum(i.startswith('edit:') for i in tap_ed),
                  'missingInTap': sorted(set(sent_ed) - set(tap_ed)), 'source': 'tap file body events, category design'}
        checks['editorSent'] = editor['sentEditor'] > 0 and editor['sentEdit'] > 0
        checks['editorTapEqualsSent'] = tap_ed == sent_ed
    first30 = None
    if args.scenario == 'telemetry_first30':
        # TASK-242: the load:/ctx:/f30: design ids, counted from the tap file (not from debugLog)
        sent_f = sorted(i for i in sent_design if i.startswith(FIRST30_PREFIXES))
        tap_f = sorted(i for i in tap_design if i.startswith(FIRST30_PREFIXES))
        first30 = {'sent': len(sent_f), 'tap': len(tap_f),
                   **{'sent_' + p[:-1]: sum(i.startswith(p) for i in sent_f) for p in FIRST30_PREFIXES},
                   **{'tap_' + p[:-1]: sum(i.startswith(p) for i in tap_f) for p in FIRST30_PREFIXES},
                   'missingInTap': sorted(set(sent_f) - set(tap_f)), 'extraInTap': sorted(set(tap_f) - set(sent_f)),
                   'source': 'tap file body events, category design', 'sentIds': sent_f}
        checks['first30Sent'] = all(first30['sent_' + p[:-1]] > 0 for p in FIRST30_PREFIXES)
        checks['first30TapEqualsSent'] = tap_f == sent_f
    seq_file = SEQ_FILES[args.scenario]
    try:
        with open(os.path.join(args.out, seq_file)) as f:
            seq_pass = json.load(f).get('pass')
    except (OSError, ValueError):
        seq_pass = None
    res = {
        'scenario': args.scenario, 'build': want_build, 'gameKey': key, 'tapFiles': files, 'runSeconds': run_seconds, 'error': error,
        'sent': {'total': len(sent), **sent_counts, 'source': 'ANALYTICS.debugLog (%s)' % args.scenario},
        'editor': editor,
        'first30': first30,
        'tap': {'linesBefore': before, 'lines': len(new_lines), 'events': len(events), 'gameEvents': len(game),
                **tap_counts, 'uniqueUuids': len(set(uuids)), 'statuses': tap_statuses,
                'testFlags': sorted({rec.get('test') for _, rec in new_lines}, key=str),
                'categories': sorted({e.get('category') for e in events}), 'userIds': users,
                'designIds': tap_design},
        'browser': {'requests': len(requests), 'responses': len(responses), 'statuses': statuses,
                    'responseList': responses},
        'sequencePass': seq_pass,
        'checks': checks,
    }
    res['pass'] = all(checks.values())
    with open(os.path.join(args.out, 'live.json'), 'w') as f:
        json.dump(res, f, separators=(',', ':'))
    if editor:
        print('editor: sent=%d tap=%d (editor: %d/%d, edit: %d/%d)' % (editor['sent'], editor['tap'], editor['sentEditor'],
              editor['tapEditor'], editor['sentEdit'], editor['tapEdit']))
    if first30:
        print('first30: sent=%d tap=%d (load %d/%d, ctx %d/%d, f30 %d/%d)' % (first30['sent'], first30['tap'],
              first30['sent_load'], first30['tap_load'], first30['sent_ctx'], first30['tap_ctx'], first30['sent_f30'], first30['tap_f30']))
    print('build=%s sent=%s tap=%s lines=%d statuses=%s tapStatuses=%s pass=%s (%.0fs)' % (
        want_build, sent_counts, tap_counts, len(new_lines), statuses, tap_statuses, res['pass'], run_seconds))
    for k, v in checks.items():
        if not v:
            print('  FAIL', k)
    if error:
        print('  error:', error)
    return 0 if res['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
