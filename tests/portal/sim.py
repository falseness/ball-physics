#!/usr/bin/env python3
"""Portal physics checks (Playwright, index.html via file://).

  python3 tests/portal/sim.py --task TASK-NNN --scenarios S1,S2,S3
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


SCENARIOS = {'S1': s1, 'S2': s2, 'S3': s3}

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
                  {k: v for k, v in chk.items() if k.startswith('ok_') or k in ('teleports', 'speedRelErr', 'posErr', 'velRelErr')})
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
