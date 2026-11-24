#!/usr/bin/env python3
"""Path preview / idle trail length regression check (TASK-120; rules of TASK-085, 111, 112, 118).

Usage: python3 tests/visual/preview_check.py [--root DIR] [--out OUT.json]

--root (default: this repo) is the tree whose index.html is loaded (file://, 1280x800); the shoot.py
helpers come from this script's own directory. Input is real page.mouse clicks / moves; JS only reads
state, records the last bounce.request coords (pass-through wrapper) and calls the test-only
calcSyncIdle() / calcSync().

Per level (source id 1: no portals, expected 100 points; source id 11: portal pair, expected 300; TASK-177:
addressed by srcId through levelBySrc, a --root tree without it is in definition order):
  a idle:      right after load, no click: !bounce.busy, positions.length == curCount() == expected,
               every point == calcSyncIdle() within 1e-9.
  b drawing:   first real click starts a line, real move to a fixed point: !bounce.busy,
               positions == calcSync(coords) within 1e-9, same count.
  c invariant: ball posX/posY/speedX/speedY, portalState.teleports.length and a deep copy of lines are
               identical before and after (a) and (b).
  d play:      on a fresh page, after loading the level, waiting for the idle trail and clicking the play icon, positions.length == 0 within 2 frames.
  e errors:    no page / console errors.
Prints one PASS/FAIL line per check, then 'allPass True|False'. Exit 1 if any check fails.
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shoot  # noqa: E402

EPS = 1e-9
LEVELS = {1: 100, 11: 300}   # level source id -> expected preview points
SRC_JS = "n => typeof levelBySrc === 'function' ? levelBySrc(n) : n - 1"

SETUP = """() => { if (window.__wrapped) return; window.__wrapped = true;
    const rq = Bounce.prototype.request; Bounce.prototype.request = function(c) { window.__req = [c[0], c[1]]; return rq.call(this, c) };
    for (const L of levels) L.unlock = Math.max(L.unlock || 0, 1) }"""

SNAP = """() => JSON.stringify({ball: [ball.posX, ball.posY, ball.speedX, ball.speedY],
    tele: portalState.teleports.length,
    lines: lines.map(l => JSON.parse(JSON.stringify(l)))})"""

DIFF = """(a, b) => { let d = a.length == b.length ? 0 : Infinity;
    for (let i = 0; i < Math.min(a.length, b.length); ++i) d = Math.max(d, Math.abs(a[i].x - b[i].x), Math.abs(a[i].y - b[i].y));
    return d }"""

CMP_IDLE = """() => { const diff = (%s); const a = bounce.positions.map(p => ({x: p.x, y: p.y}));
    const b = bounce.calcSyncIdle();
    return {n: a.length, nRef: b.length, count: bounce.curCount(), maxDiff: diff(a, b)} }""" % DIFF

CMP_DRAW = """() => { const diff = (%s); const a = bounce.positions.map(p => ({x: p.x, y: p.y})); const c = window.__req;
    bounce.calcSync(c); const b = bounce.positions.map(p => ({x: p.x, y: p.y}));
    return {n: a.length, nRef: b.length, count: bounce.curCount(), maxDiff: diff(a, b), line: !!line,
            req: c && [c[0], c[1]]} }""" % DIFF

# fixed drawing points per level: free, off the HUD, line clear of the ball
DRAW_PTS = """() => {
    const pts = [[300, 300], [200, 500], [640, 600], [900, 300], [500, 200], [150, 150], [700, 400], [400, 650], [1000, 600]];
    const ok = p => playerLineAt(p[0], p[1]) === null && !inMenuIcon(p) && !inPlayIcon(p) && !ball.collisionWithDot(p[0], p[1])
        && Math.hypot(p[0] - ball.posX, p[1] - ball.posY) > 120;
    for (const a of pts) for (const b of pts) if (a !== b && ok(a) && ok(b) && Math.hypot(a[0] - b[0], a[1] - b[1]) > 150
        && pointSegDist(ball.posX, ball.posY, a[0], a[1], b[0], b[1]) > ball.radius + 20) return [a, b];
    return null }"""


def wait_idle(page, limit=900):
    for _ in range(limit):
        if page.evaluate("!bounce.busy && bounce.positions.length == bounce.curCount()"):
            return True
        shoot.frames(page, 1)
    return False


def choose_level(page, i):
    shoot.click(page, *page.evaluate("[menuIconRect[0][0] + 31, menuIconRect[0][1] + 31]"))
    shoot.click(page, *page.evaluate("i => { const r = levelRectXY(i); return [r[0] + rectSize / 2, r[1] + rectSize / 2] }", i))


def level_run(page, src, expected):
    res, ok = {'expected': expected}, {}
    lv = page.evaluate(SRC_JS, src)
    res['srcId'] = src
    if lv != 0:
        choose_level(page, lv)
    shoot.frames(page, 1)
    res['thisLevel'] = page.evaluate("thisLevel")
    s0 = page.evaluate(SNAP)
    # (a) idle trail after load
    done = wait_idle(page)
    a = page.evaluate(CMP_IDLE)
    s1 = page.evaluate(SNAP)
    res['a'] = dict(a, done=done)
    ok['a'] = (res['thisLevel'] == lv and done and a['n'] == a['count'] == a['nRef'] == expected and a['maxDiff'] <= EPS)
    # (b) drawing: first real click + real move to a fixed point
    pts = page.evaluate(DRAW_PTS)
    p0, p1 = pts
    shoot.click(page, *p0)
    shoot.move(page, p1[0] - 10, p1[1] + 7)
    shoot.frames(page, 1)
    shoot.move(page, *p1)
    shoot.frames(page, 2)
    done = wait_idle(page)
    b = page.evaluate(CMP_DRAW)
    s2 = page.evaluate(SNAP)
    res['b'] = dict(b, done=done, p0=p0, p1=p1)
    ok['b'] = (done and b['line'] and b['n'] == b['count'] == b['nRef'] == expected and b['maxDiff'] <= EPS)
    # (c) real state unchanged by (a) and (b)
    res['c'] = {'snapBefore': json.loads(s0)['ball'] + [json.loads(s0)['tele']],
                'eqAfterA': s0 == s1, 'eqAfterB': s0 == s2, 'nLines': len(json.loads(s0)['lines'])}
    ok['c'] = s0 == s1 == s2
    return res, ok


def play_run(page, src, expected):
    """(d) fresh page: load the level, wait for the idle trail, click the play icon"""
    lv = page.evaluate(SRC_JS, src)
    if lv != 0:
        choose_level(page, lv)
    done = wait_idle(page)
    n_before = page.evaluate("bounce.positions.length")
    play = page.evaluate("[menuIconRect[0][0] - 73 + 31, menuIconRect[0][1] + 31]")
    page.mouse.click(*shoot.to_client(page, *play))
    ns = []
    for _ in range(2):
        shoot.frames(page, 1)
        ns.append(page.evaluate("bounce.positions.length"))
    run = page.evaluate("({physics, levelStarted})")
    res = {'nBefore': n_before, 'nWithin2Frames': ns, 'done': done, **run}
    return res, done and n_before == expected and run['physics'] and run['levelStarted'] and ns[-1] == 0


def open_page(br, url, errors):
    page = br.new_page(viewport=shoot.VIEWPORT)
    page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda x: errors.append('pageerror: ' + str(x)))
    page.goto(url)
    page.wait_for_function("typeof bounce !== 'undefined' && typeof levels !== 'undefined'")
    page.evaluate(SETUP)
    shoot.frames(page, 3)
    return page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(HERE)))
    ap.add_argument('--out')
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    url = 'file://' + os.path.join(root, 'index.html')
    out, oks = {'root': root, 'levels': {}}, []
    with sync_playwright() as p:
        br = p.chromium.launch()
        for lv, expected in LEVELS.items():
            errors = []
            try:
                page = open_page(br, url, errors)
                res, ok = level_run(page, lv, expected)
                page.close()
                page = open_page(br, url, errors)
                res['d'], ok['d'] = play_run(page, lv, expected)
                page.close()
            except Exception as ex:  # a broken page must still produce FAIL lines and exit 1
                res, ok = {'exception': str(ex)}, {k: False for k in 'abcd'}
            res['errors'] = errors
            ok['e'] = not errors
            res['ok'] = ok
            out['levels'][str(lv)] = res
            for k in 'abcde':
                oks.append(ok[k])
                print('%s level=%d %s' % ('PASS' if ok[k] else 'FAIL', lv, {
                    'a': 'a_idle_count_%d_eq_calcSyncIdle' % expected, 'b': 'b_drawing_eq_calcSync',
                    'c': 'c_state_invariant', 'd': 'd_play_hides_within_2_frames', 'e': 'e_no_page_errors'}[k]),
                    json.dumps(res.get(k, res.get('exception')), separators=(',', ':')) if k != 'e' else errors)
        br.close()
    out['allPass'] = all(oks)
    if args.out:
        with open(args.out, 'w') as f:
            json.dump(out, f, separators=(',', ':'))
    print('allPass', out['allPass'])
    return 0 if out['allPass'] else 1


if __name__ == '__main__':
    sys.exit(main())
