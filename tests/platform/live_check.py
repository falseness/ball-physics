"""Live delivery check through the GameAnalytics relay (TASK-193).

Plays the telemetry_ui script of tests/visual/shoot.py headless with the committed gameanalytics backend (index.html
as committed; js/buildinfo.js served stamped with 'live-<YYYYMMDD>', so an automated browser sends build
'test-live-<YYYYMMDD>'), waits for every relay answer, then reads the relay tap's raw copy
(/var/lib/ga-tap/events-<game key>-<UTC day>.jsonl, split per key since TASK-194): lines whose path holds the ball-physics game key and whose body events carry
this build. The design + progression events in the tap must equal the ones the browser sent (ANALYTICS.debugLog).

Usage: python3 tests/platform/live_check.py --out DIR [--build NAME] [--tap-dir DIR]
  --build  stamped build (default 'live-<YYYYMMDD>' UTC); a preview uses e.g. 'livepre-<YYYYMMDD>' so its events
           stay out of the proof build's count
Writes DIR/live.json and DIR/live_excerpt.jsonl (5 tap lines as recorded), DIR/sequence.json (telemetry_ui).
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
WAIT_STEPS = ('touch menu_open', 'map_close')


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    day = datetime.datetime.now(datetime.timezone.utc)
    ap.add_argument('--build', default='live-' + day.strftime('%Y%m%d'))
    ap.add_argument('--tap-dir', default='/var/lib/ga-tap')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    key = json.load(open(KEYS))['gameKey']
    with open(os.path.join(ROOT, 'analytics', 'backends', 'gameanalytics.js')) as f:
        committed_key = key in f.read()
    want_build = 'test-' + args.build
    tap_file = os.path.join(args.tap_dir, 'events-%s-%s.jsonl' % (key, day.strftime('%Y-%m-%d')))
    before = len(tap_lines(tap_file, key, want_build))

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
        if name in WAIT_STEPS:
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
            shoot.sc_telemetry_ui(page, info)
        except Exception as e:
            error = '%s: %s' % (type(e).__name__, e)
        browser.close()
    run_seconds = round(time.time() - t0, 1)

    full = shoot.TELEMETRY_LOGS.get('telemetry_ui', [])
    sent = [e for e in full if e[0] in ('addDesignEvent', 'addProgressionEvent')]
    sent_counts = {'design': sum(e[0] == 'addDesignEvent' for e in sent),
                   'progression': sum(e[0] == 'addProgressionEvent' for e in sent)}

    # the tap writes as the relay answers; give it a moment, then read
    time.sleep(2)
    lines = tap_lines(tap_file, key, want_build)
    new_lines = lines[before:]
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
    res = {
        'build': want_build, 'gameKey': key, 'tapFile': tap_file, 'runSeconds': run_seconds, 'error': error,
        'sent': {'total': len(sent), **sent_counts, 'source': 'ANALYTICS.debugLog (telemetry_ui)'},
        'tap': {'linesBefore': before, 'lines': len(new_lines), 'events': len(events), 'gameEvents': len(game),
                **tap_counts, 'uniqueUuids': len(set(uuids)), 'statuses': tap_statuses,
                'testFlags': sorted({rec.get('test') for _, rec in new_lines}, key=str),
                'categories': sorted({e.get('category') for e in events}), 'userIds': users,
                'designIds': tap_design},
        'browser': {'requests': len(requests), 'responses': len(responses), 'statuses': statuses,
                    'responseList': responses},
        'sequencePass': (info.get('telemetry') or {}).get('sequencePass'),
        'checks': checks,
    }
    res['pass'] = all(checks.values())
    with open(os.path.join(args.out, 'live.json'), 'w') as f:
        json.dump(res, f, separators=(',', ':'))
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
