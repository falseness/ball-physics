"""Analytics boot check (TASK-190): the ANALYTICS facade boots with the none and gameanalytics backends.

Same harness as tests/platform/test_backends.py (local HTTP server + a Playwright route that rewrites a
script tag in the served index.html). js/buildinfo.js is served stamped by tools/stamp_build.py
('<git short sha>-<YYYYMMDD>'), the repo copy stays unstamped.

  none:          the GameAnalytics SDK tag and the gameanalytics backend tag are replaced by
                 analytics/backends/none.js. Pass: ANALYTICS.debugLog starts with initialize({build: 'test-...'})
                 then startSession, 0 page errors, 0 console errors, no request to an analytics host, and a
                 pagehide event logs flush then endSession.
  gameanalytics: index.html as committed. Pass: debugLog as above, 0 page errors, every analytics-host
                 request goes to stats.playdiplomacy.online (none to *gameanalytics.com), the SDK's init
                 request (relay path /r/i) answers 200 or 201, the SDK build is 'test-<build id>'.

Usage: python3 tests/platform/test_analytics.py [--out DIR] [--backend none|gameanalytics]
Writes DIR/boot.json (none) and DIR/boot_ga.json (gameanalytics), compact JSON. Exit 0 only when all pass.
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sys
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import stamp_build  # noqa: E402

SDK_TAG = '<script src = "analytics/vendor/GameAnalytics.min.js"></script>'
GA_TAG = '<script src = "analytics/backends/gameanalytics.js"></script>'
NONE_TAG = '<script src = "analytics/backends/none.js"></script>'
RELAY = 'stats.playdiplomacy.online'
VIEWPORT = {'width': 1280, 'height': 800}
READY = 'typeof bootComplete !== "undefined" && bootComplete'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def analytics_host(url):
    return RELAY in url or 'gameanalytics.com' in url


def check(browser, url, backend, build):
    context = browser.new_context(viewport=VIEWPORT, locale='en-US')
    page_errors, console_errors, requests, responses, problems = [], [], [], [], []
    res = {'backend': backend, 'stampedBuild': build}
    try:
        def rewrite(route):
            response = route.fetch()
            body = response.text()
            if body.count(SDK_TAG) != 1 or body.count(GA_TAG) != 1:
                problems.append('served index.html analytics tags sdk=%d ga=%d' % (body.count(SDK_TAG), body.count(GA_TAG)))
            if backend == 'none':
                body = body.replace(SDK_TAG + '\n', '').replace(GA_TAG, NONE_TAG)
            route.fulfill(response=response, body=body)

        def buildinfo(route):
            response = route.fetch()
            route.fulfill(response=response, body=stamp_build.stamped(response.text(), build))
        context.route('**/index.html', rewrite)
        context.route('**/js/buildinfo.js', buildinfo)
        page = context.new_page()
        page.on('console', lambda m: console_errors.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: page_errors.append(str(e)))
        page.on('request', lambda r: analytics_host(r.url) and requests.append({'method': r.method, 'url': r.url}))
        page.on('response', lambda r: analytics_host(r.url) and responses.append({'url': r.url, 'status': r.status}))
        page.goto(url + 'index.html')
        page.wait_for_function(READY, timeout=20000)
        if backend == 'gameanalytics':
            # the SDK's init request answers, then the backend goes live (remote configs ready)
            page.wait_for_function('''() => { try { return gameanalytics.GameAnalytics.isRemoteConfigsReady() }
                catch (e) { return false } }''', timeout=30000)
            page.wait_for_timeout(1500)
        res['scripts'] = page.evaluate('''() => [...document.scripts].map(s => s.getAttribute('src'))
            .filter(src => src && (src.startsWith('analytics') || src === 'js/buildinfo.js'))''')
        res['backendId'] = page.evaluate('ANALYTICS_BACKEND.backendId')
        res['webdriver'] = page.evaluate('navigator.webdriver')
        res['debugLog'] = page.evaluate('ANALYTICS.debugLog.map(e => ({fn: e.fn, args: e.args}))')
        if backend == 'gameanalytics':
            res['gaState'] = page.evaluate('''() => { const s = gameanalytics.state.GAState, i = s.instance;
                return {build: s.getBuild ? s.getBuild() : i.build, sessionStarted: s.sessionIsStarted(),
                    initialized: s.isInitialized ? s.isInitialized() : null,
                    hostName: gameanalytics.http.GAHTTPApi.instance.hostName} }''')
        if backend == 'none':
            # a pagehide (synthetic: the page stays readable) calls flush() then sessionEnd(); the game's own design /
            # progression events sent first (TASK-191 abandon, TASK-192 session:levels_seen) are listed apart
            ph = page.evaluate('''() => { const n = ANALYTICS.debugLog.length;
                window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: false}));
                return ANALYTICS.debugLog.slice(n).map(e => e.fn == 'addDesignEvent' ? 'design:' + e.args[0] : e.fn) }''')
            res['pagehideGameEvents'] = [f for f in ph if f.startswith('design:') or f == 'addProgressionEvent']
            res['pagehideLog'] = [f for f in ph if f not in res['pagehideGameEvents']]
    except Exception as e:
        problems.append('exception: %s: %s' % (type(e).__name__, str(e).splitlines()[0] if str(e) else ''))
    finally:
        context.close()
    log = res.get('debugLog') or []
    res['pageErrors'] = len(page_errors)
    res['consoleErrors'] = len(console_errors)
    res['errors'] = page_errors + console_errors
    res['analyticsRequests'] = requests
    res['analyticsResponses'] = responses
    first = log[0] if log else {}
    init_build = (first.get('args') or [{}])[0].get('build', '') if first.get('fn') == 'initialize' else ''
    res['initBuild'] = init_build
    res['logStartsInitThenSessionStart'] = len(log) >= 2 and log[0]['fn'] == 'initialize' and log[1]['fn'] == 'startSession'
    checks = {
        'logOrder': res['logStartsInitThenSessionStart'],
        'initBuildTest': init_build == 'test-' + build,
        'pageErrors0': not page_errors,
        'backend': res.get('backendId') == backend,
        'noProblems': not problems,
    }
    if backend == 'none':
        checks['consoleErrors0'] = not console_errors
        checks['noAnalyticsRequests'] = not requests
        checks['pagehideFlushThenEnd'] = res.get('pagehideLog') == ['flush', 'endSession']
    else:
        init = [r for r in responses if r['url'].split('?')[0].endswith('/r/i')]
        res['initStatus'] = init[0]['status'] if init else None
        res['gameanalyticsComRequests'] = len([r for r in requests if 'gameanalytics.com' in r['url']])
        res['relayRequests'] = len([r for r in requests if RELAY in r['url']])
        checks['allToRelay'] = bool(requests) and all(r['url'].startswith('https://' + RELAY + '/') for r in requests)
        checks['noGameanalyticsCom'] = res['gameanalyticsComRequests'] == 0
        checks['initStatus200or201'] = res['initStatus'] in (200, 201)
        checks['sdkBuildTest'] = (res.get('gaState') or {}).get('build') == 'test-' + build
    res['checks'] = checks
    res['problems'] = problems
    res['pass'] = all(checks.values())
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'artifacts', 'TASK-190'))
    ap.add_argument('--backend', choices=['none', 'gameanalytics'], action='append')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    build = stamp_build.build_id()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=ROOT))
    Thread(target=server.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/' % server.server_port
    ok = True
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for backend in args.backend or ['none', 'gameanalytics']:
                r = check(browser, url, backend, build)
                name = 'boot.json' if backend == 'none' else 'boot_ga.json'
                with open(os.path.join(args.out, name), 'w') as f:
                    json.dump(r, f, separators=(',', ':'))
                print('%-13s initBuild=%s logOrder=%s pageErrors=%d consoleErrors=%d initStatus=%s relayRequests=%s '
                      'gameanalyticsCom=%s %s' % (backend, r['initBuild'], r['logStartsInitThenSessionStart'],
                      r['pageErrors'], r['consoleErrors'], r.get('initStatus'), r.get('relayRequests'),
                      r.get('gameanalyticsComRequests'),
                      'PASS' if r['pass'] else 'FAIL %s %s' % ([k for k, v in r['checks'].items() if not v], r['errors'] + r['problems'])))
                ok = ok and r['pass']
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print('OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
