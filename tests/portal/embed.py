#!/usr/bin/env python3
"""Embedded-ball ("stuck in textures") regression test for wall portals (TASK-171, Playwright, index.html via file://).

  python3 tests/portal/embed.py --task TASK-NNN [--out embed.json] [--jobs N] [--preview]
      -> artifacts/TASK-NNN/<out> (compact JSON); exit 1 when the level 24 repro (a) or the synthetic
         sweep (b) has an embedded run.
      --baseline (default tests/portal/baselines/embed_head_3bcf7b3.json, TASK-271: recorded from git archive
         3bcf7b3, the TASK-270 elastic contact model before TASK-271, per-case reasons in artifacts/TASK-271/rebaselined.md;
         before: embed_head_4deacfa.json, the code before TASK-201, and artifacts/TASK-171/baseline.json; '' = off; TASK-172): every case whose baseline exitOverlap was false must keep its outcome
         (diffNonOverlap == 0 in the log, else exit 1); TASK-176: runs with a mirrored blocked face touch
         (record.mirror) are exempt and counted as changedNonOverlapMirrored; TASK-201: so are cases in --allowlist
         (default tests/portal/allow/embed_task271.json, reviewed contact-model changes pinned to their baseline and
         new outcome, see baseline_allow.py), counted as changedNonOverlapAllowlisted.
  python3 tests/portal/embed.py --task TASK-NNN --controls [--out controls.json]
      -> detector false-positive controls (c); exit 1 if any control is embedded (or level 24 is not won).

The bug: on level 24 (srcId 24, 'pick the half') the shelf line (60,360)->(1240,360) starts exactly at
portal B's centre. A ball entering A within ~r of A's centre leaves B with its centre ON the shelf; the
exit check (portalPathBlocked between the opening point O and the exit centre, js/portal.js
portalTeleport) does not see a line that only overlaps the exit (here it is even collinear with the
exit path), and the reflect-on-overlap line collision then flips vy every step without pushing the
ball out: it slides inside the line.

Detector (EMBED_JS, shared with later tickets: `from embed import EMBED_JS, install`):
a run is EMBEDDED when the ball centre stays closer than r/2 to any segment in `lines` for >= 30
consecutive frames (500 gamePhysics steps each, sampled at the end of each frame). A ball resting on
a line sits ~r - 0.5 px from it and is not embedded.

Sweep (b): A floor portal facing up at (500, 600), B a wall portal facing right at (80, 400), h 45,
r 10, host lines 300 px. One extra level line touches B's opening (B frame: n = (1, 0), t = (0, 1)):
  start<th>      : from B's centre into the front, at th = 30..150 deg (30) from t (start90 = level 24's shelf);
  cross<th>_<s0> : through the opening point c + s0 t (s0 = -h/2, 0, h/2) at th, 150 px each side;
  end<s0>_<e>    : coming along n from the front, ending at c + s0 t + e n (s0 = -h/2, 0, h/2; e = 2, 5, 9 < r).
The ball is released 3 px above touching A's opening at offset s = -h..+h (1 px; --preview 5 px),
at 10 px/frame, entry angle -30 / 0 / +30 deg from A's normal; 120 frames (stop off map).
outcomes[caseId] = {teleported, exitOverlap, state120}: exitOverlap marks a teleport whose exit centre
was closer than r to a line other than the exit portal's host line; state120 = [x, y, vx, vy] (v in
px/step) rounded to 1e-6 after frame 120 (or when the ball left the map).
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
EMBED_FRAMES = 30
STEPS_PER_FRAME = 500

# window.__embed.run(opts):
#   opts.setup: {kind: 'cfg', cfg} (window.__portalTest.setup) or {kind: 'level', src, lines, ball}
#     (ball: {x, y, vx, vy} in px/step, optional, placed after levelChoosed)
#   opts.frames: max frames; opts.stateAt: frame whose end state is recorded (rounded 1e-6)
# returns {embedded, embedFrame, embedFrames, maxRun, frames, end, teleports, exitOverlap, state, ball}
EMBED_JS = r"""
window.__embed = {
  FRAMES: @EF@, SPF: @SPF@,
  run(o) {
    const S = o.setup
    if (S.kind === 'level') {
      // S.src: level source id (TASK-177; a --root tree without levelBySrc is in definition order)
      thisLevel = (typeof levelBySrc === 'function' ? levelBySrc(S.src) : S.src - 1); playtestLevel = null; levelChoosed(thisLevel)
      for (const l of (S.lines || [])) lines.push(new Line(l[0], l[1], l[2], l[3], dotRadius, '#0000ff', 'player'))
      linesK = (S.lines || []).length
      if (S.ball) {
        ball.posX = S.ball.x; ball.posY = S.ball.y; ball.speedX = S.ball.vx || 0; ball.speedY = S.ball.vy || 0
      }
      portalReset()
    } else window.__portalTest.setup(S.cfg)
    const P = currentPortals() || [], rd = v => Math.round(v * 1e6) / 1e6
    const det = this.detector()
    let end = 'frames', f = 0, state = null, exitOverlap = false, mirrored = false
    for (; f < o.frames; ++f) {
      let stop = null
      for (let i = 0; i < this.SPF; ++i) {
        const n0 = portalState.teleports.length, m0 = portalState.blocked.length
        gamePhysics()
        for (let k = m0; k < portalState.blocked.length; ++k) if (portalState.blocked[k].mirror) mirrored = true
        if (portalState.teleports.length > n0 && this.exitOverlaps(P, portalState.teleports[portalState.teleports.length - 1]))
          exitOverlap = true
        if (S.kind === 'level' && flagCollision(curLevel().flagX, curLevel().flagY)) { stop = 'won'; break }
        if (!ball.onMap()) { stop = 'offmap'; break }
      }
      det.frame(f + 1)
      if (o.stateAt && f + 1 === o.stateAt) state = [ball.posX, ball.posY, ball.speedX, ball.speedY].map(rd)
      if (stop) { end = stop; ++f; break }
      if (det.embedded && o.stopOnEmbed) { end = 'embedded'; ++f; break }
    }
    if (o.stateAt && state === null) state = [ball.posX, ball.posY, ball.speedX, ball.speedY].map(rd)
    return {embedded: det.embedded, embedFrame: det.embedFrame, embedFrames: det.count, maxRun: det.maxRun, frames: f, end,
            teleports: portalState.teleports.length, exitOverlap, mirrored, state,
            ball: [rd(ball.posX), rd(ball.posY), rd(ball.speedX * this.SPF), rd(ball.speedY * this.SPF)]}
  },
  batch(list) { return list.map(o => this.run(o)) },
  // the teleport record's exit centre (after) is closer than r to a line other than the exit's host line
  exitOverlaps(P, rec) {
    const B = P.find(p => p.name === rec.to)
    const host = B && typeof B.line == 'number' ? curLevel().lines[B.line] : null
    const x = rec.after[0], y = rec.after[1]
    for (const l of lines)
      if (l !== host && pointSegDist(x, y, l.posX, l.posY, l.posX2, l.posY2) < ball.radius) return true
    return false
  },
  // the detector alone: call frame(frameNo) once after each frame of SPF gamePhysics steps
  detector() {
    const T = this
    let run = 0
    return {
      embedded: false, embedFrame: null, count: 0, maxRun: 0,
      frame(fno) {
        let dmin = Infinity
        for (const l of lines) dmin = Math.min(dmin, pointSegDist(ball.posX, ball.posY, l.posX, l.posY, l.posX2, l.posY2))
        if (dmin < ball.radius / 2) { ++run; ++this.count } else run = 0
        if (run > this.maxRun) this.maxRun = run
        if (!this.embedded && run >= T.FRAMES) { this.embedded = true; this.embedFrame = fno }
      }
    }
  }
}
""".replace('@EF@', str(EMBED_FRAMES)).replace('@SPF@', str(STEPS_PER_FRAME))


def install(page):
    page.evaluate('() => {' + EMBED_JS + '}')


# (a) level 24 repro
REPRO_XS = [480, 482]
REPRO_FRAMES = 200

A_P = {'x': 500, 'y': 600, 'angle': -PI / 2, 'h': H, 'name': 'A'}
B_P = {'x': 80, 'y': 400, 'angle': 0, 'h': H, 'name': 'B'}
SPEED = 10                      # px/frame
ENTRY = [-30, 0, 30]            # deg from A's normal
GAP = 3.0


def b_pt(s, d):
    """B-frame (s along t = (0, 1), d along n = (1, 0)) -> page coordinates."""
    return [B_P['x'] + d, B_P['y'] + s]


def geometries():
    g = {}
    for th in range(30, 151, 30):
        c, sn = math.cos(math.radians(th)), math.sin(math.radians(th))
        g['start%d' % th] = b_pt(0, 0) + b_pt(300 * c, 300 * sn)
        for s0 in (-(H // 2), 0, H // 2):
            g['cross%d_%d' % (th, s0)] = b_pt(s0 - 150 * c, -150 * sn) + b_pt(s0 + 150 * c, 150 * sn)
    for s0 in (-(H // 2), 0, H // 2):
        for e in (2, 5, 9):
            g['end%d_%d' % (s0, e)] = b_pt(s0, e + 200) + b_pt(s0, e)
    return g


def release(s, ang):
    """Ball start on A's front: touches A's opening at offset s after GAP px, `ang` deg from -n."""
    nx, ny = math.cos(A_P['angle']), math.sin(A_P['angle'])
    tx, ty = -ny, nx
    cx, cy = A_P['x'] + s * tx + R * nx, A_P['y'] + s * ty + R * ny
    t = math.radians(ang)
    dx, dy = -math.cos(t) * nx + math.sin(t) * tx, -math.cos(t) * ny + math.sin(t) * ty
    v = SPEED / STEPS_PER_FRAME
    return {'x': cx - GAP * dx, 'y': cy - GAP * dy, 'vx': v * dx, 'vy': v * dy, 'r': R}


def grid(preview=False):
    g = geometries()
    ss = range(-H, H + 1, 5 if preview else 1)
    return [(k, s, a) for k in g for s in ss for a in ENTRY], g


def case_id(c):
    return '%s|s%d|a%d' % c


def opts_for(case, geo):
    k, s, a = case
    cfg = wcfg(release(s, a), [A_P, B_P], [geo[k]])
    cfg.pop('_geom')
    return {'setup': {'kind': 'cfg', 'cfg': cfg}, 'frames': 120, 'stateAt': 120}


def worker(job):
    cases, geo = job
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, ROOT)
        install(page)
        out = []
        for i in range(0, len(cases), 50):
            out += page.evaluate('l => window.__embed.batch(l)', [opts_for(c, geo) for c in cases[i:i + 50]])
        browser.close()
    return out, errors


def sweep(cases, geo, jobs):
    with Pool(jobs) as pool:
        res = pool.map(worker, [(cases[i::jobs], geo) for i in range(jobs)])
    out = [None] * len(cases)
    errs = []
    for i, (r, e) in enumerate(res):
        errs += e
        for j, x in enumerate(r):
            out[i + j * jobs] = x
    return out, errs


def single(setups):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, ROOT)
        install(page)
        out = [page.evaluate('o => window.__embed.run(o)', o) for o in setups]
        browser.close()
    return out, errors


def out_path(task, out):
    if os.path.dirname(out):
        return out
    d = os.path.join(ROOT, 'artifacts', task)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, out)


def controls(task, out):
    from shoot import LEVEL24_LINES, LEVEL24_MAX_FRAMES
    plain = [[100, 400, 1200, 400]]
    names = ['restingPlainLine', 'rollingPlainLine', 'level24Reference']
    setups = [
        {'setup': {'kind': 'cfg', 'cfg': {'wall': True, 'lines': plain, 'portals': [],
                                          'ball': {'x': 500, 'y': 400 - R, 'vx': 0, 'vy': 0, 'r': R}}}, 'frames': 200},
        {'setup': {'kind': 'cfg', 'cfg': {'wall': True, 'lines': plain, 'portals': [],
                                          'ball': {'x': 150, 'y': 400 - R, 'vx': 5 / STEPS_PER_FRAME, 'vy': 0, 'r': R}}},
         'frames': 200},
        {'setup': {'kind': 'level', 'src': 24, 'lines': [[a[0], a[1], b[0], b[1]] for a, b in LEVEL24_LINES]},
         'frames': LEVEL24_MAX_FRAMES},
    ]
    res, errors = single(setups)
    doc = {'controls': {n: {k: r[k] for k in ('embedded', 'embedFrame', 'maxRun', 'frames', 'end', 'teleports', 'ball')}
                        for n, r in zip(names, res)}, 'pageErrors': errors}
    doc['anyEmbedded'] = any(r['embedded'] for r in res)
    doc['level24Won'] = res[2]['end'] == 'won'
    doc['ok'] = not doc['anyEmbedded'] and doc['level24Won'] and not errors
    with open(out_path(task, out), 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
    print(json.dumps(doc, separators=(',', ':')))
    print('EXIT %d' % (0 if doc['ok'] else 1))
    return 0 if doc['ok'] else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--out', default=None)
    ap.add_argument('--jobs', type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    ap.add_argument('--preview', action='store_true', help='s step 5 px instead of 1 px')
    ap.add_argument('--controls', action='store_true')
    ap.add_argument('--baseline', default=os.path.join(ROOT, 'tests', 'portal', 'baselines', 'embed_head_3bcf7b3.json'),
                    help="embed.json of the code before the change: diff outcomes of cases whose baseline exitOverlap "
                         "was false ('' = no diff). Never record it from the code under test.")
    ap.add_argument('--allowlist', default=os.path.join(HERE, 'allow', 'embed_task271.json'),
                    help="reviewed changed cases (baseline_allow.py; made for this exact --baseline file); '' = none")
    a = ap.parse_args()
    if a.controls:
        return controls(a.task, a.out or 'controls.json')
    rep, errs = single([{'setup': {'kind': 'level', 'src': 24, 'lines': [], 'ball': {'x': x, 'y': 700, 'vx': 0, 'vy': 0.02}},
                         'frames': REPRO_FRAMES} for x in REPRO_XS])
    repro = [{'x': x, 'embedded': r['embedded'], 'frames': r['embedFrames'], 'embedFrame': r['embedFrame'],
              'maxRun': r['maxRun'], 'teleports': r['teleports'], 'exitOverlap': r['exitOverlap'], 'end': r['end']}
             for x, r in zip(REPRO_XS, rep)]
    for r in repro:
        print('repro', json.dumps(r, separators=(',', ':')), flush=True)
    cases, geo = grid(a.preview)
    res, e1 = sweep(cases, geo, a.jobs)
    emb = [dict(case=case_id(c), frame=r["embedFrame"], frames=r["embedFrames"], exitOverlap=r["exitOverlap"], ball=r["ball"])
           for c, r in zip(cases, res) if r['embedded']]
    by_geo = {}
    for c, r in zip(cases, res):
        if r['embedded']:
            by_geo[c[0]] = by_geo.get(c[0], 0) + 1
    doc = {
        'repro': repro,
        'sweep': {'cases': len(cases), 'embedded': len(emb), 'embeddedByGeometry': by_geo, 'embeddedCases': emb[:50],
                  'teleported': sum(1 for r in res if r['teleports']), 'exitOverlap': sum(1 for r in res if r['exitOverlap'])},
        'outcomes': {case_id(c): {'teleported': r['teleports'] > 0, 'exitOverlap': r['exitOverlap'], 'state120': r['state']}
                     for c, r in zip(cases, res)},
        'mirrored': sorted(case_id(c) for c, r in zip(cases, res) if r['mirrored']),
        'grid': {'A': A_P, 'B': B_P, 'geometries': geo, 'entry': ENTRY, 'speed': SPEED, 'sStep': 5 if a.preview else 1,
                 'h': H, 'r': R, 'gap': GAP, 'frames': 120},
        'pageErrors': errs + e1,
    }
    fail = any(r['embedded'] for r in repro) or len(emb) > 0
    if a.baseline and os.path.exists(a.baseline):
        # TASK-172: the exit-overlap block may only change runs whose pre-fix exit overlapped a line
        with open(a.baseline) as fh:
            base = json.load(fh)['outcomes']
        common = [k for k in base if k in doc['outcomes']]     # --preview runs a subset of the grid
        nonov = [k for k in common if not base[k]['exitOverlap']]
        # TASK-176: a blocked face touch mirrors the ball back about d = r (record.mirror); such a run may change too.
        # Up to its first mirror a run is the TASK-173 code's run, which had diffNonOverlap 0 against this baseline.
        mir = set(doc['mirrored'])
        al = baseline_allow.load(a.allowlist, a.baseline)
        changed = [k for k in nonov if doc['outcomes'][k] != base[k]]
        allowed = [k for k in changed if k not in mir and baseline_allow.accepted(al, k, base[k], doc['outcomes'][k])]
        diff = [k for k in changed if k not in mir and k not in set(allowed)]
        ov = [k for k in common if base[k]['exitOverlap']]
        doc['baselineDiff'] = {'baseline': os.path.relpath(a.baseline, ROOT), 'commonCases': len(common),
                               'nonOverlapCases': len(nonov),
                               'diffNonOverlap': len(diff), 'diffNonOverlapCases': diff[:50],
                               'changedNonOverlapMirrored': len([k for k in changed if k in mir]), 'mirroredCases': len(mir),
                               'changedNonOverlap': len(changed), 'changedNonOverlapAllowlisted': len(allowed),
                               'allowlist': baseline_allow.rel(a.allowlist, ROOT),
                               'overlapCases': len(ov),
                               'overlapChanged': sum(1 for k in ov if doc['outcomes'].get(k) != base[k])}
        print('baseline=%s allowlist=%s nonOverlapCases=%d diffNonOverlap=%d changedNonOverlap=%d changedNonOverlapMirrored=%d '
              'changedNonOverlapAllowlisted=%d mirroredCases=%d overlapCases=%d overlapChanged=%d'
              % (doc['baselineDiff']['baseline'], a.allowlist or '-', len(nonov), len(diff), len(changed),
                 doc['baselineDiff']['changedNonOverlapMirrored'], len(allowed), len(mir), len(ov),
                 doc['baselineDiff']['overlapChanged']))
        fail = fail or len(diff) > 0
    elif a.baseline:
        print('baseline missing: %s' % a.baseline)      # TASK-201: fail instead of skipping the comparison
        doc['baselineDiff'] = {'baseline': a.baseline, 'missing': True}
        fail = True
    doc['fail'] = fail
    with open(out_path(a.task, a.out or 'embed.json'), 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
    print('repro.embedded=%s sweep.cases=%d sweep.embedded=%d byGeometry=%s teleported=%d exitOverlap=%d errors=%d'
          % ([r['embedded'] for r in repro], len(cases), len(emb), by_geo, doc['sweep']['teleported'],
             doc['sweep']['exitOverlap'], len(doc['pageErrors'])))
    print('EXIT %d' % (1 if fail else 0))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
