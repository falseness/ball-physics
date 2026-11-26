#!/usr/bin/env python3
"""TASK-269: portal fuzz scenes for tests/physics/portal_fast.mjs, from the tests/portal/fuzz.py generators.

  python3 tests/physics/portal_fast_scenes.py --seeds 1,2 --per-mode 100 > scenes.json

For every seed: random.Random(0x9F2690 + seed), then per-mode scenes of each generator in turn (default and
crossing alternate aimed / random balls, as tests/physics/invariants_browser.py --parity-export). Prints compact JSON
{seeds, perMode, scenes: [{id, mode, seed, cfg}]} (cfg = window.__portalTest.setup input).
"""
import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tests', 'portal'))
import fuzz  # noqa: E402

MODES = ('default', 'crossing', 'backside', 'touching')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='1,2')
    ap.add_argument('--per-mode', type=int, default=100)
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(',') if s]
    out = []
    for seed in seeds:
        rng = random.Random(0x9F2690 + seed)
        for mode in MODES:
            for i in range(a.per_mode):
                aimed = i % 2 == 0
                cfg = (fuzz.make_case(rng, aimed) if mode == 'default' else fuzz.make_crossing_case(rng, aimed) if mode == 'crossing'
                       else fuzz.make_backside_case(rng) if mode == 'backside' else fuzz.make_touching_case(rng))
                out.append({'id': '%s_s%d_%d' % (mode, seed, i), 'mode': mode, 'seed': seed, 'cfg': cfg})
    json.dump({'seeds': seeds, 'perMode': a.per_mode, 'scenes': out}, sys.stdout, separators=(',', ':'))


if __name__ == '__main__':
    main()
