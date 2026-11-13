#!/usr/bin/env python3
"""Trail regression check for the current trail rules (TASK-069).

Usage: python3 tests/visual/trail_check.py [--root DIR] [--out OUT.json]

--root (default: this repo) is the tree whose index.html is loaded; the shoot.py helpers
(sc_placed, frames, click, ...) come from this script's own directory.

Checks (each recorded under "ok", written as compact JSON to --out):
  A arrows: after sc_placed, gameMechanics() is stepped synchronously in-page to trail lengths
    3,4,8,9,15,16,22,30,43,44,50,51,58,60,75. At each length trailLabels().arrows must equal a
    reference computed here from trailSamples() of the newest segment: candidates i = n-1, n-8, ...
    (i >= 1, at most TRAIL_ARROW_MAX = 7); a candidate is dropped when its anchor is < 24 px from an
    already kept arrow; label = round(|H[i] - H[i-1]| * 60). Count, labels and anchors must match exactly.
  B fade: trailAlphas() of the newest segment at length 60 is 0 at the oldest point, 0.85 at the
    newest and linear (+-1e-9).
  C visible trail: after play on sc_placed (~0.8 s, then paused), trail-attributable cyan pixels
    (r<170, g>170, b>220, minus the same frame with trailDraw as a no-op) >= 50.
  D teleport split: level 11 with its reference solution line (shoot.LEVEL11_LINE, real mouse input),
    stepped until one teleport plus 5 frames (before the win panel): 2 trail segments and 0 attributable cyan pixels
    on the straight line between the two segment ends (middle 40 %, 3 px discs).
Exit 1 if any check fails or the page logs an error.
"""
import argparse
import io
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shoot  # noqa: E402

LENGTHS = [3, 4, 8, 9, 15, 16, 22, 30, 43, 44, 50, 51, 58, 60, 75]
ARROW_STEP, ARROW_MAX, ARROW_GAP = 7, 7, 24
FADE_MAX = 0.85
C_MIN = 50


def new_page(browser, url, errors):
    page = browser.new_page(viewport=shoot.VIEWPORT)
    page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
    page.goto(url)
    page.wait_for_load_state('load')
    shoot.frames(page)
    return page


def shot(page):
    return np.asarray(Image.open(io.BytesIO(page.screenshot())).convert('RGB')).astype(int)


def trail_mask(page):
    """trail-attributable cyan of the current (paused) frame: cyan pixels that change when trailDraw is a no-op"""
    a = shot(page)
    page.evaluate("() => { window.__trailDraw = trailDraw; trailDraw = function() {} }")
    shoot.frames(page, 3)
    b = shot(page)
    page.evaluate("() => { trailDraw = window.__trailDraw }")
    shoot.frames(page, 3)
    cy = (a[..., 0] < 170) & (a[..., 1] > 170) & (a[..., 2] > 220)
    return cy & (np.abs(a - b).sum(axis=2) > 0)


def near(mask, x, y, r):
    h, w = mask.shape
    x0, x1, y0, y1 = max(0, int(x - r)), min(w, int(x + r) + 1), max(0, int(y - r)), min(h, int(y + r) + 1)
    if x0 >= x1 or y0 >= y1:
        return 0
    yy, xx = np.mgrid[y0:y1, x0:x1]
    return int((mask[y0:y1, x0:x1] & ((xx - x) ** 2 + (yy - y) ** 2 <= r * r)).sum())


def newest_segment(samples):
    seg = samples[-1]['seg']
    return [s for s in samples if s['seg'] == seg]


def reference_arrows(H):
    kept = []
    i = len(H) - 1
    c = 0
    while c < ARROW_MAX and i >= 1:
        if not any(math.hypot(a['x'] - H[i]['x'], a['y'] - H[i]['y']) < ARROW_GAP for a in kept):
            dx, dy = H[i]['x'] - H[i - 1]['x'], H[i]['y'] - H[i - 1]['y']
            kept.append({'i': i, 'x': H[i]['x'], 'y': H[i]['y'], 'label': round(math.hypot(dx, dy) * 60)})
        c += 1
        i -= ARROW_STEP
    return kept


def play_xy(page):
    return page.evaluate("[menuIconRect[0][0] - 73 + 31, menuIconRect[0][1] + 31]")


STEP_JS = """k => { physics = true; levelStarted = true
    for (let i = 0; i < k; ++i) { gameMechanics(); if (!physics) break }
    const ph = physics; physics = false
    return {ph, samples: trailSamples(), labels: trailLabels(), alphas: trailAlphas()} }"""


def check_a_b(browser, url, errors):
    page = new_page(browser, url, errors)
    shoot.sc_placed(page, {})
    rows, ok_a, b_res, ok_b = [], True, None, False
    done = 0
    for target in LENGTHS:
        st = page.evaluate(STEP_JS, target - done)
        done = target
        if not st['ph'] or st['labels'] is None:
            rows.append({'len': target, 'stopped': True, 'ok': False})
            ok_a = False
            break
        H = newest_segment(st['samples'])
        exp = reference_arrows(H)
        got = st['labels']['arrows']
        cnt = len(got) == len(exp)
        lab = [g['label'] for g in got] == [e['label'] for e in exp]
        anc = [[g['x'], g['y']] for g in got] == [[e['x'], e['y']] for e in exp]
        o = cnt and lab and anc
        rows.append({'len': target, 'n': len(H), 'count': len(got), 'refCount': len(exp),
                     'labels': [g['label'] for g in got], 'refLabels': [e['label'] for e in exp],
                     'countOk': cnt, 'labelsOk': lab, 'anchorsOk': anc, 'ok': o})
        ok_a = ok_a and o
        if target == 60:
            al = st['alphas']
            n = len(H)
            # strand points i = 1..n-1, alpha = 0.85 * (i-1)/(n-2)
            dev = max((abs(q['alpha0'] - FADE_MAX * (k / (len(al) - 1))) for k, q in enumerate(al)), default=1)
            dev = max([dev] + [abs(q['alpha1'] - q['alpha0']) for q in al])
            b_res = {'n': n, 'points': len(al), 'oldest': al[0]['alpha0'] if al else None,
                     'newest': al[-1]['alpha0'] if al else None, 'maxLinearDev': dev}
            ok_b = (n == 60 and len(al) == n - 1 and abs(al[0]['alpha0']) <= 1e-9
                    and abs(al[-1]['alpha0'] - FADE_MAX) <= 1e-9 and dev <= 1e-9)
    page.close()
    return {'rows': rows}, ok_a and len(rows) == len(LENGTHS), b_res, ok_b


def check_c(browser, url, errors):
    page = new_page(browser, url, errors)
    shoot.sc_placed(page, {})
    shoot.click(page, *play_xy(page))
    page.wait_for_timeout(800)
    page.evaluate("() => { physics = false }")
    shoot.frames(page, 2)
    n = page.evaluate("trailSamples().length")
    px = int(trail_mask(page).sum())
    page.close()
    return {'samples': n, 'trailCyanPixels': px}, px >= C_MIN


def check_d(browser, url, errors):
    page = new_page(browser, url, errors)
    page.evaluate("() => { thisLevel = 10; levelChoosed(10) }")
    shoot.frames(page)
    (x1, y1), (x2, y2) = shoot.LEVEL11_LINE
    shoot.click(page, x1, y1)
    shoot.move(page, x2, y2)
    shoot.frames(page)
    shoot.click(page, x2, y2)
    res = page.evaluate("""() => { const portals = (curLevel().portals || []).length
        physics = true; levelStarted = true
        let f = 0, after = -1
        while (f < 3000) { gameMechanics(); ++f
            if (!physics) break
            if (portalState.teleports.length && after < 0) after = f
            if (after >= 0 && f - after >= 5) break }
        physics = false
        return {portals, frames: f, completed: levelCompletedWindow, teleportFrame: after, teleports: portalState.teleports.length,
            samples: trailSamples()} }""")
    shoot.frames(page, 3)
    S = res.pop('samples')
    tr = trail_mask(page)
    page.close()
    segids = sorted(set(s['seg'] for s in S))
    res.update({'samples': len(S), 'segments': len(segids), 'trailCyanPixels': int(tr.sum())})
    if len(segids) == 2:
        e1 = [s for s in S if s['seg'] == segids[0]][-1]
        e2 = [s for s in S if s['seg'] == segids[1]][0]
        gap = 0
        for k in range(30, 71):  # middle 40 % of the straight line between the segment ends
            t = k / 100
            gap += near(tr, e1['x'] + (e2['x'] - e1['x']) * t, e1['y'] + (e2['y'] - e1['y']) * t, 3)
        res.update({'end1': [e1['x'], e1['y']], 'end2': [e2['x'], e2['y']],
                    'dist': round(math.hypot(e2['x'] - e1['x'], e2['y'] - e1['y']), 2), 'gapPixels': gap})
    ok = res['teleports'] == 1 and res['segments'] == 2 and res.get('gapPixels') == 0 and res['trailCyanPixels'] > 0
    return res, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(HERE)))
    ap.add_argument('--out')
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    url = 'file://' + os.path.join(root, 'index.html')
    errors, out, ok = [], {'root': root}, {}
    with sync_playwright() as p:
        br = p.chromium.launch()
        out['A'], ok['A'], out['B'], ok['B'] = check_a_b(br, url, errors)
        out['C'], ok['C'] = check_c(br, url, errors)
        out['D'], ok['D'] = check_d(br, url, errors)
        br.close()
    out['errors'] = errors
    out['ok'] = ok
    out['allPass'] = all(ok.values()) and not errors
    if args.out:
        with open(args.out, 'w') as f:
            json.dump(out, f, separators=(',', ':'))
    bad = [r['len'] for r in out['A']['rows'] if not r['ok']]
    print('A ok=%s failingLengths=%s' % (ok['A'], bad))
    print('B ok=%s %s' % (ok['B'], json.dumps(out['B'], separators=(',', ':'))))
    print('C ok=%s %s' % (ok['C'], json.dumps(out['C'], separators=(',', ':'))))
    print('D ok=%s %s' % (ok['D'], json.dumps({k: v for k, v in out['D'].items()}, separators=(',', ':'))))
    for e in errors:
        print('  ', e)
    print('allPass', out['allPass'])
    return 0 if out['allPass'] else 1


if __name__ == '__main__':
    sys.exit(main())
