"""Every platform backend (local + the portal stubs) boots the game.

Port of grapnelninja's tools/test_platform_backends.py (c61a049) to this
repo's Playwright harness (sync_playwright + a local HTTP server, like
tests/visual). For each of local/itch/gamepix/y8/playgama a Playwright route
rewrites the backend <script> tag in the served index.html (a portal stub
loads right after local.js, whose LOCAL_PLATFORM_BACKEND it reuses), boots to
the first frame (bootComplete: PLATFORM.init + the boot storage reads),
records PLATFORM.getPlatformId(), round-trips one key through
PLATFORM.storage.setMany/getMany and calls every facade method once with no
page or console error. No portal SDK is loaded (offline): every stub runs on
its no-SDK path.

Usage: python3 tests/platform/test_backends.py --out DIR
Writes DIR/backends.json (default artifacts/TASK-184):
[{backend, platformId, storageRoundTrip, pageErrors, consoleErrors, fallbacks, methodsCalled, pass}].
Exit 0 only when every backend passes.
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
BACKENDS = ['local', 'itch', 'gamepix', 'y8', 'playgama']
LOCAL_TAG = '<script src = "platform/backends/local.js"></script>'
ROUND_TRIP_KEY = 'bp.backendProbe'
VIEWPORT = {'width': 1280, 'height': 800}
READY = ('typeof PLATFORM !== "undefined" && PLATFORM.environment !== "pending"'
         ' && typeof bootComplete !== "undefined" && bootComplete')
PROBE_KEY = 'bp.facadeProbe'
# Every facade method, called once per backend (grapnelninja tools/test_platform_facade.py CALLS)
CALLS = [
    'PLATFORM.now()',
    'PLATFORM.isInterstitialSupported()',
    'PLATFORM.isInterstitialDue()',
    'PLATFORM.showInterstitial("game_over")',
    'PLATFORM.sendMessage("facade_probe")',
    'PLATFORM.sendLifecycle("facade_probe", {a: 1})',
    'PLATFORM.track("facade_probe", {a: 1})',
    'PLATFORM.startup("facade_probe", "classic")',
    'PLATFORM.gameReady()',
    'PLATFORM.readiness',
    'PLATFORM.isAudioEnabled()',
    'PLATFORM.onPause(() => {})',
    'PLATFORM.onAudio(() => {})',
    'PLATFORM.onAdState(() => {})',
    'PLATFORM.storage.remoteKnown',
    'PLATFORM.storage.onRecovery(() => {})',
    'PLATFORM.storage.getMany(["%s"])' % PROBE_KEY,
    'PLATFORM.storage.setMany({})',
    'PLATFORM.loadingProgress(42)',
    'PLATFORM.gameplayStart("classic")',
    'PLATFORM.gameplayStop("death", "classic")',
    'PLATFORM.happyMoment()',
    'PLATFORM.isRewardedSupported()',
    'PLATFORM.showRewarded("continue")',
    'PLATFORM.showBanner("bottom")',
    'PLATFORM.hideBanner()',
    'PLATFORM.submitScore("height", 1234)',
    'PLATFORM.unlockAchievement("summit")',
    'PLATFORM.getLanguage()',
    'PLATFORM.getPlatformId()',
]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def backend_tag(backend):
    if backend == 'local':
        return LOCAL_TAG
    return LOCAL_TAG + '\n    <script src = "platform/backends/%s.js"></script>' % backend


def check_index():
    """index.html loads local.js by default, exactly once; each stub names its id and reuses local."""
    problems = []
    html = open(os.path.join(ROOT, 'index.html')).read()
    if html.count(LOCAL_TAG) != 1:
        problems.append('index.html local tag count %d' % html.count(LOCAL_TAG))
    if html.count('platform/backends/') != 1:
        problems.append('index.html backend tags %d' % html.count('platform/backends/'))
    if html.find(LOCAL_TAG) > html.find('<script src = "platform.js"></script>') or \
            html.find('<script src = "platform.js"></script>') > html.find('<script src = "js/'):
        problems.append('index.html order: backend, platform.js, game scripts')
    for backend in BACKENDS[1:]:
        source = open(os.path.join(ROOT, 'platform/backends/%s.js' % backend)).read()
        if "platformId: '%s'" % backend not in source or 'LOCAL_PLATFORM_BACKEND' not in source:
            problems.append('%s.js stub markers missing' % backend)
    return problems


def check(browser, url, backend):
    context = browser.new_context(viewport=VIEWPORT, locale='en-US')
    errors = {'console': [], 'page': []}
    fallbacks = []
    problems = []
    try:
        def rewrite(route):
            response = route.fetch()
            body = response.text()
            if body.count(LOCAL_TAG) != 1:
                problems.append('served index.html local tag count %d' % body.count(LOCAL_TAG))
            route.fulfill(response=response, body=body.replace(LOCAL_TAG, backend_tag(backend)))
        context.route('**/index.html', rewrite)
        page = context.new_page()
        page.on('console', lambda m: errors['console'].append(m.text) if m.type == 'error' else None)
        page.on('console', lambda m: 'PLATFORM_BACKEND.' in m.text and fallbacks.append(m.text))
        page.on('pageerror', lambda e: errors['page'].append(str(e)))
        page.goto(url + 'index.html')
        page.wait_for_function(READY, timeout=15000)
        loaded = page.evaluate('''() => [...document.scripts].map(s => s.getAttribute('src'))
            .filter(src => src && src.startsWith('platform/backends/'))''')
        expected = ['platform/backends/local.js'] + ([] if backend == 'local' else ['platform/backends/%s.js' % backend])
        if loaded != expected:
            problems.append('loaded %s' % loaded)
        platform_id = page.evaluate('PLATFORM.getPlatformId()')
        ids = page.evaluate('[PLATFORM.platformId, PLATFORM_BACKEND.platformId]')
        if platform_id != backend or ids != [backend, backend]:
            problems.append('platform ids %s %s' % (platform_id, ids))
        written = page.evaluate('PLATFORM.storage.setMany({"%s": "v"})' % ROUND_TRIP_KEY)
        read = page.evaluate('PLATFORM.storage.getMany(["%s"])' % ROUND_TRIP_KEY)
        round_trip = written is True and read == {ROUND_TRIP_KEY: 'v'}
        if not round_trip:
            problems.append('round trip written=%s read=%s' % (written, read))
        for call in CALLS:
            page.evaluate('async () => { await %s }' % call)
        page.evaluate('PLATFORM.init()')
        page.wait_for_timeout(100)
        frames = page.evaluate('n => new Promise(r => { let k = 0; const f = () => ++k >= n ? r(k) : requestAnimationFrame(f); requestAnimationFrame(f) })', 3)
    except Exception as e:
        problems.append('exception: %s: %s' % (type(e).__name__, str(e).splitlines()[0] if str(e) else ''))
        platform_id, round_trip, frames = None, False, 0
    finally:
        context.close()
    res = {'backend': backend, 'platformId': platform_id, 'storageRoundTrip': round_trip,
           'pageErrors': len(errors['page']), 'consoleErrors': len(errors['console']),
           'fallbacks': len(fallbacks), 'methodsCalled': len(CALLS) + 1, 'framesAfterBoot': frames}
    res['pass'] = bool(not problems and round_trip and not errors['page'] and not errors['console'] and not fallbacks)
    if problems or errors['page'] or errors['console'] or fallbacks:
        res['problems'] = problems + errors['page'] + errors['console'] + fallbacks
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='directory for backends.json (required, TASK-280)')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    index_problems = check_index()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=ROOT))
    Thread(target=server.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/' % server.server_port
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for backend in BACKENDS:
                r = check(browser, url, backend)
                results.append(r)
                print('%-9s platformId=%s storageRoundTrip=%s pageErrors=%d consoleErrors=%d fallbacks=%d %s' % (
                    backend, r['platformId'], str(r['storageRoundTrip']).lower(), r['pageErrors'],
                    r['consoleErrors'], r['fallbacks'], 'PASS' if r['pass'] else 'FAIL %s' % r.get('problems')))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    with open(os.path.join(args.out, 'backends.json'), 'w') as f:
        json.dump(results, f, separators=(',', ':'))
    for prob in index_problems:
        print('index:', prob)
    ok = not index_problems and len(results) == len(BACKENDS) and all(r['pass'] for r in results)
    print('OK: %d backends' % len(results) if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
