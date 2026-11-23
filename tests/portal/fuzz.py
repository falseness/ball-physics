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

--crossing (TASK-104; default --cases 2000 --frames 100, --out fuzz_crossing.json): the same cases plus
1-3 extra plain lines that cross or touch a random portal opening ('cross': through a point of the
opening at 20..160 deg to it; 'touch': one end exactly on the opening, rims included, running into the
front; 'front': 1..14 px in front of the opening, roughly parallel). Extra lines keep >= 2r + 10 px from
every line except the host line of the opening they belong to. Every check above still applies, plus:
'teleportPathsBlocked' (a teleport whose entry path, centre -> touched opening point, or exit path, exit
opening point -> exit centre, meets a line other than that portal's host line; js/portal.js refuses such
exits, blockedExits, the ball bounces off the entry instead) and 'pingPongCases' (a run of > 4 teleports,
each <= 2 steps after the previous one: the ball thrown back and forth between the portals; a ball
rattling in a small pocket and bouncing off a line through the exit each time, 2 teleports per bounce,
is counted only in casesOver4In2000Steps). 'exitOverlapsLine' (exit centre within r of such a line, from the opening's
side) is only counted; since TASK-172 js/portal.js refuses such exits too (blocked, reason 'overlap'), so it stays 0.

Rim-trap (livelock) detector (TASK-165, always on in every mode): the shared detector of tests/portal/rimtrap.py
(window.__rimtrap.detector, TASK-163/164) is fed after every frame. A case is TRAPPED when the ball centre
stays within h + r + 2 px of one portal centre for >= 240 consecutive frames with no teleport in that window
while its mean speed along the portal's tangent over the window is > 1 px/frame (a ball resting or bouncing
in place is not a trap). Any TRAPPED case fails the run (counters.traps, failingCases issue 'trapped').

--backside (TASK-165; default --cases 2000 --frames 300, --out fuzz_backside.json): two random host lines with
portals as in the default mode (plus the optional plain line), but the ball starts BEHIND a random portal,
aimed to land on the back of its host line next to a random rim: contact offset s = rim +- (r + 5) px along
the opening (|s| <= h + r + 5), 3..40 px away, |v| 0.005..0.05 px/step, within +-70 deg of the line normal.
This is the level 19 rim-trap bug (TASK-163/164): the unfixed portalStep traps such balls between the rims.
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
from rimtrap import install as install_trap  # noqa: E402

FRAMES, PER, H, R, VMAX = 300, 500, 45, 10, 0.1
TASK = None

CASE_JS = """([cfg, frames, per]) => {
  const T = window.__portalTest
  T.setup(cfg)
  const P = (currentPortals() || []).map(q => ({x: q.x, y: q.y, angle: q.angle, h: q.h, name: q.name, line: q.line}))
  const L = curLevel().lines.map(l => [l.posX, l.posY, l.posX2, l.posY2])
  const det = window.__rimtrap.detector(currentPortals() || [])
  const f = new Float64Array(frames * 4)
  let nan = 0, two = 0, firstNan = -1, tunnels = 0
  const tunnelLog = []
  const side = (l, x, y) => (l[2] - l[0]) * (y - l[1]) - (l[3] - l[1]) * (x - l[0])
  for (let i = 0; i < frames; ++i) {
    const nf = portalState.teleports.length
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
    det.frame(portalState.teleports.length > nf, i + 1)
    f[4 * i] = ball.posX; f[4 * i + 1] = ball.posY; f[4 * i + 2] = ball.speedX; f[4 * i + 3] = ball.speedY
  }
  return { frames: Array.from(f), nan, firstNan, two, tunnels, tunnelLog, portals: P, steps: portalState.steps,
           rimHits: portalState.rimHits, hostHits: portalState.hostHits, teleports: portalState.teleports,
           blockedExits: portalState.blockedExits, trapped: det.trapped, trapFrame: det.trapFrame,
           trapPortal: det.trapPortal } }"""


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


def seg_hit(p0, p1, l):
    """True when segment p0 -> p1 meets segment l (endpoints included; same test as portalPathBlocked)."""
    ex, ey = p1[0] - p0[0], p1[1] - p0[1]
    fx, fy = l[2] - l[0], l[3] - l[1]
    den = ex * fy - ey * fx
    if den == 0:
        return False
    qx, qy = l[0] - p0[0], l[1] - p0[1]
    k, m = (qx * fy - qy * fx) / den, (qx * ey - qy * ex) / den
    return 0 <= k <= 1 and 0 <= m <= 1


def extra_line(rng, P):
    """One extra line crossing / touching / just in front of opening P (resolved, see resolve())."""
    nx, ny = math.cos(P['angle']), math.sin(P['angle'])
    tx, ty = -ny, nx
    kind = rng.choice(('cross', 'touch', 'front'))
    s = rng.uniform(-H, H) if rng.random() < 0.8 else rng.choice((-H, H))
    ln = rng.uniform(40, 250)
    if kind == 'front':
        d = rng.uniform(1, 14)
        a = rng.uniform(-15, 15) * math.pi / 180
        ux, uy = tx * math.cos(a) + nx * math.sin(a), ty * math.cos(a) + ny * math.sin(a)
        q = (P['x'] + s * tx + d * nx, P['y'] + s * ty + d * ny)
        f = rng.uniform(0.1, 0.9)
    else:
        a = rng.uniform(20, 160) * math.pi / 180          # angle to the opening, measured from t toward n
        ux, uy = tx * math.cos(a) + nx * math.sin(a), ty * math.cos(a) + ny * math.sin(a)
        q = (P['x'] + s * tx, P['y'] + s * ty)
        f = rng.uniform(0.15, 0.85) if kind == 'cross' else 0.0
    return kind, [q[0] - f * ln * ux, q[1] - f * ln * uy, q[0] + (1 - f) * ln * ux, q[1] + (1 - f) * ln * uy]


def make_backside_case(rng):
    """TASK-165: the ball lands on the BACK of a random portal's host line next to a random rim."""
    while True:
        cfg = make_case(rng, True)
        lines, portals = cfg['lines'], cfg['portals']
        k = rng.randrange(2)
        P = resolve(lines[k], portals[k]['u'], portals[k]['side'])
        nx, ny = math.cos(P['angle']), math.sin(P['angle'])
        tx, ty = -ny, nx
        rim = rng.choice((-H, H))
        s = rim + rng.uniform(-(R + 5), R + 5)
        th = rng.uniform(-70, 70) * math.pi / 180
        dist = rng.uniform(3, 40)
        sp = rng.uniform(0.005, 0.05)
        # direction into the BACK of the line: +n rotated by th; centre at contact = P + s t - r n
        c, sn = math.cos(th), math.sin(th)
        vx, vy = nx * c + tx * sn, ny * c + ty * sn
        cx, cy = P['x'] + s * tx - R * nx, P['y'] + s * ty - R * ny
        ball = {'x': cx - vx * dist, 'y': cy - vy * dist, 'vx': sp * vx, 'vy': sp * vy, 'r': R}
        if not (0 < ball['x'] < 1280 and 0 < ball['y'] < 800):
            continue
        if any(seg_dist((ball['x'], ball['y']), l[:2], l[2:]) < R + 2 for l in lines):
            continue
        cfg.update({'ball': ball, 'mode': 'backside', 'backside': ['AB'[k], round(s, 6), round(th * 180 / math.pi, 6)]})
        return cfg


def make_crossing_case(rng, aimed):
    while True:
        cfg = make_case(rng, aimed)
        lines, portals = cfg['lines'], cfg['portals']
        P = [resolve(lines[q['line']], q['u'], q['side']) for q in portals]
        kinds, n = [], rng.randint(1, 3)
        for _ in range(20):
            if len(kinds) == n:
                break
            k = rng.randrange(2)
            kind, l = extra_line(rng, P[k])
            if not all(30 <= v <= lim for v, lim in zip(l, (1250, 770, 1250, 770))):
                continue
            if any(segseg(l, m) < 2 * R + 10 for i, m in enumerate(lines) if i != portals[k]['line']):
                continue
            lines.append(l)
            kinds.append([kind, 'AB'[k]])
        if not kinds:
            continue
        b = cfg['ball']
        if any(seg_dist((b['x'], b['y']), l[:2], l[2:]) < R + 2 for l in lines):
            continue
        cfg['extraLines'] = kinds
        return cfg


def pack(vals):
    return struct.pack('<%dd' % len(vals), *vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--cases', type=int)
    ap.add_argument('--frames', type=int)
    ap.add_argument('--task', default='TASK-065')
    ap.add_argument('--out')
    ap.add_argument('--crossing', action='store_true', help='TASK-104: 1-3 extra lines across random openings')
    ap.add_argument('--backside', action='store_true', help='TASK-165: ball lands on the back of a host line by a rim')
    a = ap.parse_args()
    if a.crossing and a.backside:
        ap.error('--crossing and --backside are exclusive')
    mode = 'crossing' if a.crossing else 'backside' if a.backside else 'default'
    a.cases = a.cases or (500 if mode == 'default' else 2000)
    frames = a.frames or (100 if a.crossing else FRAMES)
    a.out = a.out or {'crossing': 'fuzz_crossing.json', 'backside': 'fuzz_backside.json', 'default': 'fuzz.json'}[mode]

    rng = random.Random(a.seed)
    if a.backside:
        cases = [make_backside_case(rng) for i in range(a.cases)]
    else:
        cases = [(make_crossing_case if a.crossing else make_case)(rng, i % 2 == 0) for i in range(a.cases)]
    hsh = hashlib.sha256()
    c = {'cases': a.cases, 'aimedCases': sum(1 for x in cases if x['mode'] == 'aimed'),
         'casesWithPlainLine': sum(1 for x in cases if len(x['lines']) == 3),
         'frames': frames, 'stepsPerFrame': PER, 'totalSteps': 0,
         'nanCount': 0, 'teleports': 0, 'casesWithTeleports': 0, 'stepsWithTwoTeleports': 0,
         'sameStepTeleportRecords': 0, 'tunnels': 0, 'casesWithTunnels': 0,
         'sOverH': 0, 'maxAbsSOverH': 0.0, 'notFrontToBack': 0, 'exitNotFront': 0,
         'maxSpeedRelErr': 0.0, 'speedErrOver1e9': 0, 'maxMapPosErr': 0.0, 'maxMapVelErr': 0.0,
         'mapErrOver1e9': 0, 'portalOffHostLine': 0, 'rimHits': 0, 'casesWithRimHits': 0,
         'hostHits': 0, 'casesWithHostHits': 0, 'maxTeleportsInCase': 0, 'kinds': {}, 'traps': 0}
    if a.backside:
        c.update({'mode': 'backside', 'backsideCases': sum(1 for x in cases if x['mode'] == 'backside')})
    if a.crossing:
        c.update({'mode': 'crossing', 'extraLines': 0, 'extraLineKinds': {}, 'casesWithTeleportThroughCrossedOpening': 0,
                  'blockedExits': 0, 'casesWithBlockedExits': 0, 'exitOverlapsLine': 0, 'teleportPathsBlocked': 0,
                  'pingPongCases': 0, 'longestTeleportRun': 0, 'maxTeleportsIn2000Steps': 0, 'casesOver4In2000Steps': 0})
        for x in cases:
            c['extraLines'] += len(x['extraLines'])
            for k, _ in x['extraLines']:
                c['extraLineKinds'][k] = c['extraLineKinds'].get(k, 0) + 1
    bad = []

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, ROOT)
        install_trap(page)
        for ci, cfg in enumerate(cases):
            r = page.evaluate(CASE_JS, [cfg, frames, PER])
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
            if r['trapped']:
                c['traps'] += 1
                case_bad.append(('trapped', r['trapFrame'], r['trapPortal']))
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
            crossed_tp = False
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
                if a.crossing:
                    # informational: exits overlapping a line from the opening's side (refused since TASK-172, see S11)
                    if any(seg_dist(t['after'][:2], l[:2], l[2:]) < R for i, l in enumerate(cfg['lines']) if i != B['line']):
                        c['exitOverlapsLine'] += 1
                    if t['to'] in [n for _, n in cfg['extraLines']] or t['from'] in [n for _, n in cfg['extraLines']]:
                        crossed_tp = True
                    # entry path: centre -> touched opening point; exit path: exit opening point -> exit centre
                    fa, fb = math.cos(A['angle']), math.sin(A['angle'])
                    se_in = max(-A['h'], min(A['h'], s))
                    ein = (A['x'] - fb * se_in, A['y'] + fa * se_in)
                    sb, _ = local(B, t['after'][0], t['after'][1])
                    gb, hb = math.cos(B['angle']), math.sin(B['angle'])
                    O = (B['x'] - hb * sb, B['y'] + gb * sb)
                    blk = any(seg_hit(t['before'][:2], ein, l) for i, l in enumerate(cfg['lines']) if i != A['line']) or \
                        any(seg_hit(O, t['after'][:2], l) for i, l in enumerate(cfg['lines']) if i != B['line'])
                    if blk:
                        c['teleportPathsBlocked'] += 1
                        case_bad.append(('pathBlocked', t['step'], t['from'], t['to']))
                pe = math.hypot(t['after'][0] - ex, t['after'][1] - ey)
                ve = math.hypot(t['after'][2] - evx, t['after'][3] - evy)
                c['maxMapPosErr'] = max(c['maxMapPosErr'], pe)
                c['maxMapVelErr'] = max(c['maxMapVelErr'], ve)
                if pe > 1e-9 or ve > 1e-9:
                    c['mapErrOver1e9'] += 1
                    case_bad.append(('map', t['step'], pe, ve))
            if a.crossing and crossed_tp:
                c['casesWithTeleportThroughCrossedOpening'] += 1
            if a.crossing:
                c['blockedExits'] += r['blockedExits']
                c['casesWithBlockedExits'] += r['blockedExits'] > 0
                # informational: most teleports within 2000 consecutive steps
                mx, j = 0, 0
                for i in range(len(steps)):
                    while steps[i] - steps[j] >= 2000:
                        j += 1
                    mx = max(mx, i - j + 1)
                c['maxTeleportsIn2000Steps'] = max(c['maxTeleportsIn2000Steps'], mx)
                if mx > 4:
                    c['casesOver4In2000Steps'] += 1
                # ping-pong loop: a run of > 4 teleports, each <= 2 steps after the previous one (the ball
                # bounced back and forth between the portals without getting anywhere)
                run = best = min(1, len(steps))
                for i in range(1, len(steps)):
                    run = run + 1 if steps[i] - steps[i - 1] <= 2 else 1
                    best = max(best, run)
                c['longestTeleportRun'] = max(c['longestTeleportRun'], best)
                if best > 4:
                    c['pingPongCases'] += 1
                    case_bad.append(('pingPong', best, len(steps)))
            if r['nan'] or r['two'] or r['tunnels'] or case_bad:
                bad.append({'case': ci, 'cfg': cfg, 'nan': r['nan'], 'firstNan': r['firstNan'], 'two': r['two'],
                            'tunnels': r['tunnels'], 'tunnelLog': r['tunnelLog'], 'issues': case_bad[:10]})
            if (ci + 1) % 50 == 0:
                print('cases %d/%d teleports=%d nan=%d two=%d tunnels=%d traps=%d bad=%d' % (
                    ci + 1, a.cases, c['teleports'], c['nanCount'], c['stepsWithTwoTeleports'], c['tunnels'],
                    c['traps'], len(bad)),
                    flush=True)
        browser.close()

    c['traceHash'] = hsh.hexdigest()
    checks = {
        'ok_nan': c['nanCount'] == 0,
        'ok_teleports': c['teleports'] > 0 or a.backside,
        'ok_no_tunnelling': c['tunnels'] == 0,
        'ok_no_trap': c['traps'] == 0,
        'ok_s_within_h': c['sOverH'] == 0,
        'ok_front_to_back': c['notFrontToBack'] == 0 and c['exitNotFront'] == 0,
        'ok_speed': c['speedErrOver1e9'] == 0 and c['maxSpeedRelErr'] <= 1e-9,
        'ok_map': c['mapErrOver1e9'] == 0,
        'ok_on_host_line': c['portalOffHostLine'] == 0,
        'ok_one_per_step': c['stepsWithTwoTeleports'] == 0 and c['sameStepTeleportRecords'] == 0,
        'ok_steps': c['totalSteps'] == a.cases * frames * PER,
        'ok_errors': not errors,
    }
    if a.crossing:
        checks['ok_no_blocked_teleport_path'] = c['teleportPathsBlocked'] == 0
        checks['ok_extra_lines'] = c['extraLines'] >= a.cases
        checks['ok_no_ping_pong'] = c['pingPongCases'] == 0
    if a.backside:
        checks['ok_backside_cases'] = c['backsideCases'] == a.cases
    res = {'seed': a.seed, 'mode': mode, 'counters': c, 'checks': checks, 'failingCases': bad[:20],
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
