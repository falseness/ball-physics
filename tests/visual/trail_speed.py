#!/usr/bin/env python3
"""Trail speed-up proof (TASK-125; covers TASK-122..124): bit-identity, timing and real progressive fill
of the working tree against a baseline tree.

Usage:
    git archive 7bf1d25 | tar -x -C BASE_DIR      # plus fonts/ img/ if they are untracked
    python3 tests/visual/trail_speed.py --base BASE_DIR [--work DIR] [--out OUT.json] [--runs 7] [--fills 3]

Audit runner: add this command next to tests/visual/preview_check.py in any run_checks.sh:
    python3 tests/visual/trail_speed.py --base <7bf1d25 tree> --out <dir>/speed.json

Both trees are loaded (file://, 1280x800, headless Chromium) and run the same page code:
  identity (asserted, === / Python == on floats): for every level the idle trail (calcSyncIdle), calcSync
           for 2 deterministic player lines, and a 600-tact real gameMechanics() play run per line
           (ball posX/posY/speedX/speedY per tact). Any difference is a mismatch.
           Only the levels both trees have are compared (TASK-129: levels appended after the baseline, e.g.
           level 18, are listed as informational extraLevels); the shared levels keep the strict comparison.
  timing   (informational, never fails): median of --runs calcSyncIdle() per level, pages interleaved.
  fill     (informational per level; gate over portal levels 10..16): after levelChoosed(i), the number
           of requestAnimationFrame frames of the real game loop until
           !bounce.busy && bounce.positions.length == bounce.curCount() (median of --fills loads).
           Gate: sum of work fill frames over levels 10..16 < sum of base fill frames.
Prints PASS/FAIL lines, writes one compact JSON. Exit 1 on any identity mismatch, page error or
failed fill gate.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PORTAL_LEVELS = range(10, 17)

IDENTITY = """() => {
    const CANDS = [[[200, 400], [500, 450]], [[600, 600], [900, 550]], [[300, 650], [700, 700]], [[150, 300], [450, 350]],
                   [[700, 300], [1000, 350]], [[400, 500], [800, 520]], [[900, 650], [1150, 600]], [[250, 200], [550, 260]],
                   [[100, 600], [400, 560]], [[800, 450], [1100, 480]], [[500, 300], [600, 700]], [[1000, 200], [1200, 400]]]
    const st = () => [ball.posX, ball.posY, ball.speedX, ball.speedY]
    const pts = a => a.map(p => [p.x, p.y])
    const out = []
    for (let i = 0; i < levels.length; ++i) {
        const rec = {level: i, pairs: [], calc: [], play: []}
        thisLevel = i; levelChoosed(i); bounce.cancel()
        rec.idle = pts(bounce.calcSyncIdle())
        for (const [a, b] of CANDS) {
            if (rec.pairs.length >= 2) break
            levelChoosed(i); bounce.cancel()
            const c = dotСorrection(a[0], a[1], dotRadius)
            if (ball.collisionWithDot(c[0], c[1])) continue
            line = new Line(c[0], c[1], c[0], c[1], dotRadius, '#0000ff', 'line'); linesK++
            if (!addNewLine([b[0], b[1]])) { line = false; continue }
            unfastenLastLine()
            bounce.calcSync([b[0], b[1]])
            rec.calc.push(pts(bounce.positions))
            if (!addNewLine([b[0], b[1]])) { line = false; continue }
            line = false; bounce.cancel(); bounce.setDrawEnable(false)
            physics = true; levelStarted = true; levelCompletedWindow = false
            const run = []; let end = 'tacts'
            for (let t = 0; t < 600; ++t) {
                const lc0 = levelStarted
                gameMechanics()
                run.push(st())
                if (levelCompletedWindow) { end = 'completed'; break }
                if (!levelStarted && lc0) { end = 'offmap'; break }
            }
            physics = false; levelStarted = false; levelCompletedWindow = false; bounce.setDrawEnable(true)
            rec.play.push({end, states: run})
            rec.pairs.push([a, b])
        }
        out.push(rec)
    }
    thisLevel = 0; levelChoosed(0)
    return out
}"""

TIME = """([i, n]) => { thisLevel = i; levelChoosed(i); bounce.cancel(); bounce.setDrawEnable(false); const t = [];
    for (let k = 0; k < n; ++k) { const t0 = performance.now(); bounce.calcSyncIdle(); t.push(performance.now() - t0) }
    bounce.setDrawEnable(true); return t }"""

# real game loop only: load the level, then count rAF frames until the idle trail is complete.
# Counting starts after the first frame (the game loop starts the idle job in its own rAF callback).
FILL = """([i, limit]) => new Promise(res => {
    thisLevel = i; levelChoosed(i)
    let n = 0
    const tick = () => {
        if (n > 0 && !bounce.busy && bounce.positions.length == bounce.curCount()) return res({frames: n, count: bounce.curCount()})
        if (++n > limit) return res({frames: n, count: bounce.curCount(), timeout: true})
        requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
})"""

FRAMES = "n => new Promise(r => { const f = k => k <= 0 ? r() : requestAnimationFrame(() => f(k - 1)); f(n) })"


def open_page(br, root, errors):
    p = br.new_page(viewport={'width': 1280, 'height': 800})
    p.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
    p.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    p.goto('file://' + os.path.join(root, 'index.html'))
    p.wait_for_function("typeof bounce !== 'undefined' && typeof levels !== 'undefined'")
    p.evaluate(FRAMES, 3)
    return p


def compare(B, W):
    mm, first = {'structure': 0, 'idle': 0, 'calcSync': 0, 'play': 0}, [None]
    points = {'idle': 0, 'calcSync': 0, 'play': 0}

    def bad(kind, info):
        mm[kind] += 1
        if first[0] is None:
            first[0] = dict(kind=kind, **info)

    def seq(kind, a, b, info):
        if len(a) != len(b):
            bad(kind, dict(info, len=[len(a), len(b)]))
        for k, (x, y) in enumerate(zip(a, b)):
            points[kind] += 1
            if x != y:
                bad(kind, dict(info, i=k))

    per = {}
    # only the levels both trees have are compared (zip stops at the shorter list); levels added after the
    # baseline are listed by main() as informational extraLevels, the shared ones stay strict (=== per point)
    for b, w in zip(B, W):
        L = b['level']
        n0 = sum(mm.values())
        if b['pairs'] != w['pairs'] or len(b['calc']) != len(w['calc']) or len(b['play']) != len(w['play']):
            bad('structure', {'level': L})
        seq('idle', b['idle'], w['idle'], {'level': L})
        for j, (cb, cw) in enumerate(zip(b['calc'], w['calc'])):
            seq('calcSync', cb, cw, {'level': L, 'pair': j})
        for j, (pb, pw) in enumerate(zip(b['play'], w['play'])):
            if pb['end'] != pw['end']:
                bad('play', {'level': L, 'pair': j, 'end': [pb['end'], pw['end']]})
            seq('play', pb['states'], pw['states'], {'level': L, 'pair': j})
        per[L] = {'mismatches': sum(mm.values()) - n0, 'idleN': len(b['idle']), 'pairs': len(b['pairs']),
                  'playTacts': [len(p['states']) for p in b['play']]}
    return mm, first[0], points, per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True, help='baseline tree (e.g. git archive 7bf1d25)')
    ap.add_argument('--work', default=REPO, help='tree under test (default: this repo)')
    ap.add_argument('--out', help='compact JSON result')
    ap.add_argument('--runs', type=int, default=7, help='calcSyncIdle() timings per level (median)')
    ap.add_argument('--fills', type=int, default=3, help='real fill measurements per level (median)')
    ap.add_argument('--limit', type=int, default=3000, help='frame limit per fill')
    a = ap.parse_args()
    base, work = os.path.abspath(a.base), os.path.abspath(a.work)
    eb, ew = [], []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pb, pk = open_page(br, base, eb), open_page(br, work, ew)
        B, W = pb.evaluate(IDENTITY), pk.evaluate(IDENTITY)
        n = min(len(B), len(W))
        for p in (pb, pk):
            p.evaluate(TIME, [0, 2])  # JIT warm-up
        times = [(pb.evaluate(TIME, [i, a.runs]), pk.evaluate(TIME, [i, a.runs])) for i in range(n)]
        pb.close()
        pk.close()
        # fills on fresh pages (the identity / timing code leaves the idle-trail cache stale); every measured
        # load comes right after a completed load of a different level, so the level change is real
        fpb, fpk = open_page(br, base, eb), open_page(br, work, ew)
        rows = []
        for i in range(n):
            tb, tw = times[i]
            fb, fw = [], []
            for _ in range(a.fills):  # interleaved real fills
                for p, acc in ((fpb, fb), (fpk, fw)):
                    p.evaluate(FILL, [(i + 1) % n, a.limit])
                    acc.append(p.evaluate(FILL, [i, a.limit]))
            rows.append({'level': i, 'baseMs': round(statistics.median(tb), 2), 'newMs': round(statistics.median(tw), 2),
                         'baseFill': statistics.median(f['frames'] for f in fb),
                         'newFill': statistics.median(f['frames'] for f in fw),
                         'count': fw[0]['count'], 'fillTimeout': any(f.get('timeout') for f in fb + fw)})
        fpb.close()
        fpk.close()
        br.close()
    mm, first, points, per = compare(B, W)
    for r in rows:
        r.update(per.get(r['level'], {}))
    total = sum(mm.values())
    fb_sum = sum(r['baseFill'] for r in rows if r['level'] in PORTAL_LEVELS)
    fw_sum = sum(r['newFill'] for r in rows if r['level'] in PORTAL_LEVELS)
    gate = fw_sum < fb_sum and not any(r['fillTimeout'] for r in rows)
    git = lambda *c: subprocess.run(['git', '-C', work] + list(c), capture_output=True, text=True).stdout.strip()
    res = {'base': base, 'workHead': git('rev-parse', 'HEAD'), 'workDirty': git('status', '--porcelain', 'js', 'index.html'),
           'nLevels': n, 'levelsBase': len(B), 'levelsWork': len(W), 'points': points, 'mismatches': mm,
           'mismatchTotal': total, 'firstMismatch': first, 'pageErrors': {'base': eb, 'work': ew}, 'levels': rows,
           'portalFillBase': fb_sum, 'portalFillNew': fw_sum, 'fillGatePass': gate,
           'msBaseSum': round(sum(r['baseMs'] for r in rows), 2), 'msNewSum': round(sum(r['newMs'] for r in rows), 2)}
    res['extraLevels'] = {'base': list(range(n, len(B))), 'work': list(range(n, len(W)))}
    ident = total == 0 and n > 0 and not eb and not ew
    res['identityPass'] = ident
    res['allPass'] = ident and gate
    if a.out:
        with open(a.out, 'w') as f:
            json.dump(res, f, separators=(',', ':'))
    for r in rows:
        print('%s level=%d mismatches=%d | info ms %.2f -> %.2f | fill frames %s -> %s (count %d)' % (
            'PASS' if r.get('mismatches', 1) == 0 else 'FAIL', r['level'], r.get('mismatches', -1),
            r['baseMs'], r['newMs'], r['baseFill'], r['newFill'], r['count']))
    print('points', points, 'mismatches', mm, 'first', first)
    print('shared levels %d (base %d, work %d); extra levels (informational, not compared): base %s work %s' % (
        n, len(B), len(W), res['extraLevels']['base'], res['extraLevels']['work']))
    print('%s identity mismatches=%d page_errors=%d' % ('PASS' if ident else 'FAIL', total, len(eb) + len(ew)))
    print('%s fill_gate portal levels 10..16 new %s < base %s' % ('PASS' if gate else 'FAIL', fw_sum, fb_sum))
    print('info ms sum base %.2f new %.2f' % (res['msBaseSum'], res['msNewSum']))
    print('allPass', res['allPass'])
    return 0 if res['allPass'] else 1


if __name__ == '__main__':
    sys.exit(main())
