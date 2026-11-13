#!/usr/bin/env python3
"""Seeded wall-portal fuzz test (Playwright, index.html via file://).

  python3 tests/portal/fuzz.py --seed 1 --cases 500 [--task TASK-065] [--out fuzz.json]

Each case (TASK-065, one-sided wall portals): two random host lines (centre in 150..1130 x
150..650, random direction, length 150..400), portal A cut into the first and B into the second
at a random u (0..1, portalResolve clamps it) with a random side (+1/-1), h = 45, and in half
of the cases one extra plain level line. All lines keep >= 2r + 10 px apart so the ball can never
be squeezed between two of them. A radius-10 ball starts >= r + 2 px from every line:
 - 'aimed' cases (even index): in front of A or B, 20..200 px out, aimed at a random point of the
   opening (|s| <= h) within +-60 deg of the inward normal, |v| in 0.02..0.1 px/step;
 - 'random' cases: anywhere in 100..1180 x 100..700 with a random velocity |v| <= 0.1.
Run for 300 frames x 500 gamePhysics() steps (no restart: the ball simply leaves the map).

Checked on every step in the page: NaN state, teleports per step, and tunnelling: on a step
without a teleport the ball centre's path (previous -> current position) must not cross any
level line segment (host lines included; a front-to-back pass through an opening is a teleport,
so every non-teleport crossing went through a wall). Every teleport record is re-checked in
Python against the resolved portals read from the page (TASK-074): a 'touch' teleport needs the ball
on the entry front (d > 0) moving toward it (v . n < 0) and touching the opening (centre within r of
c +- h t, so |s| <= h + r), and lands on the partner's front (d' > 0) moving away (v . n' > 0); a
'cross' teleport (fallback) needs |s| <= h and a front -> back crossing (d <= 0, |d| <= |v|) and lands
on d' = -d >= 0. Both: relative speed change <= 1e-9 and the exit state equals an independent
recomputation (sim.mapped: touch (s, d) -> (-clamp(s, h), d), cross (s, d) -> (-s, -d), v rotated).
traceHash = sha256 over the case parameters, the ball state after every frame and every teleport
record -> a second run with the same seed gives the same hash.
Output: artifacts/<task>/<out>, compact JSON; exit 1 on failure.
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

FRAMES, PER, H, R, VMAX = 300, 500, 45, 10, 0.1

CASE_JS = """([cfg, frames, per]) => {
  const T = window.__portalTest
  T.setup(cfg)
  const P = (currentPortals() || []).map(q => ({x: q.x, y: q.y, angle: q.angle, h: q.h, name: q.name, line: q.line}))
  const L = curLevel().lines.map(l => [l.posX, l.posY, l.posX2, l.posY2])
  const f = new Float64Array(frames * 4)
  let nan = 0, two = 0, firstNan = -1, tunnels = 0
  const tunnelLog = []
  const side = (l, x, y) => (l[2] - l[0]) * (y - l[1]) - (l[3] - l[1]) * (x - l[0])
  for (let i = 0; i < frames; ++i) {
    for (let k = 0; k < per; ++k) {
      const n0 = portalState.teleports.length, x0 = ball.posX, y0 = ball.posY
      gamePhysics()
      const dn = portalState.teleports.length - n0
      if (dn > 1) ++two
      if (Number.isNaN(ball.posX) || Number.isNaN(ball.posY) || Number.isNaN(ball.speedX) || Number.isNaN(ball.speedY)) {
        if (firstNan < 0) firstNan = i * per + k
        ++nan
      }
      if (dn === 0) {
        const x1 = ball.posX, y1 = ball.posY
        for (let j = 0; j < L.length; ++j) {
          const l = L[j], a0 = side(l, x0, y0), a1 = side(l, x1, y1)
          if (!(a0 > 0 && a1 <= 0) && !(a0 < 0 && a1 >= 0)) continue
          // the centre path crosses the line's infinite extension: inside the segment?
          const b0 = (x1 - x0) * (l[1] - y0) - (y1 - y0) * (l[0] - x0)
          const b1 = (x1 - x0) * (l[3] - y0) - (y1 - y0) * (l[2] - x0)
          if (b0 * b1 <= 0) {
            ++tunnels
            if (tunnelLog.length < 10) tunnelLog.push({step: i * per + k + 1, line: j, from: [x0, y0], to: [x1, y1]})
          }
        }
      }
    }
    f[4 * i] = ball.posX; f[4 * i + 1] = ball.posY; f[4 * i + 2] = ball.speedX; f[4 * i + 3] = ball.speedY
  }
  return { frames: Array.from(f), nan, firstNan, two, tunnels, tunnelLog, portals: P, steps: portalState.steps,
           rimHits: portalState.rimHits, hostHits: portalState.hostHits, teleports: portalState.teleports } }"""


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    k = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2)) if L2 else 0.0
    return math.hypot(p[0] - a[0] - k * dx, p[1] - a[1] - k * dy)


def segseg(l, m):
    a, b, c, d = l[:2], l[2:], m[:2], m[2:]

    def cr(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2, d3, d4 = cr(c, d, a), cr(c, d, b), cr(a, b, c), cr(a, b, d)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return 0.0
    return min(seg_dist(a, c, d), seg_dist(b, c, d), seg_dist(c, a, b), seg_dist(d, a, b))


def rand_line(rng):
    cx, cy = rng.uniform(150, 1130), rng.uniform(150, 650)
    ang, ln = rng.uniform(0, 2 * math.pi), rng.uniform(150, 400)
    dx, dy = math.cos(ang) * ln / 2, math.sin(ang) * ln / 2
    return [cx - dx, cy - dy, cx + dx, cy + dy]


def resolve(line, u, side, h=H):
    """Python copy of portalResolve (only used to aim the ball; the checks use the page's portals)."""
    dx, dy = line[2] - line[0], line[3] - line[1]
    ln = math.hypot(dx, dy)
    tx, ty = dx / ln, dy / ln
    m = h + R
    u = 0.5 if ln < 2 * m else min(max(u, m / ln), 1 - m / ln)
    nx, ny = side * -ty, side * tx
    return {'x': line[0] + u * dx, 'y': line[1] + u * dy, 'angle': math.atan2(ny, nx), 'h': h}


def make_case(rng, aimed):
    while True:
        lines = [rand_line(rng), rand_line(rng)]
        if rng.random() < 0.5:
            lines.append(rand_line(rng))
        if any(segseg(lines[i], lines[j]) < 2 * R + 10 for i in range(len(lines)) for j in range(i)):
            continue
        portals = [{'line': i, 'u': rng.uniform(0, 1), 'side': rng.choice((-1, 1)), 'h': H, 'name': n}
                   for i, n in enumerate('AB')]
        if aimed:
            k = rng.randrange(2)
            P = resolve(lines[k], portals[k]['u'], portals[k]['side'])
            nx, ny = math.cos(P['angle']), math.sin(P['angle'])
            tx, ty = -ny, nx
            s = rng.uniform(-H, H)
            th = rng.uniform(-math.pi / 3, math.pi / 3)
            dist = rng.uniform(20, 200)
            sp = rng.uniform(0.02, VMAX)
            # direction into the wall: -n rotated by th
            c, sn = math.cos(th), math.sin(th)
            vx, vy = -nx * c + tx * sn, -ny * c + ty * sn
            tgt = (P['x'] + s * tx, P['y'] + s * ty)
            ball = {'x': tgt[0] - vx * dist, 'y': tgt[1] - vy * dist, 'vx': sp * vx, 'vy': sp * vy, 'r': R}
        else:
            sp, dr = rng.uniform(0, VMAX), rng.uniform(0, 2 * math.pi)
            ball = {'x': rng.uniform(100, 1180), 'y': rng.uniform(100, 700),
                    'vx': sp * math.cos(dr), 'vy': sp * math.sin(dr), 'r': R}
        if not (0 < ball['x'] < 1280 and 0 < ball['y'] < 800):
            continue
        if any(seg_dist((ball['x'], ball['y']), l[:2], l[2:]) < R + 2 for l in lines):
            continue
        return {'wall': True, 'lines': lines, 'portals': portals, 'ball': ball, 'mode': 'aimed' if aimed else 'random'}


def pack(vals):
    return struct.pack('<%dd' % len(vals), *vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--cases', type=int, default=500)
    ap.add_argument('--task', default='TASK-065')
    ap.add_argument('--out', default='fuzz.json')
    a = ap.parse_args()

    rng = random.Random(a.seed)
    cases = [make_case(rng, i % 2 == 0) for i in range(a.cases)]
    hsh = hashlib.sha256()
    c = {'cases': a.cases, 'aimedCases': sum(1 for x in cases if x['mode'] == 'aimed'),
         'casesWithPlainLine': sum(1 for x in cases if len(x['lines']) == 3),
         'frames': FRAMES, 'stepsPerFrame': PER, 'totalSteps': 0,
         'nanCount': 0, 'teleports': 0, 'casesWithTeleports': 0, 'stepsWithTwoTeleports': 0,
         'sameStepTeleportRecords': 0, 'tunnels': 0, 'casesWithTunnels': 0,
         'sOverH': 0, 'maxAbsSOverH': 0.0, 'notFrontToBack': 0, 'exitNotFront': 0,
         'maxSpeedRelErr': 0.0, 'speedErrOver1e9': 0, 'maxMapPosErr': 0.0, 'maxMapVelErr': 0.0,
         'mapErrOver1e9': 0, 'portalOffHostLine': 0, 'rimHits': 0, 'casesWithRimHits': 0,
         'hostHits': 0, 'casesWithHostHits': 0, 'maxTeleportsInCase': 0, 'kinds': {}}
    bad = []

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, ROOT)
        for ci, cfg in enumerate(cases):
            r = page.evaluate(CASE_JS, [cfg, FRAMES, PER])
            P = {q['name']: q for q in r['portals']}
            b = cfg['ball']
            hsh.update(pack([v for l in cfg['lines'] for v in l]
                            + [v for q in cfg['portals'] for v in (q['u'], q['side'])]
                            + [b['x'], b['y'], b['vx'], b['vy']]))
            hsh.update(pack(r['frames']))
            case_bad = []
            # the resolved portal sits on its host line
            for q in r['portals']:
                l = cfg['lines'][q['line']]
                if seg_dist((q['x'], q['y']), l[:2], l[2:]) > 1e-9 or len(r['portals']) != 2:
                    c['portalOffHostLine'] += 1
                    case_bad.append(('offHost', q['name']))
            c['totalSteps'] += r['steps']
            c['nanCount'] += r['nan']
            c['stepsWithTwoTeleports'] += r['two']
            c['tunnels'] += r['tunnels']
            c['casesWithTunnels'] += r['tunnels'] > 0
            c['rimHits'] += r['rimHits']
            c['casesWithRimHits'] += r['rimHits'] > 0
            c['hostHits'] += r['hostHits']
            c['casesWithHostHits'] += r['hostHits'] > 0
            tps = r['teleports']
            c['teleports'] += len(tps)
            c['casesWithTeleports'] += bool(tps)
            c['maxTeleportsInCase'] = max(c['maxTeleportsInCase'], len(tps))
            steps = [t['step'] for t in tps]
            c['sameStepTeleportRecords'] += len(steps) - len(set(steps))
            for t in tps:
                hsh.update(pack([t['step'], t['s'], t['d']] + t['before'] + t['after']))
                A, B = P[t['from']], P[t['to']]
                kind = t.get('kind')
                c['kinds'][kind] = c['kinds'].get(kind, 0) + 1
                lim = A['h'] + R if kind == 'touch' else A['h']
                aso = abs(t['s']) / A['h']
                c['maxAbsSOverH'] = max(c['maxAbsSOverH'], aso)
                if abs(t['s']) > lim + 1e-9:
                    c['sOverH'] += 1
                    case_bad.append(('|s|>limit', t['step'], kind))
                s, d = local(A, t['before'][0], t['before'][1])
                anx, any_ = math.cos(A['angle']), math.sin(A['angle'])
                bnx, bny = math.cos(B['angle']), math.sin(B['angle'])
                if abs(s - t['s']) > 1e-9 or abs(d - t['d']) > 1e-9:
                    c['notFrontToBack'] += 1
                    case_bad.append(('sd', t['step'], s, d))
                elif kind == 'touch':
                    touch = math.hypot(max(abs(s) - A['h'], 0.0), d)
                    if not (d > 0 and t['before'][2] * anx + t['before'][3] * any_ < 0 and touch <= R + 1e-9):
                        c['notFrontToBack'] += 1
                        case_bad.append(('touch', t['step'], s, d, touch))
                elif kind != 'cross' or d > 0 or abs(d) > t['speedBefore'] + 1e-9:
                    c['notFrontToBack'] += 1
                    case_bad.append(('crossing', t['step'], kind, s, d))
                _, dOut = local(B, t['after'][0], t['after'][1])
                vnOut = t['after'][2] * bnx + t['after'][3] * bny
                if dOut < -1e-9 or (kind == 'touch' and not (dOut > 0 and vnOut > 0)):
                    c['exitNotFront'] += 1
                    case_bad.append(('exitBack', t['step'], dOut, vnOut))
                e = rel(t['speedAfter'], t['speedBefore']) if t['speedBefore'] > 0 else abs(t['speedAfter'])
                e2 = rel(math.hypot(t['after'][2], t['after'][3]), math.hypot(t['before'][2], t['before'][3])) \
                    if t['speedBefore'] > 0 else 0.0
                e = max(e, e2)
                c['maxSpeedRelErr'] = max(c['maxSpeedRelErr'], e)
                if e > 1e-9:
                    c['speedErrOver1e9'] += 1
                    case_bad.append(('speed', t['step'], e))
                ex, ey, evx, evy = mapped(A, B, *t['before'], kind=kind)
                pe = math.hypot(t['after'][0] - ex, t['after'][1] - ey)
                ve = math.hypot(t['after'][2] - evx, t['after'][3] - evy)
                c['maxMapPosErr'] = max(c['maxMapPosErr'], pe)
                c['maxMapVelErr'] = max(c['maxMapVelErr'], ve)
                if pe > 1e-9 or ve > 1e-9:
                    c['mapErrOver1e9'] += 1
                    case_bad.append(('map', t['step'], pe, ve))
            if r['nan'] or r['two'] or r['tunnels'] or case_bad:
                bad.append({'case': ci, 'cfg': cfg, 'nan': r['nan'], 'firstNan': r['firstNan'], 'two': r['two'],
                            'tunnels': r['tunnels'], 'tunnelLog': r['tunnelLog'], 'issues': case_bad[:10]})
            if (ci + 1) % 50 == 0:
                print('cases %d/%d teleports=%d nan=%d two=%d tunnels=%d bad=%d' % (
                    ci + 1, a.cases, c['teleports'], c['nanCount'], c['stepsWithTwoTeleports'], c['tunnels'], len(bad)),
                    flush=True)
        browser.close()

    c['traceHash'] = hsh.hexdigest()
    checks = {
        'ok_nan': c['nanCount'] == 0,
        'ok_teleports': c['teleports'] > 0,
        'ok_no_tunnelling': c['tunnels'] == 0,
        'ok_s_within_h': c['sOverH'] == 0,
        'ok_front_to_back': c['notFrontToBack'] == 0 and c['exitNotFront'] == 0,
        'ok_speed': c['speedErrOver1e9'] == 0 and c['maxSpeedRelErr'] <= 1e-9,
        'ok_map': c['mapErrOver1e9'] == 0,
        'ok_on_host_line': c['portalOffHostLine'] == 0,
        'ok_one_per_step': c['stepsWithTwoTeleports'] == 0 and c['sameStepTeleportRecords'] == 0,
        'ok_steps': c['totalSteps'] == a.cases * FRAMES * PER,
        'ok_errors': not errors,
    }
    res = {'seed': a.seed, 'counters': c, 'checks': checks, 'failingCases': bad[:20],
           'failingCaseCount': len(bad), 'invariantViolations': len(bad), 'errors': errors,
           'pass': all(checks.values())}
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
