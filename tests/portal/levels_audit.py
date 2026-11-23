#!/usr/bin/env python3
"""Portal level audit (TASK-174, part 4 of TASK-171..176): every portal level 11-32 (levels[10..31]).

  python3 tests/portal/levels_audit.py --task TASK-NNN --risk [--out risk.json]
      (1) static scan: every non-host level line within r + 2 px of a portal opening (segment c +- h t),
          with its distance; exit 0.
  python3 tests/portal/levels_audit.py --task TASK-NNN [--out sweep.json] [--root DIR] [--levels 23,..]
                                       [--s-step N] [--jobs N]
      (2) dynamic entry sweep on the real levels: for each portal the ball (r 10) is injected GAP px in
          front of the opening (centre c + s t + (r + GAP) n) at s = -h..+h (1 px, --s-step for a
          preview) x entry angles -60, -30, 0, 30, 60 deg from -n, at SPEED px/frame, then runs <= 200
          frames (500 gamePhysics steps each; stops when won / off map / embedded / trapped).
          Detectors (shared): window.__embed.detector (tests/portal/embed.py: centre closer than r/2 to a
          line for >= 30 consecutive frames) and window.__rimtrap.detector (tests/portal/rimtrap.py, the
          TASK-163 livelock detector). Start positions whose centre is closer than r to a non-host line
          (the ball would start inside a line, e.g. on level 24's shelf in front of B) are skipped and
          counted as `skipped`. Exit 1 when any run is embedded or trapped.
      --root DIR runs DIR/index.html (e.g. a pre-fix git worktree); the detectors come from this checkout.
Output: compact JSON {root, rootHead, head, perLevel: {"<level no>": {portals, runs, skipped, portalEntries,
teleports, embedded, trapped, won}}, totals, embeddedCases (<= 50), trappedCases (<= 50), pageErrors}.
portalEntries = runs with >= 1 teleport.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from sim import open_page  # noqa: E402
from embed import install as install_embed  # noqa: E402
from rimtrap import install as install_trap  # noqa: E402

LEVELS = list(range(10, 32))   # levels[10..31] = level 11..32
ANGLES = [-60, -30, 0, 30, 60]
SPEED = 10                     # px/frame (medium)
GAP = 3.0
FRAMES = 200
SPF = 500

INFO_JS = r"""(idxs) => idxs.map(i => {
  thisLevel = i; playtestLevel = null; levelChoosed(i)
  const P = currentPortals() || [], L = curLevel().lines
  return {index: i, r: ball.radius,
          lines: lines.map(l => [l.posX, l.posY, l.posX2, l.posY2, L.indexOf(l)]),
          portals: P.map(p => ({name: p.name, x: p.x, y: p.y, angle: p.angle, h: p.h, line: p.line}))}
})"""

RUN_JS = r"""(cases) => cases.map(c => {
  thisLevel = c.index; playtestLevel = null; levelChoosed(c.index)
  ball.posX = c.x; ball.posY = c.y; ball.speedX = c.vx; ball.speedY = c.vy
  portalReset()
  const P = currentPortals() || [], lv = curLevel(), rd = v => Math.round(v * 100) / 100
  const emb = window.__embed.detector(), trap = window.__rimtrap.detector(P)
  let end = 'frames', f = 0
  for (; f < c.frames; ++f) {
    const n0 = portalState.teleports.length
    let stop = null
    for (let i = 0; i < c.spf; ++i) {
      gamePhysics()
      if (flagCollision(lv.flagX, lv.flagY)) { stop = 'won'; break }
      if (!ball.onMap()) { stop = 'offmap'; break }
    }
    emb.frame(f + 1)
    trap.frame(portalState.teleports.length > n0, f + 1)
    if (stop) { end = stop; ++f; break }
    if (emb.embedded) { end = 'embedded'; ++f; break }
    if (trap.trapped) { end = 'trapped'; ++f; break }
  }
  return {teleports: portalState.teleports.length, end, frames: f, embedded: emb.embedded, embedFrame: emb.embedFrame,
          trapped: trap.trapped, trapFrame: trap.trapFrame || null, ball: [rd(ball.posX), rd(ball.posY)],
          tp: portalState.teleports.slice(0, 3).map(t => [t.from + t.to, rd(t.after[0]), rd(t.after[1])])}
})"""


def seg_dist(p, q, a, b):
    """Distance between segments pq and ab (2D)."""
    def pt_seg(x, y, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / L))
        return math.hypot(x - a[0] - t * dx, y - a[1] - t * dy)

    def cross(o, u, v):
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])
    d1, d2, d3, d4 = cross(a, b, p), cross(a, b, q), cross(p, q, a), cross(p, q, b)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 * d2 < 0 and d3 * d4 < 0:
        return 0.0
    return min(pt_seg(p[0], p[1], a, b), pt_seg(q[0], q[1], a, b), pt_seg(a[0], a[1], p, q), pt_seg(b[0], b[1], p, q))


def opening(P):
    nx, ny = math.cos(P['angle']), math.sin(P['angle'])
    tx, ty = -ny, nx
    return (nx, ny, tx, ty), (P['x'] - P['h'] * tx, P['y'] - P['h'] * ty), (P['x'] + P['h'] * tx, P['y'] + P['h'] * ty)


def sha(d):
    try:
        return subprocess.check_output(['git', '-C', d, 'rev-parse', 'HEAD'], text=True).strip()
    except Exception:
        return None


def level_info(root, idxs):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, root)
        info = page.evaluate(INFO_JS, idxs)
        browser.close()
    return info, errors


def risk(task, out, root):
    info, errors = level_info(root, LEVELS)
    doc = {'root': root, 'rootHead': sha(root), 'threshold': 'r + 2', 'perLevel': {}, 'pageErrors': errors}
    total = 0
    for L in info:
        r = L['r']
        near = []
        for P in L['portals']:
            _, a, b = opening(P)
            for k, l in enumerate(L['lines']):
                if l[4] == P['line']:
                    continue          # the portal's host line
                d = seg_dist((l[0], l[1]), (l[2], l[3]), a, b)
                if d < r + 2:
                    near.append({'portal': P['name'], 'line': k, 'seg': [round(v, 3) for v in l[:4]], 'dist': round(d, 3)})
        doc['perLevel'][str(L['index'] + 1)] = {'portals': len(L['portals']), 'near': near}
        total += len(near)
    doc['totalNear'] = total
    with open(out_path(task, out), 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
    for k, v in doc['perLevel'].items():
        if v['near']:
            print('level', k, json.dumps(v['near'], separators=(',', ':')))
    print('totalNear=%d errors=%d' % (total, len(errors)))
    return 0


def cases_for(info, s_step):
    out = []
    for L in info:
        r = L['r']
        for pi, P in enumerate(L['portals']):
            (nx, ny, tx, ty), _, _ = opening(P)
            h = int(P['h'])
            for s in range(-h, h + 1, s_step):
                cx, cy = P['x'] + s * tx + (r + GAP) * nx, P['y'] + s * ty + (r + GAP) * ny
                inside = any(l[4] != P['line'] and seg_dist((cx, cy), (cx, cy), (l[0], l[1]), (l[2], l[3])) < r
                             for l in L['lines'])
                for a in ANGLES:
                    t = math.radians(a)
                    dx, dy = -math.cos(t) * nx + math.sin(t) * tx, -math.cos(t) * ny + math.sin(t) * ty
                    v = SPEED / SPF
                    out.append({'index': L['index'], 'portal': P['name'], 's': s, 'a': a, 'skip': inside,
                                'x': cx, 'y': cy, 'vx': v * dx, 'vy': v * dy, 'frames': FRAMES, 'spf': SPF})
    return out


def worker(job):
    root, cases = job
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = open_page(p, root)
        page.evaluate("() => { window.requestAnimationFrame = () => 0 }")
        install_embed(page)
        install_trap(page)
        out = []
        for i in range(0, len(cases), 40):
            out += page.evaluate(RUN_JS, cases[i:i + 40])
        browser.close()
    return out, errors


def out_path(task, out):
    """absolute paths as given, relative ones under artifacts/<task>/"""
    if os.path.isabs(out):
        return out
    p = os.path.join(ROOT, 'artifacts', task, out)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def sweep(a):
    t0 = time.time()
    idxs = [int(x) - 1 for x in a.levels.split(',')] if a.levels else LEVELS
    info, errors = level_info(a.root, idxs)
    allc = cases_for(info, a.s_step)
    run = [c for c in allc if not c['skip']]
    J = max(1, min(a.jobs, len(run)))
    with Pool(J) as pool:
        parts = pool.map(worker, [(a.root, run[i::J]) for i in range(J)])
    res = [None] * len(run)
    for i, (rows, e) in enumerate(parts):
        errors += e
        for j, x in enumerate(rows):
            res[i + j * J] = x
    per = {}
    for L in info:
        per[str(L['index'] + 1)] = {'portals': len(L['portals']), 'runs': 0, 'skipped': 0, 'portalEntries': 0,
                                    'teleports': 0, 'embedded': 0, 'trapped': 0, 'won': 0}
    for c in allc:
        if c['skip']:
            per[str(c['index'] + 1)]['skipped'] += 1
    emb, trp = [], []
    for c, r in zip(run, res):
        p = per[str(c['index'] + 1)]
        p['runs'] += 1
        p['portalEntries'] += 1 if r['teleports'] else 0
        p['teleports'] += r['teleports']
        p['won'] += 1 if r['end'] == 'won' else 0
        case = {'level': c['index'] + 1, 'portal': c['portal'], 's': c['s'], 'a': c['a'], 'end': r['end'],
                'frames': r['frames'], 'ball': r['ball'], 'tp': r['tp']}
        if r['embedded']:
            p['embedded'] += 1
            emb.append(dict(case, embedFrame=r['embedFrame']))
        if r['trapped']:
            p['trapped'] += 1
            trp.append(dict(case, trapFrame=r['trapFrame']))
    tot = {k: sum(v[k] for v in per.values()) for k in ('runs', 'skipped', 'portalEntries', 'teleports', 'embedded', 'trapped', 'won')}
    doc = {'root': a.root, 'rootHead': sha(a.root), 'head': sha(ROOT),
           'grid': {'angles': ANGLES, 'speed': SPEED, 'gap': GAP, 'frames': FRAMES, 'spf': SPF, 'sStep': a.s_step},
           'perLevel': per, 'totals': tot, 'embeddedCases': emb[:50], 'trappedCases': trp[:50],
           'pageErrors': errors[:20], 'elapsed_s': round(time.time() - t0, 1)}
    fail = tot['embedded'] > 0 or tot['trapped'] > 0 or bool(errors)
    doc['fail'] = fail
    with open(out_path(a.task, a.out), 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
    for k, v in per.items():
        print('level %s %s' % (k, json.dumps(v, separators=(',', ':'))))
    print('totals %s errors=%d elapsed=%.0fs rootHead=%s' % (json.dumps(tot, separators=(',', ':')), len(errors),
                                                             doc['elapsed_s'], doc['rootHead']))
    print('EXIT %d' % (1 if fail else 0))
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--out', default=None)
    ap.add_argument('--root', default=ROOT)
    ap.add_argument('--risk', action='store_true')
    ap.add_argument('--levels', default='', help='comma separated level numbers (1-based), default 11..32')
    ap.add_argument('--s-step', type=int, default=1)
    ap.add_argument('--jobs', type=int, default=max(1, min(7, (os.cpu_count() or 2) - 1)))
    a = ap.parse_args()
    a.root = os.path.abspath(a.root)
    if a.risk:
        return risk(a.task, a.out or 'risk.json', a.root)
    a.out = a.out or 'sweep.json'
    return sweep(a)


if __name__ == '__main__':
    sys.exit(main())
