#!/usr/bin/env python3
"""Seeded portal fuzz test (Playwright, index.html via file://).

  python3 tests/portal/fuzz.py --seed 1 --cases 500 [--task TASK-028] [--out fuzz.json]

Each case: a random portal pair A/B (centres in 100..1180 x 100..700, random angles,
h = 45), no level lines, a radius-10 ball at a random position with a random velocity
(|v| <= 0.1 px/step), run for 300 frames x 500 gamePhysics() steps (no restart, the ball
simply leaves the map). Checked on every step in the page: NaN state, number of
teleports per step. Every teleport record (all of them, not sampled) is re-checked in
Python: |s| <= h at the crossing, relative speed change <= 1e-9, and the exit state
equals an independent recomputation of the map (s, d) -> (-s, -d), v rotated.
traceHash = sha256 over the case parameters, the ball state (x, y, vx, vy as IEEE
doubles) after every frame and every teleport record -> a second run with the same seed
must give the same hash. Output: artifacts/<task>/<out>, compact JSON; exit 1 on failure.
"""
import argparse
import hashlib
import json
import math
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import ROOT, open_page, mapped, local, rel  # noqa: E402

FRAMES, PER, H, VMAX = 300, 500, 45, 0.1

CASE_JS = """([cfg, frames, per]) => {
  const T = window.__portalTest
  T.setup(cfg)
  const f = new Float64Array(frames * 4)
  let nan = 0, two = 0, firstNan = -1
  for (let i = 0; i < frames; ++i) {
    for (let k = 0; k < per; ++k) {
      const n0 = portalState.teleports.length
      gamePhysics()
      if (portalState.teleports.length - n0 > 1) ++two
      if (Number.isNaN(ball.posX) || Number.isNaN(ball.posY) || Number.isNaN(ball.speedX) || Number.isNaN(ball.speedY)) {
        if (firstNan < 0) firstNan = i * per + k
        ++nan
      }
    }
    f[4 * i] = ball.posX; f[4 * i + 1] = ball.posY; f[4 * i + 2] = ball.speedX; f[4 * i + 3] = ball.speedY
  }
  return { frames: Array.from(f), nan: nan, firstNan: firstNan, two: two, steps: portalState.steps,
           rimHits: portalState.rimHits, teleports: portalState.teleports } }"""


def make_case(rng):
    ps = []
    for name in ('A', 'B'):
        ps.append({'x': rng.uniform(100, 1180), 'y': rng.uniform(100, 700),
                   'angle': rng.uniform(0, 2 * math.pi), 'h': H, 'name': name})
    sp, dr = rng.uniform(0, VMAX), rng.uniform(0, 2 * math.pi)
    ball = {'x': rng.uniform(100, 1180), 'y': rng.uniform(100, 700),
            'vx': sp * math.cos(dr), 'vy': sp * math.sin(dr), 'r': 10}
    return {'portals': ps, 'ball': ball, 'lines': []}


def pack(vals):
    return struct.pack('<%dd' % len(vals), *vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--cases', type=int, default=500)
    ap.add_argument('--task', default='TASK-028')
    ap.add_argument('--out', default='fuzz.json')
    a = ap.parse_args()

    rng = random.Random(a.seed)
    cases = [make_case(rng) for _ in range(a.cases)]
    hsh = hashlib.sha256()
    c = {'cases': a.cases, 'frames': FRAMES, 'stepsPerFrame': PER, 'totalSteps': 0,
         'nanCount': 0, 'teleports': 0, 'casesWithTeleports': 0, 'stepsWithTwoTeleports': 0,
         'sameStepTeleportRecords': 0, 'sOverH': 0, 'maxAbsSOverH': 0.0, 'maxSpeedRelErr': 0.0,
         'speedErrOver1e9': 0, 'maxMapPosErr': 0.0, 'maxMapVelErr': 0.0, 'mapErrOver1e9': 0,
         'crossingNotSignChange': 0, 'rimHits': 0, 'casesWithRimHits': 0, 'maxTeleportsInCase': 0}
    bad = []

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, ROOT)
        for ci, cfg in enumerate(cases):
            r = page.evaluate(CASE_JS, [cfg, FRAMES, PER])
            P = {q['name']: q for q in cfg['portals']}
            b = cfg['ball']
            hsh.update(pack([v for q in cfg['portals'] for v in (q['x'], q['y'], q['angle'])]
                            + [b['x'], b['y'], b['vx'], b['vy']]))
            hsh.update(pack(r['frames']))
            c['totalSteps'] += r['steps']
            c['nanCount'] += r['nan']
            c['stepsWithTwoTeleports'] += r['two']
            c['rimHits'] += r['rimHits']
            c['casesWithRimHits'] += r['rimHits'] > 0
            tps = r['teleports']
            c['teleports'] += len(tps)
            c['casesWithTeleports'] += bool(tps)
            c['maxTeleportsInCase'] = max(c['maxTeleportsInCase'], len(tps))
            steps = [t['step'] for t in tps]
            c['sameStepTeleportRecords'] += len(steps) - len(set(steps))
            case_bad = []
            for t in tps:
                hsh.update(pack([t['step'], t['s'], t['d']] + t['before'] + t['after']))
                A, B = P[t['from']], P[t['to']]
                aso = abs(t['s']) / A['h']
                c['maxAbsSOverH'] = max(c['maxAbsSOverH'], aso)
                if abs(t['s']) > A['h']:
                    c['sOverH'] += 1
                    case_bad.append(('|s|>h', t['step']))
                # recompute (s, d) at the crossing from the pre-teleport position
                s, d = local(A, t['before'][0], t['before'][1])
                if abs(s - t['s']) > 1e-9 or abs(d - t['d']) > 1e-9 or abs(d) > t['speedBefore'] + 1e-9:
                    c['crossingNotSignChange'] += 1
                    case_bad.append(('crossing', t['step']))
                e = rel(t['speedAfter'], t['speedBefore']) if t['speedBefore'] > 0 else abs(t['speedAfter'])
                # independent speed check from the raw vectors too
                e2 = rel(math.hypot(t['after'][2], t['after'][3]), math.hypot(t['before'][2], t['before'][3])) \
                    if t['speedBefore'] > 0 else 0.0
                e = max(e, e2)
                c['maxSpeedRelErr'] = max(c['maxSpeedRelErr'], e)
                if e > 1e-9:
                    c['speedErrOver1e9'] += 1
                    case_bad.append(('speed', t['step'], e))
                ex, ey, evx, evy = mapped(A, B, *t['before'])
                pe = math.hypot(t['after'][0] - ex, t['after'][1] - ey)
                ve = math.hypot(t['after'][2] - evx, t['after'][3] - evy)
                c['maxMapPosErr'] = max(c['maxMapPosErr'], pe)
                c['maxMapVelErr'] = max(c['maxMapVelErr'], ve)
                if pe > 1e-9 or ve > 1e-9:
                    c['mapErrOver1e9'] += 1
                    case_bad.append(('map', t['step'], pe, ve))
            if r['nan'] or r['two'] or case_bad:
                bad.append({'case': ci, 'cfg': cfg, 'nan': r['nan'], 'firstNan': r['firstNan'],
                            'two': r['two'], 'issues': case_bad[:10]})
            if (ci + 1) % 100 == 0:
                print('cases %d/%d teleports=%d nan=%d two=%d' % (ci + 1, a.cases, c['teleports'],
                                                                   c['nanCount'], c['stepsWithTwoTeleports']))
        browser.close()

    c['traceHash'] = hsh.hexdigest()
    checks = {
        'ok_nan': c['nanCount'] == 0,
        'ok_teleports': c['teleports'] > 0,
        'ok_s_within_h': c['sOverH'] == 0,
        'ok_crossing': c['crossingNotSignChange'] == 0,
        'ok_speed': c['speedErrOver1e9'] == 0 and c['maxSpeedRelErr'] <= 1e-9,
        'ok_map': c['mapErrOver1e9'] == 0,
        'ok_one_per_step': c['stepsWithTwoTeleports'] == 0 and c['sameStepTeleportRecords'] == 0,
        'ok_steps': c['totalSteps'] == a.cases * FRAMES * PER,
        'ok_errors': not errors,
    }
    res = {'seed': a.seed, 'counters': c, 'checks': checks, 'failingCases': bad[:20],
           'failingCaseCount': len(bad), 'errors': errors, 'pass': all(checks.values())}
    out_dir = os.path.join(ROOT, 'artifacts', a.task)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, a.out), 'w') as f:
        json.dump(res, f, separators=(',', ':'))
    print(json.dumps(c, separators=(',', ':')))
    print('traceHash', c['traceHash'])
    print('PASS' if res['pass'] else 'FAIL', {k: v for k, v in checks.items() if not v})
    return 0 if res['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
