#!/usr/bin/env python3
"""Frame-stability check: runs a harness scenario (default 'placed'), then takes two
canvas captures DELAY ms apart and counts differing pixels inside the union bounding
box of all lines (padded by --pad px for glow/hatching).

Usage: python3 tests/visual/stability.py --task TASK-NNN [--scenario placed] [--delay 300] [--pad 0]
                                          [--dpr 1] [--viewport 1280x800] [--out stability.json]
Writes artifacts/TASK-NNN/<out> {scenario, physics, delayMs, k, box:[x0,y0,x1,y1], boxPixels, diffPixels}.
The box is computed in logical game coordinates and scaled by k = canvas.width / GAME_W
to backing-store pixels (the canvas backing store follows CSS size x devicePixelRatio).
Exit 0 only if diffPixels == 0 and no console/page errors.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shoot  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

CAPTURE_JS = """async ([delay, pad]) => {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const l of lines) {
    x0 = Math.min(x0, l.posX, l.posX2); y0 = Math.min(y0, l.posY, l.posY2)
    x1 = Math.max(x1, l.posX, l.posX2); y1 = Math.max(y1, l.posY, l.posY2)
  }
  const k = canvas.width / GAME_W
  x0 = Math.max(0, Math.floor((x0 - pad) * k)); y0 = Math.max(0, Math.floor((y0 - pad) * k))
  x1 = Math.min(canvas.width, Math.ceil((x1 + pad) * k)); y1 = Math.min(canvas.height, Math.ceil((y1 + pad) * k))
  const grab = () => new Promise(r => requestAnimationFrame(() => r(ctx.getImageData(x0, y0, x1 - x0, y1 - y0).data)))
  const a = await grab()
  await new Promise(r => setTimeout(r, delay))
  const b = await grab()
  let diff = 0
  for (let i = 0; i < a.length; i += 4)
    if (a[i] != b[i] || a[i + 1] != b[i + 1] || a[i + 2] != b[i + 2] || a[i + 3] != b[i + 3]) diff++
  return {physics, k, canvas: [canvas.width, canvas.height], box: [x0, y0, x1, y1], boxPixels: a.length / 4, diffPixels: diff}
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--scenario', default='placed')
    ap.add_argument('--delay', type=int, default=300)
    ap.add_argument('--pad', type=int, default=0)
    ap.add_argument('--dpr', type=float, default=1, help='device_scale_factor (default 1)')
    ap.add_argument('--viewport', default='%dx%d' % (shoot.VIEWPORT['width'], shoot.VIEWPORT['height']))
    ap.add_argument('--out', default='stability.json')
    args = ap.parse_args()
    out_dir = os.path.join(shoot.ROOT, 'artifacts', args.task)
    os.makedirs(out_dir, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        vw, vh = (int(v) for v in args.viewport.lower().split('x'))
        page = browser.new_page(viewport={'width': vw, 'height': vh}, device_scale_factor=args.dpr)
        page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
        page.goto(shoot.URL)
        page.wait_for_load_state('load')
        shoot.frames(page)
        shoot.SCENARIOS[args.scenario](page, {})
        res = page.evaluate(CAPTURE_JS, [args.delay, args.pad])
        browser.close()
    out = {'scenario': args.scenario, 'viewport': args.viewport, 'dpr': args.dpr, 'delayMs': args.delay,
           'pad': args.pad, **res, 'errors': errors}
    with open(os.path.join(out_dir, args.out), 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    print(json.dumps(out, separators=(',', ':')))
    ok = res['diffPixels'] == 0 and not res['physics'] and not errors
    print('STABLE' if ok else 'UNSTABLE')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
