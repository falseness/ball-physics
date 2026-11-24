#!/usr/bin/env python3
"""3x speed execution check (TASK-188).

    python3 tests/visual/speed_check.py --out artifacts/TASK-NNN/speed_check.json [--root DIR]

Three levels (srcId 1, portal level srcId 12, the srcId-24 shelf level), each with fixed player lines, run
once at 1x (speedMul 1) and once at 3x (speedMul 3), each in a fresh browser context (no saved lines/progress).
The lines are placed with in-page handleClick (first click, end click; the last allowed line starts physics),
then gameMechanics() is called frame by frame in one synchronous evaluate (the rAF loop cannot interleave)
until the run ends: a win (levelCompletedWindow) or an off-map restart (levelStarted drops), at most MAX frames.
Every trailRecord call is logged (trailFrame / trailSeg zeroed after placement).
Asserted per level (exact float equality):
  - 3x state (x, y, vx, vy) after frame k == 1x state after frame min(3k, F1) for every k (F1 = 1x framesToEnd);
  - same outcome; framesToEnd3x == ceil(F1 / 3); identical trail point lists.
Writes one compact JSON; exit 1 on any failure or page error.
"""
import argparse
import json
import math
import os
import sys

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAX = 3000

LEVELS = [
    {'srcId': 1, 'kind': 'plain', 'lines': [((640, 170), (330, 330))]},
    {'srcId': 12, 'kind': 'portal', 'lines': [((312, 214), (388, 240))]},  # shoot.LEVEL12_LINE
    {'srcId': 24, 'kind': 'portal+shelf',
     'lines': [((170, 476), (620, 513)), ((790, 610), (730, 714)), ((1000, 140), (1024, 278))]},  # shoot.LEVEL24_LINES
]

RUN = """([src, segs, mul, max]) => {
    const i = levelBySrc(src)
    thisLevel = i; levelChoosed(i); bounce.cancel()
    for (const [a, b] of segs) { handleClick(a); handleClick(b) }
    const placed = {linesK, lineK: curLevel().lineK, physics, pending: !!line,
                    lines: lines.filter(l => l.type == 'player').map(l => [l.posX, l.posY, l.posX2, l.posY2])}
    speedMul = mul
    const trailPts = []
    const rec0 = trailRecord
    trailRecord = function (t) { rec0(t); const s = trail[trail.length - 1]; trailPts.push([s.x, s.y, s.frame, s.seg]) }
    trailFrame = 0; trailSeg = 0; trail = []
    const states = []
    let end = 'timeout'
    for (let f = 0; f < max; ++f) {
        gameMechanics()
        states.push([ball.posX, ball.posY, ball.speedX, ball.speedY])
        if (levelCompletedWindow) { end = 'win'; break }
        if (!levelStarted) { end = 'offmap'; break }
    }
    trailRecord = rec0
    return {placed, end, framesToEnd: states.length, states, trail: trailPts,
            teleports: portalState.teleports.length, speedMulUsed: speedMul}
}"""


def run(br, root, src, segs, mul, errors):
    ctx = br.new_context(viewport={'width': 1280, 'height': 800})
    p = ctx.new_page()
    p.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
    p.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    p.goto('file://' + os.path.join(root, 'index.html'))
    p.wait_for_function("typeof bootComplete !== 'undefined' && bootComplete")
    r = p.evaluate(RUN, [src, [[list(a), list(b)] for a, b in segs], mul, MAX])
    ctx.close()
    return r


def check(L, r1, r3):
    fails = []
    for tag, r in (('1x', r1), ('3x', r3)):
        pl = r['placed']
        if pl['linesK'] != len(L['lines']) or not pl['physics'] or pl['pending']:
            fails.append('%s: lines not placed / physics off: %s' % (tag, pl))
        if r['end'] == 'timeout':
            fails.append('%s: run did not end in %d frames' % (tag, MAX))
    if r1['placed']['lines'] != r3['placed']['lines']:
        fails.append('placed lines differ')
    F1, F3 = r1['framesToEnd'], r3['framesToEnd']
    state_mm, first = 0, None
    for k in range(1, F3 + 1):
        j = min(3 * k, F1)
        if r3['states'][k - 1] != r1['states'][j - 1]:
            state_mm += 1
            if first is None:
                first = {'k': k, '1x': r1['states'][j - 1], '3x': r3['states'][k - 1]}
    if state_mm:
        fails.append('state mismatches: %d, first %s' % (state_mm, first))
    if r1['end'] != r3['end']:
        fails.append('outcome differs: %s vs %s' % (r1['end'], r3['end']))
    if F3 != math.ceil(F1 / 3):
        fails.append('framesToEnd3x %d != ceil(%d / 3)' % (F3, F1))
    trail_eq = r1['trail'] == r3['trail']
    if not trail_eq:
        fails.append('trail lists differ (%d vs %d points)' % (len(r1['trail']), len(r3['trail'])))
    return {'srcId': L['srcId'], 'kind': L['kind'], 'lines': r1['placed']['lines'],
            'outcome1x': r1['end'], 'outcome3x': r3['end'], 'framesToEnd1x': F1, 'framesToEnd3x': F3,
            'expectedFrames3x': math.ceil(F1 / 3), 'framesCompared': F3, 'stateMismatches': state_mm,
            'firstMismatch': first, 'trailPoints1x': len(r1['trail']), 'trailPoints3x': len(r3['trail']),
            'trailIdentical': trail_eq, 'trailSegs': sorted({t[3] for t in r1['trail']}),
            'teleports1x': r1['teleports'], 'teleports3x': r3['teleports'],
            'final1x': r1['states'][-1], 'final3x': r3['states'][-1],
            'speedMulUsed': [r1['speedMulUsed'], r3['speedMulUsed']], 'fails': fails, 'pass': not fails}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--root', default=REPO)
    a = ap.parse_args()
    errors, out = [], []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for L in LEVELS:
            r1 = run(br, a.root, L['srcId'], L['lines'], 1, errors)
            r3 = run(br, a.root, L['srcId'], L['lines'], 3, errors)
            res = check(L, r1, r3)
            out.append(res)
            print('%s srcId %d (%s): 1x %s in %d frames, 3x %s in %d frames, state mismatches %d, trail %s (%d pts)%s' % (
                'PASS' if res['pass'] else 'FAIL', L['srcId'], L['kind'], res['outcome1x'], res['framesToEnd1x'],
                res['outcome3x'], res['framesToEnd3x'], res['stateMismatches'],
                'identical' if res['trailIdentical'] else 'DIFFERENT', res['trailPoints1x'],
                '' if res['pass'] else ' ' + '; '.join(res['fails'])))
        br.close()
    ok = all(r['pass'] for r in out) and not errors and len(out) == 3
    doc = {'levels': out, 'pageErrors': errors, 'allPass': ok}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w') as f:
        json.dump(doc, f, separators=(',', ':'))
    print('allPass' if ok else 'FAIL', '->', a.out)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
