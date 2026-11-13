#!/usr/bin/env python3
"""Informational frame-time measurement (never a pass/fail gate).

Runs a harness scenario (default 'placed'), then records the interval between
N consecutive requestAnimationFrame callbacks and the time spent in draw()
(wrapped for the measurement only), and writes artifacts/TASK/perf.json.

Usage: python3 tests/visual/perf.py --task TASK-NNN [--scenario placed] [--frames 120] [--dpr 1] [--out perf.json]
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shoot  # noqa: E402

MEASURE_JS = """async n => {
  const orig = window.draw, work = [];
  window.draw = function () { const t = performance.now(); const r = orig.apply(this, arguments); work.push(performance.now() - t); return r; };
  const ts = [];
  await new Promise(r => { const f = t => { ts.push(t); ts.length > n ? r() : requestAnimationFrame(f); }; requestAnimationFrame(f); });
  window.draw = orig;
  const dt = ts.slice(1).map((t, i) => t - ts[i]);
  const st = a => { const s = [...a].sort((x, y) => x - y); return s.length ? {median: +s[s.length >> 1].toFixed(3), max: +s[s.length - 1].toFixed(3), n: s.length} : null; };
  return {frame: st(dt), draw: st(work), physics};
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--scenario', default='placed')
    ap.add_argument('--frames', type=int, default=120)
    ap.add_argument('--dpr', type=float, default=1, help='device_scale_factor (default 1)')
    ap.add_argument('--out', default='perf.json')
    a = ap.parse_args()
    out_dir = os.path.join(shoot.ROOT, 'artifacts', a.task)
    os.makedirs(out_dir, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport=shoot.VIEWPORT, device_scale_factor=a.dpr)
        page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
        page.goto(shoot.URL)
        page.wait_for_load_state('load')
        shoot.frames(page)
        shoot.SCENARIOS[a.scenario](page, {})
        r = page.evaluate(MEASURE_JS, a.frames)
        b.close()
    res = {'scenario': a.scenario, 'frames': a.frames, 'dpr': a.dpr,
           'frameMs': r['frame'], 'drawMs': r['draw'], 'physics': r['physics'],
           'errors': errors, 'informational': True}
    with open(os.path.join(out_dir, a.out), 'w') as f:
        json.dump(res, f, separators=(',', ':'))
    print(json.dumps(res, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
