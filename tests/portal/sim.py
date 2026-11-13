#!/usr/bin/env python3
"""Portal physics checks (Playwright, index.html via file://).

  python3 tests/portal/sim.py --task TASK-NNN --scenarios S1,...,S14 [--out suite.json]
      -> artifacts/TASK-NNN/core.json (compact), exit 1 if any check fails.
  python3 tests/portal/sim.py --trajectory OUT.json [--root DIR] [--frames 600]
      -> x, y after every frame (500 gamePhysics steps) for levels 1..10 without
         player lines, loaded from DIR/index.html (default: this repo). Used to
         compare against a pre-portal checkout.
  python3 tests/portal/sim.py --compare BASE.json CUR.json --out OUT.json
"""
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


def mapped(A, B, x, y, vx, vy):
    """Independent recomputation of the teleport: (s, d) -> (-s, -d), velocity rotated."""
    s, d = local(A, x, y)
    nx, ny, tx, ty = frame(B)
    a = B['angle'] - A['angle'] + PI
    c, sn = math.cos(a), math.sin(a)
    return (B['x'] - s * tx - d * nx, B['y'] - s * ty - d * ny,
            vx * c - vy * sn, vx * sn + vy * c)


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-300)


def run(page, cfg, steps):
    page.evaluate('c => window.__portalTest.setup(c)', cfg)
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
    ex, ey, evx, evy = mapped(A, B, bx, by, bvx, bvy)
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
    st = run(page, {'ball': {'x': 300, 'y': 250, 'vx': 0, 'vy': 0}, 'portals': [A_FLOOR, B]}, 20000)
    chk = {}
    t = teleport_checks(st, A_FLOOR, B, chk)
    chk['final'] = [st['x'], st['y'], st['vx'], st['vy']]
    chk['ok_down_below_B'] = bool(t) and st['vy'] > 0 and st['y'] > B['y'] and t['after'][3] > 0 \
        and abs(st['x'] - B['x']) < 1e-6
    return chk


def s2(page):
    B = {'x': 900, 'y': 300, 'angle': PI, 'h': 45, 'name': 'B', 'color': '#a259ff'}
    st = run(page, {'ball': {'x': 300, 'y': 250, 'vx': 0, 'vy': 0}, 'portals': [A_FLOOR, B]}, 20000)
    chk = {}
    t = teleport_checks(st, A_FLOOR, B, chk)
    chk['final'] = [st['x'], st['y'], st['vx'], st['vy']]
    chk['ok_moves_left'] = bool(t) and st['vx'] < 0 and t['after'][2] < 0 and st['x'] < B['x']
    return chk


def s3(page):
    B = {'x': 800, 'y': 200, 'angle': PI / 2, 'h': 45, 'name': 'B', 'color': '#a259ff'}
    x = A_FLOOR['x'] + A_FLOOR['h'] + 3
    chk = {'x': x}
    # ball radius 2: the centre path (3 px outside the opening) does not touch the rim
    st = run(page, {'ball': {'x': x, 'y': 250, 'vx': 0, 'vy': 0, 'r': 2}, 'portals': [A_FLOOR, B]}, 20000)
    chk['r2'] = {'teleports': len(st['teleports']), 'rimHits': st['rimHits'], 'final': [st['x'], st['y'], st['vx'], st['vy']]}
    chk['ok_r2_no_teleport'] = len(st['teleports']) == 0
    chk['ok_r2_rim_untouched_passed_plane'] = st['rimHits'] == 0 and st['vx'] == 0 and st['y'] > A_FLOOR['y']
    # default radius 10 at the same x overlaps the rim: it bounces off, still no teleport
    st = run(page, {'ball': {'x': x, 'y': 250, 'vx': 0, 'vy': 0, 'r': 10}, 'portals': [A_FLOOR, B]}, 20000)
    chk['r10'] = {'teleports': len(st['teleports']), 'rimHits': st['rimHits'], 'final': [st['x'], st['y'], st['vx'], st['vy']]}
    chk['ok_r10_no_teleport'] = len(st['teleports']) == 0
    chk['ok_r10_finite'] = all(math.isfinite(v) for v in chk['r10']['final'])
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
        st = run(page, {'ball': {'x': x, 'y': y, 'vx': -0.05 * nx, 'vy': -0.05 * ny}, 'portals': [A, B]}, 2000)
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


def s5(page):
    """Back-side entry into A exits on B's back side, moving away from B."""
    A, B = portal(400, 400, 30, 'A'), portal(900, 300, 180, 'B')
    nx, ny, _, _ = frame(A)
    x, y = at_local(A, 0, -30)
    st = run(page, {'ball': {'x': x, 'y': y, 'vx': 0.05 * nx, 'vy': 0.05 * ny}, 'portals': [A, B]}, 2000)
    chk = {}
    t = teleport_checks(st, A, B, chk)
    if t:
        chk['start_d'] = -30
        sB, dB = local(B, t['after'][0], t['after'][1])
        bnx, bny, _, _ = frame(B)
        chk['exit_d'] = dB
        chk['exit_vn'] = t['after'][2] * bnx + t['after'][3] * bny
        _, dEnd = local(B, st['x'], st['y'])
        chk['final_d'] = dEnd
        chk['ok_entered_from_back'] = t['d'] >= 0       # crossed from d < 0 (behind A) to d >= 0
        chk['ok_exit_back_strict'] = dB <= 0 and dEnd < -10
        chk['ok_moving_away'] = chk['exit_vn'] < 0
    else:
        chk['ok_entered_from_back'] = False
    return chk


def s6(page):
    """Off-centre entry at s = +-(h-1): exit offset s' = -s within 0.05 px.
    Ball radius 0.5: at |s| = 44 a larger ball would hit the rim (1 px away) before reaching the plane."""
    A, B = portal(300, 400, -90, 'A'), portal(900, 300, 180, 'B')
    out = {}
    errs = []
    for sv in (44.0, -44.0):
        x, y = at_local(A, sv, 30)
        st = run(page, {'ball': {'x': x, 'y': y, 'vx': 0, 'vy': 0.05, 'r': 0.5}, 'portals': [A, B]}, 2000)
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
    st = run(page, {'ball': ball, 'portals': [A, B]}, steps)
    c = {'teleports': len(st['teleports']), 'rimHits': st['rimHits'], 'final': [st['x'], st['y'], st['vx'], st['vy']]}
    c['finite'] = all(math.isfinite(v) for v in c['final'])
    if st['rims']:
        h = st['rims'][0]
        sb, sa = math.hypot(*h['before']), math.hypot(*h['after'])
        c['speedRelErr'] = rel(sa, sb)
        c['vnBefore'] = h['before'][0] * h['n'][0] + h['before'][1] * h['n'][1]
        c['vnAfter'] = h['after'][0] * h['n'][0] + h['after'][1] * h['n'][1]
        rx, ry = h['rim']
        c['distFinal'] = math.hypot(st['x'] - rx, st['y'] - ry)
    return c


def s7(page):
    """Rim hit with the centre path outside the opening: 0 teleports, |v| preserved, ball moves away."""
    A, B = portal(300, 400, -90, 'A'), portal(900, 300, 180, 'B')
    out = {}
    # (a) falling straight down 4 px right of the right rim (345, 400)
    out['vertical'] = rim_case(page, A, B, {'x': 349, 'y': 300, 'vx': 0, 'vy': 0.05}, 4000)
    # (b) angled 30 deg A, ball aimed at the rim point c + h t from 20 px out along the outward tangent direction
    A2 = portal(500, 400, -60, 'A')
    _, _, tx, ty = frame(A2)
    nx, ny, _, _ = frame(A2)
    rx, ry = A2['x'] + 45 * tx, A2['y'] + 45 * ty
    sx, sy = rx + 30 * nx + 6 * tx, ry + 30 * ny + 6 * ty      # centre path stays 6 px outside the opening
    out['angled'] = rim_case(page, A2, B, {'x': sx, 'y': sy, 'vx': -0.05 * nx, 'vy': -0.05 * ny}, 4000)
    cases = (out['vertical'], out['angled'])
    out['teleports'] = [c['teleports'] for c in cases]
    out['speedRelErr'] = max(c.get('speedRelErr', 1) for c in cases)
    out['ok_no_teleport'] = all(c['teleports'] == 0 for c in cases)
    out['ok_rim_hit'] = all(c['rimHits'] >= 1 for c in cases)
    out['ok_speed'] = out['speedRelErr'] <= 1e-9
    out['ok_no_nan'] = all(c['finite'] for c in cases)
    out['ok_moves_away'] = all(c.get('vnBefore', 0) < 0 < c.get('vnAfter', 0) and c['distFinal'] > 20 for c in cases)
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
          finite: f.every(r => r.every(Number.isFinite))} }"""


def trace(page, cfg, frames=300, per=500):
    page.evaluate('c => window.__portalTest.setup(c)', cfg)
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
    tr = trace(page, {'ball': {'x': x, 'y': y, 'vx': 0.05 * tx, 'vy': 0.05 * ty}, 'portals': [A, B]})
    out['floor'] = {'teleports': tr['frames'][-1][4], 'rimHits': tr['rimHits'], 'finite': tr['finite']}
    # (b) vertical wall portal, ball sliding down parallel to it 5 px in front (gravity along the plane)
    A2 = portal(600, 400, 180, 'A')
    x, y = at_local(A2, 30, 5)                     # t = (0,-1): s = +30 is 30 px above the centre
    tr2 = trace(page, {'ball': {'x': x, 'y': y, 'vx': 0, 'vy': 0.05}, 'portals': [A2, B]})
    out['wall'] = {'teleports': tr2['frames'][-1][4], 'rimHits': tr2['rimHits'], 'finite': tr2['finite']}
    out['teleports'] = [out['floor']['teleports'], out['wall']['teleports']]
    out['ok_at_most_one'] = max(out['teleports']) <= 1
    out['ok_no_two_in_step'] = tr['twoInStep'] == 0 and tr2['twoInStep'] == 0
    out['ok_finite'] = tr['finite'] and tr2['finite']
    return out


def s9(page):
    """Loop: two floor portals at the same y, ball dropped into A keeps cycling."""
    A, B = portal(300, 400, -90, 'A'), portal(700, 400, -90, 'B')
    cfg = {'ball': {'x': 300, 'y': 250, 'vx': 0, 'vy': 0}, 'portals': [A, B]}
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
        st = run(page, {'ball': {'x': x0, 'y': y0, 'vx': 0, 'vy': 0.2}, 'portals': [A, B]}, 20000)
        chk = {}
        teleport_checks(st, A, B, chk)
        out[key] = chk
    out['teleports'] = [out['aligned']['teleports'], out['offgrid']['teleports']]
    out['speedRelErr'] = max(out[k].get('speedRelErr', 1) for k in ('aligned', 'offgrid'))
    out['ok_exactly_one'] = out['teleports'] == [1, 1]
    out['ok_checks'] = all(all(v for k, v in out[c].items() if k.startswith('ok_')) for c in ('aligned', 'offgrid'))
    return out


def s11(page):
    """Exit 12 px from a level line parallel to B in front of it: not stuck, <= 4 velocity sign flips."""
    A = portal(300, 400, 0, 'A')                 # wall facing right; ball comes in from the right
    B = portal(900, 500, -90, 'B')               # floor facing up; line 12 px above it
    line = [850, 488, 950, 488]
    tr = trace(page, {'ball': {'x': 400, 'y': 400, 'vx': -0.05, 'vy': 0}, 'portals': [A, B], 'lines': [line]})
    fr = tr['frames']
    disp = math.hypot(fr[-1][0] - 400, fr[-1][1] - 400)
    out = {'teleports': fr[-1][4], 'displacement': disp, 'flips': flips(fr), 'rimHits': tr['rimHits'],
           'final': fr[-1][:4]}
    out['ok_used_portal'] = out['teleports'] >= 1
    out['ok_not_stuck'] = disp > 5
    out['ok_flips'] = out['flips'] <= 4
    out['ok_finite'] = tr['finite']
    return out


S12_JS = """([A, B, start, l1, l2]) => {
  window.__portalTest.setup({ball: {x: start[0], y: start[1], vx: 0, vy: 0}, portals: [A, B]})
  handleClick(l1)                               // starts the player line (real click path)
  if (!line) return {error: 'line not started'}
  bounce.calc(l2)                               // mousemove preview
  const preview = bounce.positions.map(p => [p.x, p.y])
  const stateAfterPreview = {teleports: portalState.teleports.length, prevD: portalState.prevD.slice()}
  handleClick(l2)                               // places the line -> physics = true
  const placed = !line && physics
  const real = [], onMap = [], realRestart = restart
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
  restart = function () { if (!restarted) tpSteps = portalState.teleports.map(t => t.step); restarted = true; realRestart() }   // the real game restarts an off-map ball
  for (let f = 0; f < preview.length; ++f) {    // real per-frame code path (rAF cannot interleave here)
    gameMechanics()
    real.push([ball.posX, ball.posY]); onMap.push(!restarted)
  }
  restart = realRestart
  gamePhysics = realPhysics
  physics = false
  const teleports = tpSteps || portalState.teleports.map(t => t.step)   // teleports before the first restart
  const completed = levelCompletedWindow; levelCompletedWindow = false
  return {preview, real, onMap, placed, minDist, stateAfterPreview, teleports, completed, nLines: lines.length} }"""


def s12(page):
    """Path preview (bounce.calc) with portals + a player line equals the real run frame by frame."""
    A, B = portal(600, 400, -90, 'A'), portal(1000, 300, 180, 'B')
    r = page.evaluate(S12_JS, [A, B, [600, 150], [450, 560], [850, 440]])
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


S13_JS = """([A, B, frames, cutAt]) => {
  thisLevel = 0
  const lv = levels[0], keep = lv.portals
  lv.portals = [A, B]
  const traceRun = (n) => { const out = []
    for (let f = 0; f < n; ++f) { for (let k = 0; k < cyclesPerTact; ++k) gamePhysics(); out.push([ball.posX, ball.posY, ball.speedX, ball.speedY]) }
    return out }
  levelChoosed(0)
  const first = traceRun(frames)
  const firstTeleports = portalState.teleports.map(t => t.step)
  // second attempt: run until the ball is mid-transit (within ball.radius of a portal plane, just after a teleport)
  levelChoosed(0)
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
  levelChoosed(0)
  for (let i = 0; i < (midTransit ? midTransit.step : 0); ++i) gamePhysics()
  levelChoosed(0)
  const third = traceRun(frames)
  if (keep === undefined) delete lv.portals; else lv.portals = keep
  levelChoosed(0)
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
    r = page.evaluate(S13_JS, [A, B, 60, 200000])
    out = dict(r)
    out['teleports'] = len(r['firstTeleports'])
    out['ok_first_teleported'] = len(r['firstTeleports']) >= 1
    out['ok_was_mid_transit'] = r['midTransit'] is not None
    out['ok_state_cleared'] = r['stateAfterRestart'] == {'prevD': [], 'teleports': 0, 'steps': 0, 'rimHits': 0}
    out['ok_restart_trace_identical'] = r['same2'] == r['frames'] and r['firstTeleports'] == r['secondTeleports']
    out['ok_levelChoosed_trace_identical'] = r['same3'] == r['frames']
    return out


S14_JS = """(frames) => {
  const runLevel = (i) => { thisLevel = i; levelChoosed(i); const out = []
    for (let f = 0; f < frames; ++f) { for (let k = 0; k < cyclesPerTact; ++k) gamePhysics(); out.push([ball.posX, ball.posY]) }
    return {out, teleports: portalState.teleports.length, steps: portalState.steps} }
  const res = []
  for (let i = 0; i < levels.length; ++i) {
    const lv = levels[i], had = 'portals' in lv
    delete lv.portals
    const absent = runLevel(i)
    lv.portals = []
    const empty = runLevel(i)
    delete lv.portals
    const realStep = portalStep
    portalStep = function () {}                // the no-portal code path: no portal hook at all
    const none = runLevel(i)
    portalStep = realStep
    let diffAbsent = 0, diffEmpty = 0
    for (let f = 0; f < frames; ++f) {
      if (absent.out[f][0] !== none.out[f][0] || absent.out[f][1] !== none.out[f][1]) ++diffAbsent
      if (empty.out[f][0] !== none.out[f][0] || empty.out[f][1] !== none.out[f][1]) ++diffEmpty
    }
    res.push({level: i + 1, hadPortals: had, teleports: absent.teleports + empty.teleports, portalSteps: absent.steps + empty.steps, diffAbsent, diffEmpty})
  }
  thisLevel = 0; levelChoosed(0)
  return res }"""


def s14(page):
    """A level without `portals` (or with []) has no portal behaviour: 0 teleports, trace identical to no hook."""
    res = page.evaluate(S14_JS, 300)
    out = {'levels': res}
    out['teleports'] = sum(r['teleports'] for r in res)
    out['mismatchingFrames'] = sum(r['diffAbsent'] + r['diffEmpty'] for r in res)
    out['ok_no_teleports'] = out['teleports'] == 0
    out['ok_no_portal_steps'] = all(r['portalSteps'] == 0 for r in res)
    out['ok_identical'] = out['mismatchingFrames'] == 0
    out['ok_levels'] = len(res) == 10
    return out


SCENARIOS = {'S1': s1, 'S2': s2, 'S3': s3, 'S4': s4, 'S5': s5, 'S6': s6, 'S7': s7, 'S8': s8,
             'S9': s9, 'S10': s10, 'S11': s11, 'S12': s12, 'S13': s13, 'S14': s14}

TRAJ_JS = """(frames) => { const out = []
  for (let i = 0; i < levels.length; ++i) {
    thisLevel = i; levelChoosed(i)
    const xs = [], ys = []
    for (let f = 0; f < frames; ++f) {
      for (let k = 0; k < cyclesPerTact; ++k) gamePhysics()
      xs.push(ball.posX); ys.push(ball.posY)
    }
    out.push({level: i + 1, nLines: lines.length, x: xs, y: ys})
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
    a = ap.parse_args()

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
        res = {'levels': levels, 'levelCount': len(levels), 'sameLevelCount': len(base) == len(cur) == 10,
               'totalMismatchingFrames': total, 'pass': total == 0 and len(base) == len(cur) == 10}
        with open(a.out, 'w') as f:
            json.dump(res, f, separators=(',', ':'))
        print('noportal: levels=%d mismatching=%d pass=%s' % (len(levels), total, res['pass']))
        return 0 if res['pass'] else 1

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, a.root)
        if a.trajectory:
            res = page.evaluate(TRAJ_JS, a.frames)
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
                      'minMoveIn10Frames', 'flips', 'displacement', 'maxErr', 'comparedFrames', 'mismatchingFrames')})
        browser.close()
    results['errors'] = errors
    results['pass'] = ok and not errors
    out_dir = os.path.join(ROOT, 'artifacts', a.task)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, a.out), 'w') as f:
        json.dump(results, f, separators=(',', ':'))
    print('OK' if results['pass'] else 'FAILED', 'errors=%d' % len(errors))
    return 0 if results['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
