#!/usr/bin/env python3
"""Rim-trap (livelock) regression test for wall portals (TASK-163, Playwright, index.html via file://).

  python3 tests/portal/rimtrap.py --task TASK-NNN [--out rimtrap.json] [--jobs N] [--preview]
      -> artifacts/TASK-NNN/<out> (compact JSON), exit 1 when the level 19 repro is trapped, the
         back-side sweep finds a trap, or (TASK-164) a front-side outcome differs from --baseline
         (default tests/portal/baselines/rimtrap_head_3bcf7b3.json, TASK-271: recorded from git archive 3bcf7b3, the
         TASK-270 elastic contact model before TASK-271; it replaces rimtrap_head_4deacfa.json, the unfixed TASK-163
         code, per-case reasons in artifacts/TASK-271/rebaselined.md) that is not in the --allowlist (default
         tests/portal/allow/rimtrap_task271.json; TASK-201 started them: reviewed changes, each pinned to its baseline
         and new outcome, see baseline_allow.py); front_diff =
         changed cases not allowlisted, front_changed = all changed cases, front_allowlisted = the accepted ones.
  python3 tests/portal/rimtrap.py --task TASK-NNN --controls [--out detector_controls.json]
      -> detector false-positive controls; exit 1 if any control is reported trapped.

The bug: a ball on the BACK of a wall portal's host line next to a rim is reflected by the rim point
(no side check) and by the host line in the same step; the two normals are ~2 deg apart, which turns
the velocity horizontal, and the ball shuttles between the two rims forever with no teleport.

Detector (TRAP_JS, shared with later tickets: `from rimtrap import TRAP_JS, install`):
a run is TRAPPED when the ball centre stays within h + r + 2 px of one portal centre for >= 240
consecutive frames (500 gamePhysics steps each) with no teleport in that window, while its mean
speed ALONG the portal's tangent over the window is > 1 px/frame (speed = |v . t| * 500, v in px/step):
a ball resting still is not a trap, and neither is a ball bouncing in place on the host line (the
physics is elastic, such a ball never settles; it moves along the normal only - TASK-163 preview run
found 17 of these with |v| as the speed, all s = any, angle 0, slow, floorDown). The rim shuttle of
the bug moves along the tangent at ~14 px/frame.

Sweep (b): one wall portal pair (A at (500, 400), h 45, r 10; B a wall facing right at (80, 400)),
A in 5 orientations; the ball is released 3 px before touching A's host line at offset s from A's
centre (s = -(h+r+5)..+(h+r+5), 1 px), incoming angle -60..60 deg (15 deg) from the line normal,
speeds 3 / 10 / 20 px/frame (slow roll, medium, fast drop). Back runs: <= 600 frames, early stop when
the ball leaves the box (|ball - A| > h + r + 100) or the map, or when trapped. (c) front-side
controls on the same grid: <= 120 frames (stop off map); outcome = teleport or not, frame of the
first teleport, ball state rounded to 1e-6 at the end (frame 120 unless it left the map).
"""
import argparse
import json
import math
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tests', 'visual'))
from sim import open_page, wcfg  # noqa: E402
import baseline_allow  # noqa: E402

PI = math.pi
H, R = 45, 10
TRAP_FRAMES = 240
TRAP_MARGIN = 2
TRAP_MIN_SPEED = 1.0          # px/frame
STEPS_PER_FRAME = 500

# Shared livelock detector + runner. window.__rimtrap.run(opts):
#   opts.setup: {kind: 'cfg', cfg} (window.__portalTest.setup) or {kind: 'level', src, lines}
#   opts.frames: max frames; opts.box: stop when |ball - portal[boxPortal]| > box (null = no box);
#   opts.stateAt: frame whose end state is recorded (rounded 1e-6); opts.stopOnTrap
# returns {trapped, trapFrame, trapPortal, frames, end, teleports, firstTeleport, state, hostHits, rimHits}
TRAP_JS = r"""
window.__rimtrap = {
  TRAP_FRAMES: @TF@, MARGIN: @MG@, MIN_SPEED: @MS@, SPF: @SPF@,
  run(o) {
    const S = o.setup
    if (S.kind === 'level') {
      // S.src: level source id (TASK-177; a --root tree without levelBySrc is in definition order)
      thisLevel = (typeof levelBySrc === 'function' ? levelBySrc(S.src) : S.src - 1); playtestLevel = null; levelChoosed(thisLevel)
      for (const l of S.lines) lines.push(new Line(l[0], l[1], l[2], l[3], dotRadius, '#0000ff', 'player'))
      linesK = S.lines.length
    } else window.__portalTest.setup(S.cfg)
    const P = currentPortals() || [], rd = v => Math.round(v * 1e6) / 1e6
    const det = this.detector(P)
    let end = 'frames', f = 0, first = null, state = null
    const bp = o.box != null ? P[o.boxPortal || 0] : null
    for (; f < o.frames; ++f) {
      const n0 = portalState.teleports.length
      let stop = null
      for (let i = 0; i < this.SPF; ++i) {
        gamePhysics()
        if (S.kind === 'level' && flagCollision(curLevel().flagX, curLevel().flagY)) { stop = 'won'; break }
        if (!ball.onMap()) { stop = 'offmap'; break }
      }
      const tp = portalState.teleports.length > n0
      if (tp && first === null) first = f + 1
      det.frame(tp, f + 1)
      const trapped = det.trapped
      if (o.stateAt && f + 1 === o.stateAt) state = [ball.posX, ball.posY, ball.speedX, ball.speedY].map(rd)
      if (stop) { end = stop; ++f; break }
      if (trapped && o.stopOnTrap) { end = 'trapped'; ++f; break }
      if (bp && Math.hypot(ball.posX - bp.x, ball.posY - bp.y) > o.box) { end = 'box'; ++f; break }
    }
    if (o.stateAt && state === null) state = [ball.posX, ball.posY, ball.speedX, ball.speedY].map(rd)
    return {trapped: det.trapped, trapFrame: det.trapFrame, trapPortal: det.trapPortal, frames: f, end, teleports: portalState.teleports.length,
            firstTeleport: first, state, hostHits: portalState.hostHits, rimHits: portalState.rimHits,
            ball: [rd(ball.posX), rd(ball.posY), rd(ball.speedX * this.SPF), rd(ball.speedY * this.SPF)]}
  },
  batch(list) { return list.map(o => this.run(o)) },
  // the detector alone, for runs driven elsewhere (e.g. the real game loop in tests/visual/shoot.py):
  // call frame(teleportedThisFrame, frameNo) once after each frame of SPF gamePhysics steps
  detector(P) {
    const T = this, ring = new Float64Array(T.TRAP_FRAMES)
    let near = -1, run = 0, sum = 0
    return {
      trapped: false, trapFrame: null, trapPortal: null,
      frame(tp, fno) {
        // nearest portal within h + r + margin, no teleport in the window, mean speed
        let k = -1
        for (let i = 0; i < P.length; ++i)
          if (Math.hypot(ball.posX - P[i].x, ball.posY - P[i].y) <= P[i].h + ball.radius + T.MARGIN) { k = i; break }
        // speed ALONG the portal's opening (|v . t|): a ball bouncing in place on the host line (elastic
        // physics, it never settles) moves only along n and is not a trap; the rim shuttle moves along t
        const fk = k >= 0 ? portalFrame(P[k]) : null
        const sp = fk ? Math.abs(ball.speedX * fk.tx + ball.speedY * fk.ty) * T.SPF : 0
        if (tp || k < 0 || k !== near) { run = 0; sum = 0 }
        near = tp ? -1 : k
        if (near >= 0) {
          if (run >= T.TRAP_FRAMES) sum -= ring[run % T.TRAP_FRAMES]
          ring[run % T.TRAP_FRAMES] = sp; sum += sp; ++run
          if (!this.trapped && run >= T.TRAP_FRAMES && sum / T.TRAP_FRAMES > T.MIN_SPEED) {
            this.trapped = true; this.trapFrame = fno; this.trapPortal = P[near].name
          }
        }
      }
    }
  }
}
""".replace('@TF@', str(TRAP_FRAMES)).replace('@MG@', str(TRAP_MARGIN)) \
    .replace('@MS@', repr(TRAP_MIN_SPEED)).replace('@SPF@', str(STEPS_PER_FRAME))


def install(page):
    page.evaluate('() => {' + TRAP_JS + '}')


# level 19 (srcId 19) bug repro (artifacts/ball-physics-bug.mp4)
REPRO_LINES = [[40, 400, 295, 750], [295, 750, 980, 240]]
REPRO_FRAMES = 900

A_C = (500, 400)
B_PORTAL = {'x': 80, 'y': 400, 'angle': 0, 'h': H, 'name': 'B'}
ORIENTS = {'floorUp': -PI / 2, 'floorDown': PI / 2, 'wallLeft': PI, 'wallRight': 0, 'diag45': -PI / 4}
SPEEDS = {'slow': 3, 'medium': 10, 'fast': 20}     # px/frame
ANGLES = list(range(-60, 61, 15))
GAP = 3.0


def release(orient, side, s, ang, speed):
    """Ball start {x, y, vx, vy} (v in px/step): it touches A's host line at offset s on `side`
    ('back' d < 0 or 'front' d > 0) after GAP px, moving at `ang` deg from the line normal."""
    a = ORIENTS[orient]
    nx, ny = math.cos(a), math.sin(a)
    tx, ty = -ny, nx
    sg = -1 if side == 'back' else 1                    # side of the line the ball comes from
    cx, cy = A_C[0] + s * tx + sg * R * nx, A_C[1] + s * ty + sg * R * ny   # centre at contact
    t = math.radians(ang)
    dx, dy = -sg * math.cos(t) * nx + math.sin(t) * tx, -sg * math.cos(t) * ny + math.sin(t) * ty
    v = speed / STEPS_PER_FRAME
    return {'x': cx - GAP * dx, 'y': cy - GAP * dy, 'vx': v * dx, 'vy': v * dy, 'r': R}


def case_cfg(orient, ball):
    A = {'x': A_C[0], 'y': A_C[1], 'angle': ORIENTS[orient], 'h': H, 'name': 'A'}
    c = wcfg(ball, [A, B_PORTAL])
    c.pop('_geom')
    return c


def grid(preview=False):
    lim = H + R + 5
    ss = range(-lim, lim + 1, 6 if preview else 1)
    return [(o, s, a, sp) for o in ORIENTS for s in ss for a in ANGLES for sp in SPEEDS]


def opts_for(side, case):
    o, s, a, sp = case
    cfg = case_cfg(o, release(o, side, s, a, SPEEDS[sp]))
    if side == 'back':
        return {'setup': {'kind': 'cfg', 'cfg': cfg}, 'frames': 600, 'box': H + R + 100, 'stopOnTrap': True}
    return {'setup': {'kind': 'cfg', 'cfg': cfg}, 'frames': 120, 'stateAt': 120}


def worker(job):
    side, cases = job
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, ROOT)
        install(page)
        out = []
        for i in range(0, len(cases), 50):
            out += page.evaluate('l => window.__rimtrap.batch(l)', [opts_for(side, c) for c in cases[i:i + 50]])
        browser.close()
    return out, errors


def sweep(side, cases, jobs):
    chunks = [(side, cases[i::jobs]) for i in range(jobs)]
    with Pool(jobs) as pool:
        res = pool.map(worker, chunks)
    out = [None] * len(cases)
    errs = []
    for i, (r, e) in enumerate(res):
        errs += e
        for j, x in enumerate(r):
            out[i + j * jobs] = x
    return out, errs


def case_key(c):
    return {'orient': c[0], 's': c[1], 'angle': c[2], 'speed': c[3]}


def single(setups):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, ROOT)
        install(page)
        out = [page.evaluate('o => window.__rimtrap.run(o)', o) for o in setups]
        browser.close()
    return out, errors


def out_path(task, out):
    if os.path.dirname(out):
        return out
    d = os.path.join(ROOT, 'artifacts', task)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, out)


def controls(task, out):
    sys.path.insert(0, os.path.join(ROOT, 'tests', 'visual'))
    from shoot import LEVEL19_LINES, LEVEL19_MAX_FRAMES
    plain = [[300, 400, 700, 400]]
    floor_down = {'x': 500, 'y': 400, 'angle': PI / 2, 'h': H, 'name': 'A'}
    names = ['restingPlainLine', 'restingBackOfPortal', 'rollingPlainLine', 'level19Reference']
    setups = [
        # (i) at rest on a plain line, and at rest on the back of a portal's host line (s = 0)
        {'setup': {'kind': 'cfg', 'cfg': {'wall': True, 'lines': plain, 'portals': [],
                                          'ball': {'x': 500, 'y': 400 - R, 'vx': 0, 'vy': 0, 'r': R}}}, 'frames': 600},
        {'setup': {'kind': 'cfg', 'cfg': dict((k, v) for k, v in wcfg({'x': 500, 'y': 400 - R, 'vx': 0, 'vy': 0, 'r': R},
                                                                     [floor_down, B_PORTAL]).items() if k != '_geom')},
         'frames': 600},
        # (ii) rolling across a plain line with no portal (5 px/frame)
        {'setup': {'kind': 'cfg', 'cfg': {'wall': True, 'lines': plain, 'portals': [],
                                          'ball': {'x': 320, 'y': 400 - R, 'vx': 5 / STEPS_PER_FRAME, 'vy': 0, 'r': R}}},
         'frames': 600},
        # (iii) level 19 reference solution
        {'setup': {'kind': 'level', 'src': 19, 'lines': [[a[0], a[1], b[0], b[1]] for a, b in LEVEL19_LINES]},
         'frames': LEVEL19_MAX_FRAMES},
    ]
    res, errors = single(setups)
    doc = {'controls': {n: {k: r[k] for k in ('trapped', 'trapFrame', 'frames', 'end', 'teleports', 'ball')}
                        for n, r in zip(names, res)}, 'pageErrors': errors}
    doc['anyTrapped'] = any(r['trapped'] for r in res)
    doc['level19Won'] = res[3]['end'] == 'won'
    doc['ok'] = not doc['anyTrapped'] and doc['level19Won'] and not errors
    with open(out_path(task, out), 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
    print(json.dumps(doc, separators=(',', ':')))
    return 0 if doc['ok'] else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--out', default=None)
    ap.add_argument('--jobs', type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    ap.add_argument('--preview', action='store_true', help='s step 6 px instead of 1 px')
    ap.add_argument('--controls', action='store_true')
    ap.add_argument('--baseline', default=os.path.join(ROOT, 'tests', 'portal', 'baselines', 'rimtrap_head_3bcf7b3.json'),
                    help='rimtrap.json of the code before the change (default: the TASK-270 elastic contact model, git '
                         'archive 3bcf7b3): front outcomes must match it case by case unless allowlisted (front_diff, exit 1 when '
                         '> 0); "" = no comparison. Never record it from the code under test.')
    ap.add_argument('--allowlist', default=os.path.join(HERE, 'allow', 'rimtrap_task271.json'),
                    help='reviewed changed cases (baseline_allow.py; made for this exact --baseline file); "" = none')
    a = ap.parse_args()
    if a.controls:
        return controls(a.task, a.out or 'detector_controls.json')
    rep, errs = single([{'setup': {'kind': 'level', 'src': 19, 'lines': REPRO_LINES}, 'frames': REPRO_FRAMES}])
    rep = rep[0]
    print('repro', json.dumps(rep, separators=(',', ':')), flush=True)
    cases = grid(a.preview)
    back, e1 = sweep('back', cases, a.jobs)
    front, e2 = sweep('front', cases, a.jobs)
    traps = [dict(case_key(c), frame=r['trapFrame'], ball=r['ball']) for c, r in zip(cases, back) if r['trapped']]
    by_orient, by_s = {}, {}
    for t in traps:
        by_orient[t['orient']] = by_orient.get(t['orient'], 0) + 1
        by_s[str(t['s'])] = by_s.get(str(t['s']), 0) + 1
    doc = {
        'repro': {'trapped': rep['trapped'], 'frame': rep['trapFrame'], 'end': rep['end'], 'frames': rep['frames'],
                  'teleports': rep['teleports'], 'ball': rep['ball'], 'hostHits': rep['hostHits'], 'rimHits': rep['rimHits']},
        'back': {'cases': len(cases), 'traps': len(traps), 'trapsByOrient': by_orient, 'trapsByS': by_s,
                 'backTeleports': sum(1 for r in back if r['teleports']),
                 'backTeleportCases': [case_key(c) for c, r in zip(cases, back) if r['teleports']][:50],
                 'trapCases': traps[:50]},
        'front': {'cases': len(cases), 'teleported': sum(1 for r in front if r['teleports']),
                  'outcomes': [[r['teleports'] > 0, r['firstTeleport'], r['state']] for r in front],
                  'keys': [list(c) for c in cases]},
        'grid': {'orients': ORIENTS, 'angles': ANGLES, 'speeds': SPEEDS, 'sLim': H + R + 5, 'preview': a.preview,
                 'h': H, 'r': R, 'gap': GAP},
        'pageErrors': errs + e1 + e2,
    }
    front_diff = None
    if a.baseline and os.path.exists(a.baseline):
        with open(a.baseline) as fh:
            base = json.load(fh)['front']
        al = baseline_allow.load(a.allowlist, a.baseline)
        bmap = {tuple(k): o for k, o in zip(base['keys'], base['outcomes'])}
        changed = [list(c) for c, o in zip(doc['front']['keys'], doc['front']['outcomes']) if tuple(c) not in bmap or bmap[tuple(c)] != o]
        omap = {tuple(k): o for k, o in zip(doc['front']['keys'], doc['front']['outcomes'])}
        diffs = [c for c in changed if not (tuple(c) in bmap and
                 baseline_allow.accepted(al, '|'.join(map(str, c)), bmap[tuple(c)], omap[tuple(c)]))]
        front_diff = len(diffs)
        doc['front']['allowlist'] = baseline_allow.rel(a.allowlist, ROOT)
        doc['front']['front_changed'] = len(changed)
        doc['front']['front_allowlisted'] = len(changed) - len(diffs)
        doc['front']['baseline'] = os.path.relpath(a.baseline, ROOT)
        doc['front']['baselineCases'] = len(base['keys'])
        doc['front']['diffCases'] = diffs[:50]
    elif a.baseline:
        front_diff = -1      # TASK-201: a named baseline that does not exist fails instead of skipping the comparison
        print('baseline missing: %s' % a.baseline)
    doc['front']['front_diff'] = front_diff
    print('front_diff=%s front_changed=%s front_allowlisted=%s baseline=%s allowlist=%s'
          % (front_diff, doc['front'].get('front_changed'), doc['front'].get('front_allowlisted'), a.baseline or '-',
             a.allowlist or '-'))
    fail = rep['trapped'] or len(traps) > 0 or bool(front_diff)
    doc['fail'] = fail
    with open(out_path(a.task, a.out or 'rimtrap.json'), 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
    print('repro.trapped=%s frame=%s back.cases=%d back.traps=%d byOrient=%s front.cases=%d front.teleported=%d errors=%d'
          % (rep['trapped'], rep['trapFrame'], len(cases), len(traps), by_orient, len(cases),
             doc['front']['teleported'], len(doc['pageErrors'])))
    print('EXIT %d' % (1 if fail else 0))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
