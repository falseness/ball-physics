#!/usr/bin/env python3
"""Portal physics checks (Playwright, index.html via file://).

  python3 tests/portal/sim.py --task TASK-NNN --scenarios S1,...,S14 [--out suite.json]
      -> artifacts/TASK-NNN/core.json (compact), exit 1 if any check fails.
  python3 tests/portal/sim.py --trajectory OUT.json [--root DIR] [--frames 600]
      -> x, y after every frame (500 gamePhysics steps) for levels 1..10 without
         player lines, loaded from DIR/index.html (default: this repo). Used to
         compare against a pre-portal checkout.
  python3 tests/portal/sim.py --compare BASE.json CUR.json --out OUT.json
  python3 tests/portal/sim.py --trajectory OUT.json --levels 10
      -> only levels 1..10 (the pre-portal ones); each entry also carries a sha256 of its x/y list.

S1-S4, S6-S14 (TASK-065) run with wall portals too: wcfg() cuts every scenario portal
{x, y, angle} into its own host line (300 px along the portal's tangent, u = 0.5, side -1) and
check_geometry() asserts the resolved portal is exactly the scenario's free-standing geometry.
S5 (back-side entry) is retired: wall portals are one-sided. Legacy {x, y, angle} portals are
no longer exercised by these scenarios.
W7 (TASK-074) replays artifacts/portal_physics.png (edge capture sweep) and writes
artifacts/<task>/edge.json and edge.png.
W1-W6 (--scenarios W1,...) run one-sided wall portals ({line, u, side} on the scenario's own
lines, installed by __portalTest.setup({wall: true, ...}) as a scratch level).
W8-W11 (TASK-104): the standard W pair plus one extra plain line across / in front of an opening
(the line stays solid; see the comment above W_X_JS).
--out: a bare file name is written to artifacts/<task>/, a path with a directory as given.
"""
import hashlib
import random
import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PI = math.pi


def open_page(p, root):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    errors = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('file://' + os.path.join(root, 'index.html'))
    page.wait_for_function('typeof gamePhysics === "function"')
    return browser, page, errors


def frame(P):
    nx, ny = math.cos(P['angle']), math.sin(P['angle'])
    return nx, ny, -ny, nx


def local(P, x, y):
    nx, ny, tx, ty = frame(P)
    dx, dy = x - P['x'], y - P['y']
    return dx * tx + dy * ty, dx * nx + dy * ny


EXIT_MIN_D = 1e-6      # js/portal.js PORTAL_EXIT_MIN_D


def mapped(A, B, x, y, vx, vy, kind=None):
    """Independent recomputation of the teleport, velocity rotated by angB - angA + PI.
    TASK-074 'touch' capture (entry d > 0): (s, d) -> (-clamp(s, -h, h), max(d, 1e-6)) at the exit;
    'cross' fallback (entry d <= 0): (s, d) -> (-s, -d). kind defaults to the sign of the entry d."""
    s, d = local(A, x, y)
    if kind is None:
        kind = 'touch' if d > 0 else 'cross'
    if kind == 'touch':
        s, d = max(-B['h'], min(B['h'], s)), -max(d, EXIT_MIN_D)
    nx, ny, tx, ty = frame(B)
    a = B['angle'] - A['angle'] + PI
    c, sn = math.cos(a), math.sin(a)
    return (B['x'] - s * tx - d * nx, B['y'] - s * ty - d * ny,
            vx * c - vy * sn, vx * sn + vy * c)


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-300)


def wall_line(P, L=300):
    """Host line for portal P {x, y, angle}: length L, centred on P, running along P's tangent t."""
    _, _, tx, ty = frame(P)
    return [P['x'] - L / 2 * tx, P['y'] - L / 2 * ty, P['x'] + L / 2 * tx, P['y'] + L / 2 * ty]


def wcfg(ball, portals, lines=(), L=300):
    """TASK-065: S-scenario setup with wall portals. Every portal {x, y, angle, h, name} is cut into its
    own host line (wall_line, u = 0.5). The line runs along t = (-ny, nx), so side -1 gives the front
    normal n of the portal (portalResolve: n = side * (-ty, tx)); `lines` are extra plain level lines."""
    Ls = list(L) if isinstance(L, (list, tuple)) else [L] * len(portals)
    return {'wall': True, 'ball': ball,
            'lines': [wall_line(P, l) for P, l in zip(portals, Ls)] + [list(l) for l in lines],
            'portals': [{'line': i, 'u': 0.5, 'side': -1, 'h': P['h'], 'name': P['name']} for i, P in enumerate(portals)],
            '_geom': [{'x': P['x'], 'y': P['y'], 'angle': P['angle'], 'name': P['name']} for P in portals]}


GEOM_JS = """() => (currentPortals() || []).map(P => [P.x, P.y, Math.cos(P.angle), Math.sin(P.angle), P.line])"""


def check_geometry(page, cfg):
    """The resolved wall portals must sit exactly where the scenario's free-standing geometry says."""
    if not cfg.get('wall'):
        return
    got = page.evaluate(GEOM_JS)
    for i, q in enumerate(cfg.get('_geom', [])):
        x, y, c, sn, line = got[i]
        err = max(abs(x - q['x']), abs(y - q['y']), abs(c - math.cos(q['angle'])), abs(sn - math.sin(q['angle'])))
        if err > 1e-9 or line != i:
            raise AssertionError('wall portal %s resolved to %r, expected %r (err %g)' % (q['name'], got[i], q, err))


def run(page, cfg, steps):
    page.evaluate('c => window.__portalTest.setup(c)', cfg)
    check_geometry(page, cfg)
    return page.evaluate('n => window.__portalTest.step(n)', steps)


A_FLOOR = {'x': 300, 'y': 400, 'angle': -PI / 2, 'h': 45, 'name': 'A', 'color': '#ff8a3d'}


def teleport_checks(st, A, B, chk):
    tps = st['teleports']
    chk['teleports'] = len(tps)
    chk['ok_one_teleport'] = len(tps) == 1 and tps[0]['from'] == 'A'
    if not tps:
        return None
    t = tps[0]
    bx, by, bvx, bvy = t['before']
    ex, ey, evx, evy = mapped(A, B, bx, by, bvx, bvy, t.get('kind'))
    ax, ay, avx, avy = t['after']
    chk['speedRelErr'] = rel(t['speedAfter'], t['speedBefore'])
    chk['ok_speed'] = chk['speedRelErr'] <= 1e-9
    chk['posErr'] = math.hypot(ax - ex, ay - ey)
    chk['ok_pos'] = chk['posErr'] <= 0.05
    vmag = math.hypot(evx, evy)
    chk['velRelErr'] = math.hypot(avx - evx, avy - evy) / vmag
    chk['ok_vel'] = chk['velRelErr'] <= 1e-9
    s, d = local(A, bx, by)
    chk['entry_sd'] = [s, d]
    chk['ok_sd_recorded'] = abs(s - t['s']) < 1e-9 and abs(d - t['d']) < 1e-9
    return t


def s1(page):
    B = {'x': 800, 'y': 200, 'angle': PI / 2, 'h': 45, 'name': 'B', 'color': '#a259ff'}
    st = run(page, wcfg({'x': 300, 'y': 250, 'vx': 0, 'vy': 0}, [A_FLOOR, B]), 20000)
    chk = {}
    t = teleport_checks(st, A_FLOOR, B, chk)
    chk['final'] = [st['x'], st['y'], st['vx'], st['vy']]
    chk['ok_down_below_B'] = bool(t) and st['vy'] > 0 and st['y'] > B['y'] and t['after'][3] > 0 \
        and abs(st['x'] - B['x']) < 1e-6
    return chk


def s2(page):
    B = {'x': 900, 'y': 300, 'angle': PI, 'h': 45, 'name': 'B', 'color': '#a259ff'}
    st = run(page, wcfg({'x': 300, 'y': 250, 'vx': 0, 'vy': 0}, [A_FLOOR, B]), 20000)
    chk = {}
    t = teleport_checks(st, A_FLOOR, B, chk)
    chk['final'] = [st['x'], st['y'], st['vx'], st['vy']]
    chk['ok_moves_left'] = bool(t) and st['vx'] < 0 and t['after'][2] < 0 and st['x'] < B['x']
    return chk


def s3(page):
    """Ball dropped with its centre path 3 px outside A's capture zone lands on A's host line, 0 teleports.
    (Free-standing portals: the r = 2 ball fell past the plane; on a wall the line piece next to the
    opening catches it.) TASK-074: a ball touching the opening is captured, so 'outside' now means
    |s| = h + r + 3 (was h + 3)."""
    B = {'x': 800, 'y': 200, 'angle': PI / 2, 'h': 45, 'name': 'B', 'color': '#a259ff'}
    chk = {'x': {}}
    for r in (2, 10):
        x = A_FLOOR['x'] + A_FLOOR['h'] + r + 3
        chk['x']['r%d' % r] = x
        c = wcfg({'x': x, 'y': 250, 'vx': 0, 'vy': 0, 'r': r}, [A_FLOOR, B])
        page.evaluate('c => window.__portalTest.setup(c)', c)
        check_geometry(page, c)
        st = w_run(page, c['ball'], lines=c['lines'], portals=c['portals'], steps=20000)
        chk['r%d' % r] = {'teleports': len(st['teleports']), 'rimHits': st['rimHits'], 'hostHits': st['hostHits'],
                          'minD': st['minD'], 'final': st['final']}
    r2, r10 = chk['r2'], chk['r10']
    chk['teleports'] = [r2['teleports'], r10['teleports']]
    chk['ok_r2_no_teleport'] = r2['teleports'] == 0
    # r = 2 misses the capture zone (3 px beyond h + r) and bounces off the piece: centre never closer than r to the line
    chk['ok_r2_bounced_off_piece'] = r2['rimHits'] == 0 and r2['hostHits'] >= 1 and r2['minD'] > 1 \
        and r2['final'][1] < A_FLOOR['y'] - 2
    chk['ok_r10_no_teleport'] = r10['teleports'] == 0
    chk['ok_r10_stayed_in_front'] = r10['minD'] > 0 and r10['final'][1] < A_FLOOR['y']
    chk['ok_r10_finite'] = all(math.isfinite(v) for v in r10['final'])
    return chk


def angdiff(a, b):
    """a - b wrapped to (-PI, PI]."""
    d = math.fmod(a - b, 2 * PI)
    if d <= -PI:
        d += 2 * PI
    if d > PI:
        d -= 2 * PI
    return d


def portal(x, y, deg, name):
    return {'x': x, 'y': y, 'angle': deg * PI / 180, 'h': 45, 'name': name,
            'color': '#ff9a2e' if name == 'A' else '#b46cff'}


def at_local(P, s, d):
    nx, ny, tx, ty = frame(P)
    return P['x'] + s * tx + d * nx, P['y'] + s * ty + d * ny


def s4(page):
    """Angled pairs, ball aimed through A's centre from its front: 1 teleport, v rotated by angB-angA+PI."""
    out, ok = {}, True
    for key, (da, db) in (('A30_B135', (30, 135)), ('A-60_B200', (-60, 200))):
        A, B = portal(400, 400, da, 'A'), portal(900, 300, db, 'B')
        nx, ny, _, _ = frame(A)
        x, y = at_local(A, 0, 30)
        st = run(page, wcfg({'x': x, 'y': y, 'vx': -0.05 * nx, 'vy': -0.05 * ny}, [A, B]), 2000)
        chk = {}
        t = teleport_checks(st, A, B, chk)
        if t:
            rot = math.atan2(t['after'][3], t['after'][2]) - math.atan2(t['before'][3], t['before'][2])
            chk['rotErr'] = abs(angdiff(rot, B['angle'] - A['angle'] + PI))
            chk['ok_rotation'] = chk['rotErr'] <= 1e-9
            chk['ok_entry_near_centre'] = abs(t['s']) < 1
        else:
            chk['ok_rotation'] = False
        chk['pass'] = all(v for k, v in chk.items() if k.startswith('ok_'))
        ok &= chk['pass']
        out[key] = chk
    out['ok_all_pairs'] = ok
    out['teleports'] = [out[k]['teleports'] for k in ('A30_B135', 'A-60_B200')]
    out['speedRelErr'] = max(out[k].get('speedRelErr', 1) for k in ('A30_B135', 'A-60_B200'))
    return out


# S5 (back-side entry exits on the partner's back) is retired in TASK-065: wall portals teleport
# front -> back only and the host line blocks a ball behind it (see W2).


def s6(page):
    """Off-centre entry at s = +-(h-1): exit offset s' = -s within 0.05 px.
    Ball radius 0.5: at |s| = 44 a larger ball would hit the rim (1 px away) before reaching the plane."""
    A, B = portal(300, 400, -90, 'A'), portal(900, 300, 180, 'B')
    out = {}
    errs = []
    for sv in (44.0, -44.0):
        x, y = at_local(A, sv, 30)
        st = run(page, wcfg({'x': x, 'y': y, 'vx': 0, 'vy': 0.05, 'r': 0.5}, [A, B]), 2000)
        c = {'teleports': len(st['teleports']), 'rimHits': st['rimHits']}
        if st['teleports']:
            t = st['teleports'][0]
            sIn = local(A, t['before'][0], t['before'][1])[0]
            sOut = local(B, t['after'][0], t['after'][1])[0]
            c.update({'sIn': sIn, 'sOut': sOut, 'err': abs(sOut + sIn)})
            errs.append(c['err'])
        out['s=%+g' % sv] = c
    out['teleports'] = [out[k]['teleports'] for k in ('s=+44', 's=-44')]
    out['maxOffsetErr'] = max(errs) if len(errs) == 2 else None
    out['ok_one_teleport_each'] = out['teleports'] == [1, 1]
    out['ok_offset'] = len(errs) == 2 and max(errs) <= 0.05
    out['ok_sin_is_pm44'] = all(abs(abs(out[k].get('sIn', 0)) - 44) < 1e-6 for k in ('s=+44', 's=-44'))
    return out


def rim_case(page, A, B, ball, steps):
    st = run(page, wcfg(ball, [A, B]), steps)
    c = {'teleports': len(st['teleports']), 'rimHits': st['rimHits'], 'hostHits': st['hostHits'],
         'final': [st['x'], st['y'], st['vx'], st['vy']]}
    c['finite'] = all(math.isfinite(v) for v in c['final'])
    if st['rims']:
        h = st['rims'][0]
        sb, sa = math.hypot(*h['before']), math.hypot(*h['after'])
        c['speedRelErr'] = rel(sa, sb)
        c['vnBefore'] = h['before'][0] * h['n'][0] + h['before'][1] * h['n'][1]
        c['vnAfter'] = h['after'][0] * h['n'][0] + h['after'][1] * h['n'][1]
        rx, ry = h['rim']
        c['distFinal'] = math.hypot(st['x'] - rx, st['y'] - ry)
    _, c['finalD'] = local(A, st['x'], st['y'])
    return c


def s7(page):
    """Edge of the opening (TASK-074 'generous' capture). Centre path inside the opening 4 px from
    the rim (vertical and angled A): the ball touches the opening and is captured, 1 teleport,
    no rim / host-line bounce, |v| preserved, exit in front of B moving away from it.
    Centre path 4 px outside the capture zone (|s| = h + r + 4): the host line piece bounces it,
    0 teleports, back up in front. A ball moving away from A (leaving the opening, v . n > 0) that
    overlaps a rim still reflects off it (the rims stay solid for balls that are not captured)."""
    A, B = portal(300, 400, -90, 'A'), portal(900, 300, 180, 'B')
    out = {}

    def capture(c, st):
        c['bounces'] = st['rimHits'] + st['hostHits']
        if st['teleports']:
            t = st['teleports'][0]
            c['kind'] = t.get('kind')
            c['speedRelErr'] = rel(t['speedAfter'], t['speedBefore'])
            _, c['exitD'] = local(B, t['after'][0], t['after'][1])
            nx, ny, _, _ = frame(B)
            c['exitVn'] = t['after'][2] * nx + t['after'][3] * ny
        return c
    # (a) falling straight down 4 px left of the right rim (345, 400), inside the opening
    st = run(page, wcfg({'x': 341, 'y': 300, 'vx': 0, 'vy': 0.05}, [A, B]), 4000)
    out['vertical'] = capture({'teleports': len(st['teleports'])}, st)
    # (b) angled 30 deg A, ball aimed along -n at a point 4 px inside the rim c + h t, from 30 px out
    A2 = portal(500, 400, -60, 'A')
    nx, ny, tx, ty = frame(A2)
    rx, ry = A2['x'] + 45 * tx, A2['y'] + 45 * ty
    sx, sy = rx + 30 * nx - 4 * tx, ry + 30 * ny - 4 * ty
    st = run(page, wcfg({'x': sx, 'y': sy, 'vx': -0.05 * nx, 'vy': -0.05 * ny}, [A2, B]), 4000)
    out['angled'] = capture({'teleports': len(st['teleports'])}, st)
    # (c) falling straight down 4 px outside the capture zone (|s| = h + r + 4): lands on the host line piece
    out['piece'] = rim_case(page, A, B, {'x': 300 + 45 + 10 + 4, 'y': 300, 'vx': 0, 'vy': 0.05}, 4000)
    # (d) leaving A's opening (moving up, v . n > 0) 3 px above the plane, 4 px inside the right rim,
    #     drifting right into the rim: one rim reflection, no teleport
    out['leaving'] = rim_case(page, A, B, {'x': 341, 'y': 397, 'vx': 0.05, 'vy': -0.01}, 4000)
    caps = (out['vertical'], out['angled'])
    out['teleports'] = [c['teleports'] for c in (out['vertical'], out['angled'], out['piece'], out['leaving'])]
    out['speedRelErr'] = max([c.get('speedRelErr', 1) for c in caps] + [out['leaving'].get('speedRelErr', 1)])
    out['ok_edge_captured'] = out['teleports'] == [1, 1, 0, 0] and all(c.get('kind') == 'touch' for c in caps)
    out['ok_no_bounce_before_capture'] = all(c['bounces'] == 0 for c in caps)
    out['ok_speed'] = out['speedRelErr'] <= 1e-9
    out['ok_exit_front_moving_away'] = all(c.get('exitD', -1) > 0 and c.get('exitVn', -1) > 0 for c in caps)
    out['ok_no_nan'] = out['piece']['finite'] and out['leaving']['finite']
    p = out['piece']
    out['ok_piece_bounce'] = p['hostHits'] >= 1 and p['final'][3] < 0 and p['finalD'] > 10
    lv = out['leaving']
    out['ok_rim_solid_when_leaving'] = lv['rimHits'] >= 1 and lv.get('vnBefore', 0) < 0 < lv.get('vnAfter', 0)
    return out


TRACE_JS = """([frames, per]) => { const f = []
  let maxE = -Infinity, prevStep = -1, twoInStep = 0, steps = 0
  const g = gravitationalAcceleration
  for (let i = 0; i < frames; ++i) {
    for (let k = 0; k < per; ++k) {
      const n0 = portalState.teleports.length
      gamePhysics(); ++steps
      if (portalState.teleports.length - n0 > 1) ++twoInStep
      const E = 0.5 * (ball.speedX * ball.speedX + ball.speedY * ball.speedY) - g * ball.posY
      if (E > maxE) maxE = E
    }
    f.push([ball.posX, ball.posY, ball.speedX, ball.speedY, portalState.teleports.length])
  }
  const steps_ = portalState.teleports.map(t => t.step)
  return {frames: f, maxE: maxE, twoInStep: twoInStep, teleportSteps: steps_, rimHits: portalState.rimHits,
          blockedExits: portalState.blockedExits, blockedReasons: portalState.blocked.map(b => b.reason),
          finite: f.every(r => r.every(Number.isFinite))} }"""


def trace(page, cfg, frames=300, per=500):
    page.evaluate('c => window.__portalTest.setup(c)', cfg)
    check_geometry(page, cfg)
    return page.evaluate(TRACE_JS, [frames, per])


def flips(frames):
    n = 0
    for c in (2, 3):
        sign = 0
        for r in frames:
            sg = (r[c] > 0) - (r[c] < 0)
            if sg and sign and sg != sign:
                n += 1
            if sg:
                sign = sg
    return n


def s8(page):
    """Grazing: parallel to the portal plane at distance r/2 across the opening: <= 1 teleport in 300 frames."""
    out = {}
    # (a) horizontal floor portal, ball moving along it 5 px above (gravity pulls it in once)
    A, B = portal(300, 400, -90, 'A'), portal(900, 300, 180, 'B')
    x, y = at_local(A, -30, 5)
    _, _, tx, ty = frame(A)
    tr = trace(page, wcfg({'x': x, 'y': y, 'vx': 0.05 * tx, 'vy': 0.05 * ty}, [A, B]))
    out['floor'] = {'teleports': tr['frames'][-1][4], 'rimHits': tr['rimHits'], 'finite': tr['finite'], 'final': tr['frames'][-1][:4]}
    # (b) vertical wall portal, ball sliding down parallel to it 5 px in front (gravity along the plane)
    A2 = portal(600, 400, 180, 'A')
    x, y = at_local(A2, 30, 5)                     # t = (0,-1): s = +30 is 30 px above the centre
    tr2 = trace(page, wcfg({'x': x, 'y': y, 'vx': 0, 'vy': 0.05}, [A2, B]))
    out['wall'] = {'teleports': tr2['frames'][-1][4], 'rimHits': tr2['rimHits'], 'finite': tr2['finite'], 'final': tr2['frames'][-1][:4]}
    out['teleports'] = [out['floor']['teleports'], out['wall']['teleports']]
    out['ok_at_most_one'] = max(out['teleports']) <= 1
    out['ok_no_two_in_step'] = tr['twoInStep'] == 0 and tr2['twoInStep'] == 0
    out['ok_finite'] = tr['finite'] and tr2['finite']
    return out


def s9(page):
    """Loop: two floor portals at the same y, ball dropped into A keeps cycling."""
    A, B = portal(300, 400, -90, 'A'), portal(700, 400, -90, 'B')
    cfg = wcfg({'x': 300, 'y': 250, 'vx': 0, 'vy': 0}, [A, B])
    g = page.evaluate('gravitationalAcceleration')
    E0 = -g * 250
    tr = trace(page, cfg)
    fr = tr['frames']
    tele = fr[-1][4]
    pts = [(300.0, 250.0, 0)] + [(r[0], r[1], r[4]) for r in fr]
    win = []
    for i in range(0, 300, 10):
        w = pts[i:i + 11]
        maxDisp = max(math.hypot(p[0] - w[0][0], p[1] - w[0][1]) for p in w)
        travel = sum(math.hypot(w[j + 1][0] - w[j][0], w[j + 1][1] - w[j][1])
                     for j in range(len(w) - 1) if w[j + 1][2] == w[j][2])
        win.append(min(maxDisp, travel))
    steps = tr['teleportSteps']
    out = {'teleports': tele, 'E0': E0, 'energyMax': tr['maxE'], 'energyExcess': tr['maxE'] - E0,
           'minMoveIn10Frames': min(win), 'twoInStep': tr['twoInStep'],
           'uniqueTeleportSteps': len(set(steps)) == len(steps)}
    out['ok_cycles'] = tele >= 4
    out['ok_one_per_step'] = tr['twoInStep'] == 0 and out['uniqueTeleportSteps']
    out['ok_energy'] = tr['maxE'] <= E0 + 1e-6
    out['ok_not_stuck'] = min(win) > 1
    out['ok_finite'] = tr['finite']
    return out


def s10(page):
    """High speed 0.2 px/step straight through A's centre: exactly 1 teleport."""
    A, B = portal(300, 400, -90, 'A'), portal(900, 300, 180, 'B')
    out = {}
    for key, x0 in (('aligned', 300.0), ('offgrid', 300.0)):
        y0 = 300.0 if key == 'aligned' else 300.07
        st = run(page, wcfg({'x': x0, 'y': y0, 'vx': 0, 'vy': 0.2}, [A, B]), 20000)
        chk = {}
        teleport_checks(st, A, B, chk)
        out[key] = chk
    out['teleports'] = [out['aligned']['teleports'], out['offgrid']['teleports']]
    out['speedRelErr'] = max(out[k].get('speedRelErr', 1) for k in ('aligned', 'offgrid'))
    out['ok_exactly_one'] = out['teleports'] == [1, 1]
    out['ok_checks'] = all(all(v for k, v in out[c].items() if k.startswith('ok_')) for c in ('aligned', 'offgrid'))
    return out


def s11(page):
    """Exit 12 px from a level line parallel to B in front of it (closer than the ball radius): since TASK-172 the
    exit is refused (blocked, reason 'overlap', no teleport; before, it teleported onto the line); not stuck,
    <= 4 velocity sign flips."""
    A = portal(300, 400, 0, 'A')                 # wall facing right; ball comes in from the right
    B = portal(900, 500, -90, 'B')               # floor facing up; line 12 px above it
    line = [850, 488, 950, 488]
    tr = trace(page, wcfg({'x': 400, 'y': 400, 'vx': -0.05, 'vy': 0}, [A, B], lines=[line]))
    fr = tr['frames']
    disp = math.hypot(fr[-1][0] - 400, fr[-1][1] - 400)
    out = {'teleports': fr[-1][4], 'displacement': disp, 'flips': flips(fr), 'rimHits': tr['rimHits'],
           'blockedExits': tr.get('blockedExits'), 'blockedReasons': tr.get('blockedReasons'), 'final': fr[-1][:4]}
    out['ok_overlap_exit_blocked'] = (out['teleports'] == 0 and (out['blockedExits'] or 0) >= 1
                                      and set(out['blockedReasons'] or []) == {'overlap'})
    out['ok_not_stuck'] = disp > 5
    out['ok_flips'] = out['flips'] <= 4
    out['ok_finite'] = tr['finite']
    return out


S12_JS = """([cfg, l1, l2]) => {
  window.__portalTest.setup(cfg)                // wall portals on a scratch level (restart() -> its ball start)
  handleClick(l1)                               // starts the player line (real click path)
  if (!line) return {error: 'line not started'}
  bounce.calcSync(l2)                           // mousemove preview (synchronous twin)
  const preview = bounce.positions.map(p => [p.x, p.y])
  const stateAfterPreview = {teleports: portalState.teleports.length, prevD: portalState.prevD.slice()}
  handleClick(l2)                               // places the line -> physics = true
  const placed = !line && physics
  const real = [], onMap = [], realRestart = restartKeepLines   // the off-map reset (TASK-087)
  let restarted = false, tpSteps = null
  const realPhysics = gamePhysics, pl = lines[lines.length - 1]
  let minDist = Infinity
  gamePhysics = function () {                   // per-step distance to the player line (until the first restart)
    realPhysics()
    if (restarted) return
    const dx = pl.posX2 - pl.posX, dy = pl.posY2 - pl.posY
    const u = Math.max(0, Math.min(1, ((ball.posX - pl.posX) * dx + (ball.posY - pl.posY) * dy) / (dx * dx + dy * dy)))
    minDist = Math.min(minDist, Math.hypot(ball.posX - pl.posX - u * dx, ball.posY - pl.posY - u * dy))
  }
  restartKeepLines = function () { if (!restarted) tpSteps = portalState.teleports.map(t => t.step); restarted = true; realRestart() }   // the real game restarts an off-map ball
  for (let f = 0; f < preview.length; ++f) {    // real per-frame code path (rAF cannot interleave here)
    gameMechanics()
    real.push([ball.posX, ball.posY]); onMap.push(!restarted)
  }
  restartKeepLines = realRestart
  gamePhysics = realPhysics
  physics = false
  const teleports = tpSteps || portalState.teleports.map(t => t.step)   // teleports before the first restart
  const completed = levelCompletedWindow; levelCompletedWindow = false
  playtestLevel = null
  return {preview, real, onMap, placed, minDist, stateAfterPreview, teleports, completed, nLines: lines.length} }"""


S12_HOST_A = 120     # short floor under A: the ball leaving B (moving left, falling) clears its right end


def s12(page):
    """Path preview (bounce.calcSync) with portals + a player line equals the real run frame by frame."""
    A, B = portal(600, 400, -90, 'A'), portal(1000, 300, 180, 'B')
    cfg = wcfg({'x': 600, 'y': 150, 'vx': 0, 'vy': 0}, [A, B], L=[S12_HOST_A, 300])
    cfg['lineK'] = 1                              # one player line allowed on the scratch level
    r = page.evaluate(S12_JS, [cfg, [450, 560], [850, 440]])
    out = {'placed': r.get('placed'), 'nLinesAtEnd': r.get('nLines'), 'teleportStepsReal': r.get('teleports'),
           'stateAfterPreview': r.get('stateAfterPreview'), 'completed': r.get('completed')}
    if 'error' in r:
        out['error'] = r['error']
        out['ok_ran'] = False
        return out
    n = 0
    errs = []
    for i, (p, q) in enumerate(zip(r['preview'], r['real'])):
        if not r['onMap'][i]:
            break           # the real game restarts an off-map ball, the preview (original design) does not
        errs.append(math.hypot(p[0] - q[0], p[1] - q[1]))
        n += 1
    firstTp = r['teleports'][0] if r['teleports'] else None
    out.update({'previewFrames': len(r['preview']), 'comparedFrames': n, 'maxErr': max(errs) if errs else None,
                'firstTeleportFrame': None if firstTp is None else firstTp // 500})
    out['minDistToPlayerLine'] = r['minDist']        # per step, real run before the first restart
    out['ok_line_touched'] = r['minDist'] <= 10.5   # ball radius 10: the ball bounced off the player line
    out['ok_placed'] = bool(r['placed'])
    out['ok_teleport_in_compared'] = firstTp is not None and firstTp // 500 < n and firstTp > 1
    out['ok_compared_enough'] = n >= 30
    out['ok_match'] = bool(errs) and max(errs) <= 0.5
    out['ok_preview_left_no_state'] = r['stateAfterPreview']['teleports'] == 0 and r['stateAfterPreview']['prevD'] == []
    return out


S13_JS = """([A, B, hosts, frames, cutAt]) => {
  playtestLevel = null
  thisLevel = levelBySrc(1)                    // level 1 by source id (TASK-177)
  const L1 = thisLevel, lv = levels[L1], keep = lv.portals, n0 = lv.lines.length
  // wall portals cut into two host lines appended to level 1 (removed again at the end)
  for (const l of hosts) lv.lines.push(new Line(l[0], l[1], l[2], l[3], dotRadius, levelLineColor, 'line'))
  lv.portals = [{line: n0, u: 0.5, side: -1, h: 45, name: 'A'}, {line: n0 + 1, u: 0.5, side: -1, h: 45, name: 'B'}]
  const traceRun = (n) => { const out = []
    for (let f = 0; f < n; ++f) { for (let k = 0; k < cyclesPerTact; ++k) gamePhysics(); out.push([ball.posX, ball.posY, ball.speedX, ball.speedY]) }
    return out }
  levelChoosed(L1)
  const first = traceRun(frames)
  const firstTeleports = portalState.teleports.map(t => t.step)
  // second attempt: run until the ball is mid-transit (within ball.radius of a portal plane, just after a teleport)
  levelChoosed(L1)
  let midTransit = null
  for (let i = 0; i < cutAt && !midTransit; ++i) {
    gamePhysics()
    const tp = portalState.teleports.length
    if (tp) { const L = portalLocal(B, ball.posX, ball.posY); if (Math.abs(L.d) < ball.radius) midTransit = {step: portalState.steps, d: L.d, prevD: portalState.prevD.slice(), teleports: tp} }
  }
  restart()
  const stateAfterRestart = {prevD: portalState.prevD.slice(), teleports: portalState.teleports.length, steps: portalState.steps, rimHits: portalState.rimHits}
  const second = traceRun(frames)
  const secondTeleports = portalState.teleports.map(t => t.step)
  // also via levelChoosed mid-transit (menu level pick path)
  levelChoosed(L1)
  for (let i = 0; i < (midTransit ? midTransit.step : 0); ++i) gamePhysics()
  levelChoosed(L1)
  const third = traceRun(frames)
  if (keep === undefined) delete lv.portals; else lv.portals = keep
  lv.lines.length = n0
  levelChoosed(L1)
  let same2 = 0, same3 = 0
  for (let i = 0; i < frames; ++i) {
    if (first[i].every((v, k) => v === second[i][k])) ++same2
    if (first[i].every((v, k) => v === third[i][k])) ++same3
  }
  return {frames, midTransit, stateAfterRestart, firstTeleports, secondTeleports, same2, same3} }"""


def s13(page):
    """restart()/levelChoosed() mid-transit clears portal state: the next run reproduces the first exactly."""
    # level 1 ball starts at (512, 125): A right under it, B a wall facing left
    A, B = portal(512, 300, -90, 'A'), portal(1000, 300, 180, 'B')
    r = page.evaluate(S13_JS, [A, B, [wall_line(A), wall_line(B)], 60, 200000])
    out = dict(r)
    out['teleports'] = len(r['firstTeleports'])
    out['ok_first_teleported'] = len(r['firstTeleports']) >= 1
    out['ok_was_mid_transit'] = r['midTransit'] is not None
    out['ok_state_cleared'] = r['stateAfterRestart'] == {'prevD': [], 'teleports': 0, 'steps': 0, 'rimHits': 0}
    out['ok_restart_trace_identical'] = r['same2'] == r['frames'] and r['firstTeleports'] == r['secondTeleports']
    out['ok_levelChoosed_trace_identical'] = r['same3'] == r['frames']
    return out


S14_JS = """(frames) => {
  playtestLevel = null
  const runLevel = (i) => { thisLevel = i; levelChoosed(i); const out = []
    for (let f = 0; f < frames; ++f) { for (let k = 0; k < cyclesPerTact; ++k) gamePhysics(); out.push([ball.posX, ball.posY]) }
    return {out, teleports: portalState.teleports.length, steps: portalState.steps} }
  const res = []
  for (let i = 0; i < levels.length; ++i) {
    const lv = levels[i], had = 'portals' in lv, saved = lv.portals
    delete lv.portals
    const absent = runLevel(i)
    lv.portals = []
    const empty = runLevel(i)
    delete lv.portals
    const realStep = portalStep
    portalStep = function () {}                // the no-portal code path: no portal hook at all
    const none = runLevel(i)
    portalStep = realStep
    if (had) lv.portals = saved                // portal levels (11+) keep their pair
    let diffAbsent = 0, diffEmpty = 0
    for (let f = 0; f < frames; ++f) {
      if (absent.out[f][0] !== none.out[f][0] || absent.out[f][1] !== none.out[f][1]) ++diffAbsent
      if (empty.out[f][0] !== none.out[f][0] || empty.out[f][1] !== none.out[f][1]) ++diffEmpty
    }
    res.push({level: lv.srcId, index: i, hadPortals: had, teleports: absent.teleports + empty.teleports, portalSteps: absent.steps + empty.steps, diffAbsent, diffEmpty})
  }
  thisLevel = 0; levelChoosed(0)
  return res.sort((a, b) => a.level - b.level) }"""


def s14(page):
    """A level without `portals` (or with []) has no portal behaviour: 0 teleports, trace identical to no hook."""
    res = page.evaluate(S14_JS, 300)
    out = {'levels': res, 'levelCount': page.evaluate('levels.length')}
    out['teleports'] = sum(r['teleports'] for r in res)
    out['mismatchingFrames'] = sum(r['diffAbsent'] + r['diffEmpty'] for r in res)
    out['ok_no_teleports'] = out['teleports'] == 0
    out['ok_no_portal_steps'] = all(r['portalSteps'] == 0 for r in res)
    out['ok_identical'] = out['mismatchingFrames'] == 0
    # every level is covered: the 10 original ones plus any portal levels added later (11+)
    out['ok_levels'] = len(res) == out['levelCount'] and len(res) >= 10
    return out


# ---- Wall portals (TASK-064): one-sided teleport, host line split while in front ----
# Standard pair: A cut into a floor (450,600)-(750,600) facing up, B into the wall x = 1040
# (0..450) at y = 250 facing +x.
W_LINES = [[450, 600, 750, 600], [1040, 0, 1040, 450]]
W_PORTALS = [{'line': 0, 'u': 0.5, 'side': -1, 'h': 45, 'name': 'A'},
             {'line': 1, 'u': 250 / 450, 'side': -1, 'h': 45, 'name': 'B'}]

# Runs one wall-portal configuration step by step and returns a compact summary:
#  teleports (step, from, to, exit position / velocity in the exit portal's frame),
#  W5 window: host-line collisions of the exit portal's host line within 50 steps after each
#   teleport, split by the velocity's normal component before the hit (vn >= 0: moving away),
#  A-tracking until the first teleport: min d of the ball in front of/behind A's host segment
#   (only while the centre projects onto the segment) and front->back crossings of the segment,
#  end: 'left' (off the map), 'settled' (|v| < 1e-4 for 20000 steps) or 'steps'.
W_RUN_JS = r"""([cfg, maxSteps, traj]) => {
  const T = window.__portalTest; T.setup(cfg)
  const P = currentPortals() || [], A = P[0] || {x: 0, y: 0, angle: 0, line: 0}   // no portals: plain-line reference run
  const la = curLevel().lines[A.line]
  const lp = (l, x, y) => { const dx = l.posX2 - l.posX, dy = l.posY2 - l.posY
    return ((x - l.posX) * dx + (y - l.posY) * dy) / (dx * dx + dy * dy) }
  let prevD = portalLocal(A, ball.posX, ball.posY).d, minD = Infinity, leftExtent = false, passThroughs = 0
  const wins = [], tps = [], path = []
  let end = 'steps', step = 0, still = 0
  for (; step < maxSteps; ++step) {
    const n0 = portalState.teleports.length
    gamePhysics()
    const n1 = portalState.teleports.length, st = portalState.steps
    if (n1 > n0) {
      const t = portalState.teleports[n1 - 1], Q = P.find(q => q.name === t.to), f = portalFrame(Q)
      const L = portalLocal(Q, t.after[0], t.after[1])
      tps.push({step: t.step, from: t.from, to: t.to, s: t.s, d: t.d, exitS: L.s, exitD: L.d,
                exitVn: (t.after[2] * f.nx + t.after[3] * f.ny) / Math.hypot(t.after[2], t.after[3])})
      wins.push({step: t.step, line: Q.line, Q: Q, hits: 0, awayHits: 0})
    }
    const h = portalState.hostHit
    if (h && h.step === st)
      for (const w of wins)
        if (st > w.step && st - w.step <= 50 && h.line === w.line) {
          const f = portalFrame(w.Q), vn = h.v[0] * f.nx + h.v[1] * f.ny
          ++w.hits; if (vn >= 0) ++w.awayHits
        }
    const L = portalLocal(A, ball.posX, ball.posY), u = lp(la, ball.posX, ball.posY)
    if (n1 === 0 && !leftExtent) {
      if (L.d <= 0 && (u < 0 || u > 1)) leftExtent = true
      else if (u >= 0 && u <= 1) {
        if (L.d < minD) minD = L.d
        if (prevD > 0 && L.d <= 0) ++passThroughs
      }
    }
    prevD = L.d
    if (traj && step % traj === 0) path.push([ball.posX, ball.posY])
    if (!ball.onMap()) { end = 'left'; break }
    if (Math.hypot(ball.speedX, ball.speedY) < 1e-4) { if (++still >= 20000) { end = 'settled'; break } } else still = 0
  }
  return {steps: step, end, teleports: tps, windows: wins.map(w => ({step: w.step, line: w.line, hits: w.hits, awayHits: w.awayHits})),
          minD: minD === Infinity ? null : minD, passThroughs, leftExtent, hostHits: portalState.hostHits,
          rimHits: portalState.rimHits, final: [ball.posX, ball.posY, ball.speedX, ball.speedY], r: ball.radius, path} }"""


def w_run(page, ball, lines=None, portals=None, steps=40000, traj=0):
    cfg = {'wall': True, 'lines': lines or W_LINES, 'portals': W_PORTALS if portals is None else portals, 'ball': ball}
    return page.evaluate(W_RUN_JS, [cfg, steps, traj])


W5_RUNS = []        # every W1 / W4 run, checked by W5


def w1(page):
    """Ball thrown at A's front inside the opening: 1 teleport, leaves B's front moving away from B's wall."""
    out = {}
    for key, b in (('drop', {'x': 600, 'y': 450, 'vx': 0, 'vy': 0}),
                   ('thrown', {'x': 560, 'y': 500, 'vx': 0.02, 'vy': 0.05})):
        r = w_run(page, b)
        W5_RUNS.append(('W1.' + key, r))
        t = r['teleports'][0] if r['teleports'] else {}
        out[key] = {'teleports': len(r['teleports']), 'end': r['end'], 'entry_sd': [t.get('s'), t.get('d')],
                    'exit_sd': [t.get('exitS'), t.get('exitD')], 'exitVnOverSpeed': t.get('exitVn'),
                    'to': t.get('to'), 'final': r['final']}
    cases = [out['drop'], out['thrown']]
    out['teleports'] = [c['teleports'] for c in cases]
    out['exitVnOverSpeed'] = [c['exitVnOverSpeed'] for c in cases]
    out['ok_one_teleport'] = out['teleports'] == [1, 1] and all(c['to'] == 'B' for c in cases)
    out['ok_exit_front'] = all(c['exit_sd'][1] is not None and c['exit_sd'][1] >= 0 for c in cases)
    out['ok_moving_away_from_B'] = all((c['exitVnOverSpeed'] or 0) > 0.5 for c in cases)
    out['ok_left_map'] = all(c['end'] == 'left' and c['final'][0] > 1040 for c in cases)
    return out


def w2(page):
    """Ball hitting the back of A's (and B's) wall at the opening bounces off: 0 teleports."""
    out = {}
    cases = {'A_back': ({'x': 600, 'y': 700, 'vx': 0, 'vy': -0.1}, 'y'),
             'B_back': ({'x': 980, 'y': 250, 'vx': 0.1, 'vy': 0}, 'x')}
    for key, (b, axis) in cases.items():
        r = w_run(page, b)
        out[key] = {'teleports': len(r['teleports']), 'hostHits': r['hostHits'], 'end': r['end'], 'final': r['final']}
        # bounced: the velocity component that was into the wall is reversed
        out[key]['bounced'] = r['final'][3] > 0 if axis == 'y' else r['final'][2] < 0
    out['teleports'] = [out[k]['teleports'] for k in cases]
    out['ok_no_teleport'] = out['teleports'] == [0, 0]
    out['ok_bounced'] = all(out[k]['bounced'] and out[k]['hostHits'] >= 1 for k in cases)
    out['ok_stayed_behind'] = out['A_back']['final'][1] > 600 and out['B_back']['final'][0] < 1040
    return out


def w3(page):
    """Ball hitting A's / B's host line outside the opening: same trajectory as a plain line, 0 teleports."""
    out = {}
    cases = {'A_left': {'x': 500, 'y': 450, 'vx': 0, 'vy': 0},
             'A_right': {'x': 700, 'y': 450, 'vx': 0, 'vy': 0},
             'B_above': {'x': 1100, 'y': 120, 'vx': -0.1, 'vy': 0}}
    for key, b in cases.items():
        r = w_run(page, b, steps=30000, traj=50)
        plain = w_run(page, b, portals=[], steps=30000, traj=50)
        dev = max(math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(r['path'], plain['path']))
        out[key] = {'teleports': len(r['teleports']), 'hostHits': r['hostHits'], 'maxDevFromPlainLine': dev,
                    'samples': len(r['path']), 'samePathLength': len(r['path']) == len(plain['path'])}
    out['teleports'] = [out[k]['teleports'] for k in cases]
    out['maxDevFromPlainLine'] = max(out[k]['maxDevFromPlainLine'] for k in cases)
    out['ok_no_teleport'] = out['teleports'] == [0, 0, 0]
    out['ok_hit_host_line'] = all(out[k]['hostHits'] >= 1 for k in cases)
    out['ok_like_plain_line'] = out['maxDevFromPlainLine'] <= 1e-9 and all(out[k]['samePathLength'] for k in cases)
    return out


def w4(page, n=200, seed=64):
    """200 seeded throws at A's opening near the rims (|s| in [h - r, h]): never behind A's wall without a teleport."""
    rng = random.Random(seed)
    A = {'x': 600.0, 'y': 600.0}           # A centre; t_A = (1, 0) (side -1 on a left-to-right floor), n_A = (0, -1)
    h, r = 45, 10
    res = []
    for k in range(n):
        s = rng.uniform(h - r, h) * rng.choice((-1, 1))
        theta = rng.uniform(-60, 60) * PI / 180              # angle from -n (straight into the wall)
        speed = rng.uniform(0.03, 0.15)
        dist = rng.uniform(25, 60)
        dx, dy = math.sin(theta), math.cos(theta)            # direction: down (+y), tilted by theta
        tx, ty = A['x'] + s, A['y']
        b = {'x': tx - dx * dist, 'y': ty - dy * dist, 'vx': speed * dx, 'vy': speed * dy}
        rr = w_run(page, b, steps=30000)
        W5_RUNS.append(('W4.%d' % k, rr))
        res.append({'s': s, 'thetaDeg': theta * 180 / PI, 'speed': speed, 'teleports': len(rr['teleports']),
                    'minD': rr['minD'], 'passThroughs': rr['passThroughs'], 'end': rr['end']})
    behind = [x for x in res if x['minD'] is not None and x['minD'] < -r]
    out = {'throws': n, 'seed': seed,
           'teleportedThrows': sum(1 for x in res if x['teleports']),
           'teleports': sum(x['teleports'] for x in res),
           'minDBehindWall': min(x['minD'] for x in res if x['minD'] is not None),
           'behindWithoutTeleport': len(behind), 'passThroughsWithoutTeleport': sum(x['passThroughs'] for x in res),
           'ends': {e: sum(1 for x in res if x['end'] == e) for e in ('left', 'settled', 'steps')},
           'cases': [[round(x['s'], 3), round(x['thetaDeg'], 2), round(x['speed'], 4), x['teleports'],
                      None if x['minD'] is None else round(x['minD'], 4), x['passThroughs']] for x in res],
           'casesFormat': ['s', 'thetaDeg', 'speed', 'teleports', 'minD', 'passThroughs']}
    out['ok_never_behind_without_teleport'] = out['behindWithoutTeleport'] == 0 and out['passThroughsWithoutTeleport'] == 0
    out['ok_throw_count'] = len(res) == n
    return out


def w5(page):
    """After every teleport of W1/W4: no hit on the exit portal's host line within 50 steps while moving away."""
    if not W5_RUNS:
        w1(page)
        w4(page)
    wins = [(name, w) for name, r in W5_RUNS for w in r['windows']]
    away = [(name, w) for name, w in wins if w['awayHits']]
    out = {'runs': len(W5_RUNS), 'teleportsChecked': len(wins),
           'hitsWithin50': sum(w['hits'] for _, w in wins),
           'hitsWithin50MovingAway': sum(w['awayHits'] for _, w in wins),
           'turnedBackHits': sum(w['hits'] - w['awayHits'] for _, w in wins),
           'offenders': [[n, w['step']] for n, w in away[:20]]}
    out['teleports'] = len(wins)
    out['ok_checked_teleports'] = len(wins) >= 3
    out['ok_no_spurious_exit_hit'] = out['hitsWithin50MovingAway'] == 0
    return out


def w6(page):
    """Two wall portals facing each other across a 400 px gap: the run ends (no endless loop / ping-pong).
    TASK-074: with capture by touch (|s| <= h + r) and the exit clamped to the opening, the fast ball
    keeps passing for longer (each pass a real 400 px trip), so the bound is <= 400 teleports in
    3000 frames (was 20) plus >= 300 steps between consecutive teleports."""
    lines = [[400, 0, 400, 600], [800, 0, 800, 600]]
    portals = [{'line': 0, 'u': 0.5, 'side': -1, 'h': 45, 'name': 'A'},      # x = 400, front +x
               {'line': 1, 'u': 0.5, 'side': 1, 'h': 45, 'name': 'B'}]       # x = 800, front -x
    out = {}
    for key, b in (('slow', {'x': 600, 'y': 285, 'vx': -0.2, 'vy': 0}),
                   ('fast', {'x': 600, 'y': 300, 'vx': -1.0, 'vy': 0})):
        r = w_run(page, b, lines=lines, portals=portals, steps=3000 * 500)
        gaps = [b['step'] - a['step'] for a, b in zip(r['teleports'], r['teleports'][1:])]
        out[key] = {'teleports': len(r['teleports']), 'end': r['end'], 'steps': r['steps'],
                    'frames': r['steps'] // 500, 'final': r['final'], 'minStepsBetweenTeleports': min(gaps) if gaps else None}
    out['teleports'] = [out[k]['teleports'] for k in ('slow', 'fast')]
    out['ok_ended'] = all(out[k]['end'] in ('left', 'settled') for k in ('slow', 'fast'))
    out['ok_teleports_le_400'] = max(out['teleports']) <= 400 and min(out['teleports']) >= 1
    out['ok_no_ping_pong'] = all((out[k]['minStepsBetweenTeleports'] or 1e9) >= 300 for k in ('slow', 'fast'))
    return out


# ---- W7 (TASK-074): the artifacts/portal_physics.png replay ----
# Portal A cut into a vertical level wall x = 900 (100..700) facing left (centre (900, 400); its frame
# t = (-n.y, n.x) = (0, -1), so s = 400 - y and the lower rim is s = -h); B in a floor (150, 650)-(450, 650) facing up. A sloped
# level line (12 deg, descending to the right, x 500..898) rolls the ball into A's lower edge. The ramp
# is placed so the ball centre's rolling path, extended, meets the opening plane (x = 900, d = 0) at
# y = 400 - s: s is the entry offset along the opening, swept in 1 px steps over s = -(h-10..h+20)
# (contactS, the offset at first touch of the wall plane d = r, is about s + r tan(12 deg) = s + 2.1:
# the ball keeps descending while it closes in).
# Each run covers the first approach: deterministic gamePhysics() steps in frames of cyclesPerTact,
# up to W7_MAX_FRAMES, stopped W7_AFTER frames after the first teleport or the first host-line bounce
# (after a bounce the ball hops back up the ramp; a later approach is a new trajectory).
W7_WALL, W7_CX, W7_CY, W7_SLOPE_DEG, W7_X0, W7_X1 = 900, 900, 400, 12, 500, 898
W7_MAX_FRAMES, W7_AFTER = 300, 3


W7_RIDE = 0.5        # measured: the rolling ball's centre rides ~0.5 px above the ideal r / cos(a) offset


def w7_cfg(s, r=10):
    """s = portal-local offset (A's t points up: s = 400 - y, the lower rim is s = -h)."""
    a = W7_SLOPE_DEG * PI / 180
    yc = W7_CY - s                                    # centre path height at x = 900 (the opening plane, d = 0)
    yl = yc + r / math.cos(a) + W7_RIDE               # ramp height under that point (vertical offset r / cos a)
    k = math.tan(a)
    line_y = lambda x: yl + (x - W7_WALL) * k
    ramp = [W7_X0, line_y(W7_X0), W7_X1, line_y(W7_X1)]
    bx = W7_X0 + 25
    by = line_y(bx) - r / math.cos(a) - 0.5           # resting 0.5 px above the ramp
    return {'wall': True, 'ball': {'x': bx, 'y': by, 'vx': 0, 'vy': 0, 'r': r},
            'lines': [[W7_WALL, 100, W7_WALL, 700], [150, 650, 450, 650], ramp],
            'portals': [{'line': 0, 'u': 0.5, 'side': 1, 'h': 45, 'name': 'A'},
                        {'line': 1, 'u': 0.5, 'side': -1, 'h': 45, 'name': 'B'}]}


W7_JS = r"""([cfg, maxFrames, after, keepPath]) => {
  const T = window.__portalTest; T.setup(cfg)
  const P = currentPortals(), A = P[0], fa = portalFrame(A)
  let contact = null, tp = null, bounces = 0, hostBounces = 0, rimBounces = 0, frame = 0, stopAt = Infinity
  const path = [[ball.posX, ball.posY]]
  for (; frame < maxFrames && frame < stopAt; ++frame) {
    for (let k = 0; k < cyclesPerTact; ++k) {
      const n0 = portalState.teleports.length, h0 = portalState.hostHits, r0 = portalState.rimHits
      gamePhysics()
      if (!tp && portalState.teleports.length > n0) {
        const t = portalState.teleports[n0], Q = P.find(q => q.name === t.to), fq = portalFrame(Q), L = portalLocal(Q, t.after[0], t.after[1])
        tp = {step: t.step, frame: frame, from: t.from, to: t.to, kind: t.kind, s: t.s, d: t.d, exitS: L.s, exitD: L.d,
              exitVn: t.after[2] * fq.nx + t.after[3] * fq.ny, speedRelErr: Math.abs(t.speedAfter - t.speedBefore) / t.speedBefore}
        stopAt = frame + 1 + after
      }
      if (!tp && portalState.hostHits && stopAt === Infinity) stopAt = frame + 1 + after
      if (!tp) { hostBounces += portalState.hostHits - h0; rimBounces += portalState.rimHits - r0 }
      const L = portalLocal(A, ball.posX, ball.posY)
      if (!contact && !tp && L.d <= ball.radius) contact = {step: portalState.steps, s: L.s, d: L.d}
    }
    if (keepPath) { if (tp && tp.frame === frame) path.push(null); path.push([ball.posX, ball.posY]) }   // null: trail break at the teleport
  }
  return {tp, contact, hostBounces, rimBounces, hostHits: portalState.hostHits, rimHits: portalState.rimHits,
          firstHostHit: portalState.hostHits ? portalState.hostHit : null, frames: frame, steps: portalState.steps,
          teleports: portalState.teleports.length, final: [ball.posX, ball.posY, ball.speedX, ball.speedY], path,
          h: A.h, r: ball.radius} }"""

W7_SHOT_JS = r"""(path) => {
  window.__w7path = path
  if (!window.__w7draw) {
    window.__w7draw = draw
    draw = function () { window.__w7draw()
      const p = window.__w7path; if (!p || !p.length) return
      ctx.save(); ctx.strokeStyle = 'rgba(255,90,90,.9)'; ctx.lineWidth = 1.5; ctx.setLineDash([3, 4])
      ctx.beginPath(); let pen = false
      for (const q of p) { if (!q) { pen = false; continue } if (pen) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); pen = true }
      ctx.stroke(); ctx.restore() }
  }
  draw(); return true }"""

TASK = None


def w7(page):
    """Edge capture replay of artifacts/portal_physics.png (ball rolling down a ramp into A's lower edge):
    |s| in h-10..h+9 teleports with no bounce, |s| in h+11..h+20 bounces off the host line, no teleport."""
    h, r = 45, 10
    rows = []
    mags = list(range(h - 10, h + 10)) + list(range(h + 11, h + 21))
    for sign in (-1,):                                # the lower rim (the screenshot's case)
        for m in mags:
            sv = sign * m
            res = page.evaluate(W7_JS, [w7_cfg(sv), W7_MAX_FRAMES, W7_AFTER, False])
            tp = res['tp']
            rows.append({'s': sv, 'teleported': tp is not None,
                         'bouncesBeforeTeleport': (res['hostBounces'] + res['rimBounces']) if tp else None,
                         'exitD': tp['exitD'] if tp else None, 'exitVn': tp['exitVn'] if tp else None,
                         'kind': tp['kind'] if tp else None, 'entryS': tp['s'] if tp else None,
                         'entryD': tp['d'] if tp else None, 'speedRelErr': tp['speedRelErr'] if tp else None,
                         'contactS': res['contact']['s'] if res['contact'] else None,
                         'hostHits': res['hostHits'], 'rimHits': res['rimHits'],
                         'hostBounceLogged': res['firstHostHit'] is not None,
                         'firstHostHitStep': res['firstHostHit']['step'] if res['firstHostHit'] else None,
                         'frames': res['frames'], 'vxAtEnd': res['final'][2]})
    cap = [x for x in rows if abs(x['s']) <= h + 9]
    bounce = [x for x in rows if abs(x['s']) >= h + 11]
    out = {'h': h, 'r': r, 'slopeDeg': W7_SLOPE_DEG, 'rows': rows, 'captureRows': len(cap), 'bounceRows': len(bounce),
           'contactMinusS': [min(x['contactS'] - x['s'] for x in rows if x['contactS'] is not None),
                             max(x['contactS'] - x['s'] for x in rows if x['contactS'] is not None)]}
    out['teleports'] = sum(1 for x in rows if x['teleported'])
    out['ok_capture_h-10..h+9'] = len(cap) == 20 and all(x['teleported'] and x['bouncesBeforeTeleport'] == 0 for x in cap)
    out['ok_bounce_h+11..h+20'] = len(bounce) == 10 and all(not x['teleported'] and x['hostBounceLogged'] and x['hostHits'] >= 1
                                                          and x['vxAtEnd'] < 0 for x in bounce)   # bounced back (A faces -x)
    tps = [x for x in rows if x['teleported']]
    out['ok_exit_front_moving_away'] = bool(tps) and all(x['exitD'] > 0 and x['exitVn'] > 0 for x in tps)
    out['ok_speed'] = bool(tps) and all(x['speedRelErr'] <= 1e-9 for x in tps)
    out['ok_touch_kind'] = all(x['kind'] == 'touch' for x in cap)
    if TASK:
        d = os.path.join(ROOT, 'artifacts', TASK)
        os.makedirs(d, exist_ok=True)
        # screenshot: the s = -(h + 9) replay (lower edge, the screenshot's case), W7_AFTER frames after the teleport
        res = page.evaluate(W7_JS, [w7_cfg(-(h + 9)), W7_MAX_FRAMES, W7_AFTER, True])
        page.evaluate(W7_SHOT_JS, res['path'])
        page.wait_for_timeout(200)
        page.screenshot(path=os.path.join(d, 'edge.png'))
        page.evaluate('() => { if (window.__w7draw) { draw = window.__w7draw; delete window.__w7draw } window.__w7path = null }')
        out['screenshot'] = {'s': -(h + 9), 'teleportFrame': res['tp']['frame'] if res['tp'] else None, 'framesRun': res['frames'],
                             'ball': res['final'][:2]}
        with open(os.path.join(d, 'edge.json'), 'w') as f:
            json.dump(dict(out, passAll=all(v for k, v in out.items() if k.startswith('ok_'))), f, separators=(',', ':'))
    return out


# ---- W8-W11 (TASK-104): a plain level line across / in front of a portal opening ----
# Standard pair (W_LINES / W_PORTALS: A in the floor y = 600 centred at x = 600 facing up, s = x - 600;
# B in the wall x = 1040 centred at y = 250 facing +x, s = y - 250) plus one extra non-host line (index 2).
# The line stays solid everywhere: the ball bounces off it and can reach an opening only through the part
# the line leaves free; a ball leaving a portal into the line bounces off it.
# Per step (W_X_JS): teleports, bounces off the extra line (centre within r + 0.5 of it and the velocity's
# component along its normal changed sign, no teleport in that step), crossings of the extra line by the
# centre path on non-teleport steps, NaN, the max number of teleports in any 2000-step window and, for every
# A -> B teleport until the next teleport ('exit window'): steps with the centre behind B (d_B <= 0) or,
# while it projects onto the extra segment, on the other side of the extra line than the exit opening point
# O (= B - s_exit t_B), plus whether the ball bounced off the extra line in that window.
# 'teleportPathsBlocked': teleports whose entry path (centre -> closest opening point) or exit path
# (O -> exit centre) crosses the extra line; 'exitIntoLine': teleports leaving the centre within r of it
# (from O's side: allowed, the next collision bounces the ball off the line); 'blockedExits' (js/portal.js,
# TASK-104): teleports refused because the line lies between O and the exit centre (the ball bounces off the
# entry portal's plane instead; 'blockedList' the first records).
W_X_JS = r"""([cfg, maxSteps]) => {
  const T = window.__portalTest; T.setup(cfg)
  const P = currentPortals(), byName = {}; for (const q of P) byName[q.name] = q
  const X = cfg.lines[cfg.extra]
  const side = (x, y) => (X[2] - X[0]) * (y - X[1]) - (X[3] - X[1]) * (x - X[0])
  const segX = (x0, y0, x1, y1) => { const a0 = side(x0, y0), a1 = side(x1, y1)
    if (!((a0 > 0 && a1 <= 0) || (a0 < 0 && a1 >= 0))) return false
    const b0 = (x1 - x0) * (X[1] - y0) - (y1 - y0) * (X[0] - x0), b1 = (x1 - x0) * (X[3] - y0) - (y1 - y0) * (X[2] - x0)
    return b0 * b1 <= 0 }
  const L = Math.hypot(X[2] - X[0], X[3] - X[1]), lnx = -(X[3] - X[1]) / L, lny = (X[2] - X[0]) / L
  const dist = (x, y) => pointSegDist(x, y, X[0], X[1], X[2], X[3])
  const opening = (Q, x, y) => { const f = portalFrame(Q), s = Math.max(-Q.h, Math.min(Q.h, portalLocalS(Q, x, y)))
    return [Q.x + s * f.tx, Q.y + s * f.ty] }
  let nan = 0, bounces = 0, crossings = 0, still = 0, end = 'steps', step = 0, blocked = 0, exitIntoLine = 0
  const proj = (x, y) => ((x - X[0]) * (X[2] - X[0]) + (y - X[1]) * (X[3] - X[1])) / (L * L)
  const tps = [], wins = [], crossLog = []
  let win = null
  for (; step < maxSteps; ++step) {
    const n0 = portalState.teleports.length, x0 = ball.posX, y0 = ball.posY
    const vn0 = ball.speedX * lnx + ball.speedY * lny
    // gamePhysics() (index.html) split up so a bounce is seen even when the same step teleports
    ball.physics()
    const vn1 = ball.speedX * lnx + ball.speedY * lny
    if (dist(x0, y0) < ball.radius + 0.5 && vn0 * vn1 < 0) { ++bounces; if (win) win.bounced = true }
    ball.move()
    portalStep()
    const n1 = portalState.teleports.length, x1 = ball.posX, y1 = ball.posY
    if (!(Number.isFinite(x1) && Number.isFinite(y1) && Number.isFinite(ball.speedX) && Number.isFinite(ball.speedY))) { ++nan; end = 'nan'; break }
    if (n1 > n0) {
      const t = portalState.teleports[n1 - 1], A = byName[t.from], B = byName[t.to]
      const ei = opening(A, t.before[0], t.before[1]), O = opening(B, t.after[0], t.after[1])
      const pb = segX(t.before[0], t.before[1], ei[0], ei[1]) || segX(O[0], O[1], t.after[0], t.after[1])
      if (pb) ++blocked
      tps.push({step: t.step, from: t.from, to: t.to, kind: t.kind, s: t.s, d: t.d,
                exitD: portalLocalD(B, t.after[0], t.after[1]), exitDistToExtra: dist(t.after[0], t.after[1]), pathBlocked: pb})
      if (dist(t.after[0], t.after[1]) < ball.radius) ++exitIntoLine
      if (win) { wins.push(win); win = null }
      if (t.to === 'B') win = {step: t.step, O: O, oSide: Math.sign(side(O[0], O[1])), behindSteps: 0, wrongSideSteps: 0, bounced: false, steps: 0}
    } else {
      if (segX(x0, y0, x1, y1)) { ++crossings; if (crossLog.length < 10) crossLog.push([step + 1, x0, y0, x1, y1]) }
    }
    if (win) {
      ++win.steps
      if (portalLocalD(byName.B, x1, y1) <= 0) ++win.behindSteps
      const u = proj(x1, y1)
      if (u >= 0 && u <= 1 && Math.sign(side(x1, y1)) !== win.oSide) ++win.wrongSideSteps
    }
    if (!ball.onMap()) { end = 'left'; break }
    if (Math.hypot(ball.speedX, ball.speedY) < 1e-4) { if (++still >= 20000) { end = 'settled'; break } } else still = 0
  }
  if (win) wins.push(win)
  let maxIn2000 = 0
  for (let i = 0, j = 0; i < tps.length; ++i) { while (tps[i].step - tps[j].step >= 2000) ++j; maxIn2000 = Math.max(maxIn2000, i - j + 1) }
  return {steps: step, end, nan, teleports: tps.length, teleportList: tps.slice(0, 12), bounces, crossings, crossLog,
          maxTeleportsIn2000: maxIn2000, teleportPathsBlocked: blocked, exitIntoLine, hostHits: portalState.hostHits, rimHits: portalState.rimHits,
          blockedExits: portalState.blockedExits, blockedList: portalState.blocked.slice(0, 4).map(b => ({step: b.step, from: b.from, to: b.to,
            kind: b.kind, reason: b.reason, s: b.s, d: b.d, before: b.before, after: b.after})),
          exitWindows: wins.map(w => ({step: w.step, steps: w.steps, behindSteps: w.behindSteps, wrongSideSteps: w.wrongSideSteps, bounced: w.bounced})),
          final: [ball.posX, ball.posY, ball.speedX, ball.speedY]} }"""


def wx_run(page, ball, extra, steps):
    cfg = {'wall': True, 'lines': W_LINES + [extra], 'extra': len(W_LINES), 'portals': W_PORTALS, 'ball': ball}
    return page.evaluate(W_X_JS, [cfg, steps])


def wx_common(r):
    """Invariants for every W8-W11 run: no NaN, the centre never crosses the extra line outside a teleport
    step, no teleport path through the extra line, no ping-pong (<= 4 teleports in any 2000 steps)."""
    return r['nan'] == 0 and r['crossings'] == 0 and r['teleportPathsBlocked'] == 0 and r['maxTeleportsIn2000'] <= 4


def wx_summary(r):
    keep = ('steps', 'end', 'nan', 'teleports', 'bounces', 'crossings', 'maxTeleportsIn2000', 'teleportPathsBlocked',
            'exitIntoLine', 'blockedExits', 'blockedList', 'hostHits', 'rimHits', 'final')
    out = {k: r[k] for k in keep}
    out['teleportList'] = r['teleportList'][:6]
    out['exitWindows'] = r['exitWindows'][:6]
    if r['crossLog']:
        out['crossLog'] = r['crossLog']
    return out


def w8(page):
    """Extra line y = 595 (5 px in front of A), x 530..670: covers A's whole opening plus the capture zone
    (|s| <= h + r = 55). Balls dropped / thrown at A bounce off it: 0 teleports."""
    extra = [530, 595, 670, 595]
    out = {'extra': extra}
    for key, b in (('drop', {'x': 600, 'y': 450, 'vx': 0, 'vy': 0}),
                   ('thrown', {'x': 560, 'y': 500, 'vx': 0.02, 'vy': 0.05}),
                   ('edgeDrop', {'x': 548, 'y': 450, 'vx': 0, 'vy': 0})):
        out[key] = wx_summary(wx_run(page, b, extra, 40000))
    cases = [out[k] for k in ('drop', 'thrown', 'edgeDrop')]
    out['teleports'] = [c['teleports'] for c in cases]
    out['bounces'] = [c['bounces'] for c in cases]
    out['ok_no_teleport'] = out['teleports'] == [0, 0, 0]
    out['ok_bounced_off_extra'] = all(c['bounces'] >= 1 for c in cases)
    out['ok_stayed_above_extra'] = all(c['final'][1] < 595 for c in cases)
    out['ok_invariants'] = all(c['nan'] == 0 and c['crossings'] == 0 and c['maxTeleportsIn2000'] <= 4 for c in cases)
    return out


def w9(page):
    """Extra line y = 595 over the right half of A's opening only (x 600..670, s 0..70). A ball dropped at
    s = -23 (free half) teleports A -> B; a ball dropped at s = +23 (covered half) bounces off it, 0 teleports."""
    extra = [600, 595, 670, 595]
    out = {'extra': extra}
    out['free'] = wx_summary(wx_run(page, {'x': 577, 'y': 450, 'vx': 0, 'vy': 0}, extra, 40000))
    out['covered'] = wx_summary(wx_run(page, {'x': 623, 'y': 450, 'vx': 0, 'vy': 0}, extra, 40000))
    f, c = out['free'], out['covered']
    out['teleports'] = [f['teleports'], c['teleports']]
    out['bounces'] = [f['bounces'], c['bounces']]
    out['ok_free_half_teleports'] = f['teleports'] == 1 and f['teleportList'][0]['from'] == 'A' and f['end'] == 'left'
    out['ok_covered_half_bounces'] = c['teleports'] == 0 and c['bounces'] >= 1 and c['final'][1] < 595
    out['ok_invariants'] = all(x['nan'] == 0 and x['crossings'] == 0 and x['teleportPathsBlocked'] == 0
                               and x['maxTeleportsIn2000'] <= 4 for x in (f, c))
    return out


def wx_exit_case(page, b, extra, steps):
    r = wx_run(page, b, extra, steps)
    s = wx_summary(r)
    s['allExitWindows'] = r['exitWindows']
    return s


def wx_windows(out, cases):
    wins = [w for c in cases for w in c.pop('allExitWindows')]
    out['exitWindows'] = len(wins)
    out['exitWindowsWithoutBounce'] = sum(1 for w in wins if not w['bounced'])
    out['exitWindowStepsBehindB'] = sum(w['behindSteps'] for w in wins)
    out['exitWindowStepsWrongSide'] = sum(w['wrongSideSteps'] for w in wins)
    return wins


def blocked_away_from_A(c):
    """Every blocked exit was a touch from A to B and left the ball moving away from A (v . n_A > 0)."""
    return c['blockedExits'] >= 1 and all(b['from'] == 'A' and b['to'] == 'B' and b['after'][3] < 0 for b in c['blockedList'])


def w10(page):
    """Extra line across portal B's opening (exit) in front of it, y 150..350 (s_B -100..100).
    'gap6' (x = 1046, 6 px, the ticket's case): there is no room for the ball (r = 10) between B and the line,
    so every A -> B exit is blocked: no teleport, the ball bounces off A's opening (as it would after
    'teleport, bounce off the line, teleport back') and never crosses the line.
    'gap25' (x = 1065, room for the ball): the ball is teleported A -> B, bounces off the extra line and stays
    on B's front side without crossing it. Both: no NaN, <= 4 teleports in any 2000 steps."""
    out = {}
    g6, g25 = [1046, 150, 1046, 350], [1065, 150, 1065, 350]
    out['extra'] = {'gap6': g6, 'gap25': g25}
    for key, b in (('drop', {'x': 600, 'y': 450, 'vx': 0, 'vy': 0}),
                   ('thrown', {'x': 560, 'y': 500, 'vx': 0.02, 'vy': 0.05}),
                   ('nearRim', {'x': 557, 'y': 450, 'vx': 0, 'vy': 0})):
        out['gap6_' + key] = wx_exit_case(page, b, g6, 60000)
        out['gap25_' + key] = wx_exit_case(page, b, g25, 60000)
    c6 = [out['gap6_' + k] for k in ('drop', 'thrown', 'nearRim')]
    c25 = [out['gap25_' + k] for k in ('drop', 'thrown', 'nearRim')]
    for c in c6:
        c.pop('allExitWindows')
    wx_windows(out, c25)
    out['teleports'] = [c['teleports'] for c in c6 + c25]
    out['blockedExits'] = [c['blockedExits'] for c in c6 + c25]
    out['bounces'] = [c['bounces'] for c in c6 + c25]
    out['ok_gap6_exit_blocked_no_teleport'] = all(c['teleports'] == 0 and blocked_away_from_A(c) for c in c6)
    out['ok_gap6_ball_stays_above_A'] = all(c['final'][1] < 600 and c['final'][0] < 1040 for c in c6)
    out['ok_gap25_teleported_to_B'] = all(c['teleports'] >= 1 and c['teleportList'][0]['from'] == 'A' and
                                          c['teleportList'][0]['to'] == 'B' for c in c25)
    out['ok_gap25_bounced_off_extra_after_exit'] = out['exitWindows'] >= 3 and out['exitWindowsWithoutBounce'] == 0
    out['ok_gap25_stays_on_B_front_side'] = out['exitWindowStepsBehindB'] == 0 and out['exitWindowStepsWrongSide'] == 0
    out['ok_invariants'] = all(wx_common(c) for c in c6 + c25)
    return out


def w11(page):
    """Extra line at 45 deg through B's front zone touching B's lower rim: (1040, 295) up-right to (1110, 225).
    Drops at A's s = 0 / -35 / -40 / -44 would leave B at y = 250 / 285 / 290 / 294 (s_B = -s_A), exit centre
    x = 1050. s = 0: 24.7 px from the line, the ball is teleported, runs into the line and bounces off it and
    stays on B's front side without crossing it. s = -35: the exit centre is just on the opening's side of the
    line but overlapping it (as in S11): since TASK-172 blocked (reason 'overlap'), no teleport, the ball bounces
    off A (before, it was teleported onto the line). s = -40 / -44: the exit centre would be on the far side of
    the line: blocked (reason 'path'), no teleport, the ball bounces off A and never crosses the line.
    All: no NaN, <= 4 teleports in any 2000 steps."""
    extra = [1040, 295, 1110, 225]
    out = {'extra': extra}
    keys = []
    for sA in (0, -35, -40, -44):
        k = 's%d' % sA
        keys.append(k)
        out[k] = wx_exit_case(page, {'x': 600 + sA, 'y': 450, 'vx': 0, 'vy': 0}, extra, 60000)
    tp, ov, bl = keys[:1], keys[1:2], keys[2:]
    wx_windows(out, [out[k] for k in tp])
    for k in ov + bl:
        out[k].pop('allExitWindows')
    cases = [out[k] for k in keys]
    out['teleports'] = [c['teleports'] for c in cases]
    out['blockedExits'] = [c['blockedExits'] for c in cases]
    out['bounces'] = [c['bounces'] for c in cases]
    out['ok_teleported_to_B'] = all(out[k]['teleports'] >= 1 and out[k]['teleportList'][0]['to'] == 'B' for k in tp)
    out['ok_bounced_off_extra_after_exit'] = out['exitWindows'] >= 1 and out['exitWindowsWithoutBounce'] == 0
    out['ok_overlap_exit_blocked'] = all(out[k]['teleports'] == 0 and blocked_away_from_A(out[k]) and
                                         all(b['reason'] == 'overlap' for b in out[k]['blockedList']) for k in ov)
    out['ok_stays_on_B_front_side'] = out['exitWindowStepsBehindB'] == 0 and out['exitWindowStepsWrongSide'] == 0
    out['ok_far_side_exits_blocked'] = all(out[k]['teleports'] == 0 and blocked_away_from_A(out[k]) and
                                           all(b['reason'] == 'path' for b in out[k]['blockedList']) for k in bl)
    out['ok_invariants'] = all(wx_common(c) for c in cases)
    return out


SCENARIOS = {'S1': s1, 'S2': s2, 'S3': s3, 'S4': s4, 'S6': s6, 'S7': s7, 'S8': s8,
             'S9': s9, 'S10': s10, 'S11': s11, 'S12': s12, 'S13': s13, 'S14': s14,
             'W1': w1, 'W2': w2, 'W3': w3, 'W4': w4, 'W5': w5, 'W6': w6, 'W7': w7,
             'W8': w8, 'W9': w9, 'W10': w10, 'W11': w11}

TRAJ_JS = """([frames, nLevels]) => { const out = []
  // levels in source-id order (TASK-177: play order != definition order), so --levels N and --compare
  // address the first N definition levels
  for (let n = 1; n <= Math.min(levels.length, nLevels || levels.length); ++n) {
    const i = levelBySrc(n)
    thisLevel = i; levelChoosed(i)
    const xs = [], ys = []
    for (let f = 0; f < frames; ++f) {
      for (let k = 0; k < cyclesPerTact; ++k) gamePhysics()
      xs.push(ball.posX); ys.push(ball.posY)
    }
    out.push({level: n, nLines: lines.length, x: xs, y: ys})
  }
  return out }"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task')
    ap.add_argument('--scenarios', default='S1,S2,S3')
    ap.add_argument('--out', default='core.json')
    ap.add_argument('--trajectory')
    ap.add_argument('--root', default=ROOT)
    ap.add_argument('--frames', type=int, default=600)
    ap.add_argument('--compare', nargs=2)
    ap.add_argument('--levels', type=int, default=0)
    a = ap.parse_args()
    global TASK
    TASK = a.task

    if a.compare:
        base, cur = (json.load(open(f)) for f in a.compare)
        levels, total = [], 0
        for b, c in zip(base, cur):
            mism = sum(1 for i in range(len(b['x']))
                       if i >= len(c['x']) or b['x'][i] != c['x'][i] or b['y'][i] != c['y'][i])
            mism += max(0, len(c['x']) - len(b['x']))
            total += mism
            levels.append({'level': b['level'], 'frames': len(b['x']), 'nLines': [b['nLines'], c['nLines']],
                           'mismatchingFrames': mism, 'last': [c['x'][-1], c['y'][-1]]})
        # the 10 original levels must match bit for bit; levels appended later (11+, portal
        # levels) have no baseline and are only counted
        res = {'levels': levels, 'levelCount': len(levels), 'sameLevelCount': len(base) == len(cur) == 10,
               'baseLevels': len(base), 'curLevels': len(cur), 'addedLevels': len(cur) - len(base),
               'totalMismatchingFrames': total, 'pass': total == 0 and len(base) == 10 and len(cur) >= len(base)}
        with open(a.out, 'w') as f:
            json.dump(res, f, separators=(',', ':'))
        print('noportal: levels=%d mismatching=%d pass=%s' % (len(levels), total, res['pass']))
        return 0 if res['pass'] else 1

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, a.root)
        if a.trajectory:
            res = page.evaluate(TRAJ_JS, [a.frames, a.levels])
            for lv in res:
                lv['sha256'] = hashlib.sha256(json.dumps([lv['x'], lv['y']], separators=(',', ':')).encode()).hexdigest()
            browser.close()
            with open(a.trajectory, 'w') as f:
                json.dump(res, f, separators=(',', ':'))
            print('trajectory: %d levels x %d frames, errors=%s' % (len(res), a.frames, errors))
            return 1 if errors else 0
        results, ok = {}, True
        for name in a.scenarios.split(','):
            chk = SCENARIOS[name](page)
            chk['pass'] = all(v for k, v in chk.items() if k.startswith('ok_'))
            ok &= chk['pass']
            results[name] = chk
            print(name, 'PASS' if chk['pass'] else 'FAIL',
                  {k: v for k, v in chk.items() if k.startswith('ok_') or k in (
                      'teleports', 'speedRelErr', 'posErr', 'velRelErr', 'maxOffsetErr', 'energyExcess',
                      'minMoveIn10Frames', 'flips', 'displacement', 'maxErr', 'comparedFrames', 'mismatchingFrames',
                      'exitVnOverSpeed', 'minDBehindWall', 'behindWithoutTeleport', 'maxDevFromPlainLine',
                      'hitsWithin50MovingAway', 'teleportsChecked', 'bounces', 'blockedExits', 'exitWindowStepsWrongSide')})
        browser.close()
    results['errors'] = errors
    results['pass'] = ok and not errors
    out_path = a.out if os.path.dirname(a.out) else os.path.join(ROOT, 'artifacts', a.task, a.out)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, separators=(',', ':'))
    print('OK' if results['pass'] else 'FAILED', 'errors=%d' % len(errors))
    return 0 if results['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
