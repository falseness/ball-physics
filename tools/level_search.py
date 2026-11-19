#!/usr/bin/env python3
"""Reusable level search tool for Ball physics (generalises the TASK-101 / TASK-114 throwaway scripts).

Opens index.html via file:// in headless Chromium (Python Playwright), one page per worker process, stops the
live game loop (requestAnimationFrame) and evaluates candidate player-line sets in-page:

  placement  every line is placed through the game's own handleClick(): a start click and an end click, exactly
             like a real mouse click/tap (dotСorrection snap onto existing line ends, ball.collisionWithDot start
             refusal, addNewLine end rules: snap + segment-ball distance <= ball.radius refusal, linesK < lineK,
             a click on an existing player line selects it instead of starting a line, clicks on the HUD icons
             trigger the icon). Since TASK-105 there is no portal refusal for player lines (they may cross an
             opening). A candidate is valid only if every line was accepted (one more player line per pair of
             clicks). With fewer lines than the level's lineK the run is started like pressing the play icon.
  physics    gameMechanics() frames (cyclesPerTact physics cycles each, as the game loop) until the win
             (levelCompletedWindow), a restart (ball left the map -> restartKeepLines), the ball standing still
             for --still frames (default 60; a resting ball can never win) or --max-frames (default 2000).

Level input: --level INDEX (levels[INDEX], 0-based: --level 16 is level 17), optionally with --level-json FILE,
an editor export ({version 2, ballX, ballY, flagX, flagY, flagRotate, lineK, lines, portals}) injected in-page
as levels[INDEX] (test only, js/levels.js is not touched; INDEX == levels.length appends).

Modes (--lines k = player lines per candidate):
  dense1     one line, both endpoints on a --step px lattice over --bounds (default the whole field 1280x800,
             margin step/2), each unordered endpoint pair once (both orders deduplicated: the end rule is a
             superset of the start rule, so the order does not change validity or the line), then a refinement:
             all single-coordinate +-8/+-4 px variants of the 20 valid candidates with the smallest ball-flag
             distance (--refine 0 disables).
  sample     k lines: --random N uniformly random VALID k-line candidates (endpoints uniform over --bounds,
             length >= --min-len) from --seed (placement is validated first, cheaply, and the first N valid in
             generation order are simulated, so the set does not depend on --workers), plus, with --around FILE,
             every seed solution and its single-coordinate +-step variants.
  local      a given --solution and all its single-coordinate +-delta variants (--delta, default 2 px).
  necessity  a given --solution and each variant with one line removed.
  merge      no simulation: merges the jsonl files given with --inputs (e.g. background shards) into one summary.

--solution: comma separated numbers, 4 per line (x1,y1,x2,y2,...); ';' may separate lines.
--around FILE: json list of solutions (each a list of [x1,y1,x2,y2]) or jsonl rows with a "lines" or "c" key.
--shard i/n keeps candidates i, i+n, ... (run shards in the background, then --mode merge).

Output: --out PATH.json (summary, compact JSON) and PATH.jsonl (one compact row per candidate:
{c: requested lines, valid, lines: placed lines, win: frame or -1, end: win|off|still|max, frames,
 teleports: [from+to, ...], minFlagDist}). Summary: {mode, level, lines, candidates, valid, wins, winLines (<= 50),
 winsWithoutTeleport, elapsed_s, workers, ...}; local/necessity summaries also list every row (results).

Examples:
  python3 tools/level_search.py --level 16 --lines 1 --mode local --solution 320,280,1060,620 --out /tmp/l17.json
  python3 tools/level_search.py --level 16 --lines 1 --mode dense1 --step 80 --out /tmp/dense.json
  python3 tools/level_search.py --level 17 --level-json new.json --lines 2 --mode sample --random 3000 --out s.json
"""
import argparse
import collections
import json
import math
import os
import random
import sys
import time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = 'file://' + os.path.join(ROOT, 'index.html')
FIELD = (1280, 800)

# In-page evaluation of a batch of candidates. args: [idx, cands, maxF, still, simulate]
EVAL_JS = r"""([idx, cands, maxF, still, simulate]) => {
const r2 = x => Math.round(x * 100) / 100
const out = []
for (const c of cands) {
  editorMode = false; playtestLevel = null; drawMenu = false; levelCompletedWindow = false; line = false
  thisLevel = idx; levelChoosed(idx)
  let ok = true
  for (const s of c) {
    const n0 = lines.length, k0 = linesK
    handleClick([s[0], s[1]])                       // start click
    if (!line || linesK !== k0 + 1) { ok = false; break }
    handleClick([s[2], s[3]])                       // end click
    if (line || lines.length !== n0 + 1 || lines[n0].type !== 'player') { ok = false; break }
  }
  if (!ok) { line = false; out.push({c, valid: 0}); continue }
  const placed = lines.filter(l => l.type == 'player').map(l => [r2(l.posX), r2(l.posY), r2(l.posX2), r2(l.posY2)])
  if (!simulate) { out.push({c, valid: 1, lines: placed}); continue }
  if (!physics) { selectionClear(); physics = true; levelStarted = true }   // fewer lines than lineK: the play icon
  const lv = curLevel()
  let win = -1, f = 0, end = 'max', tps = [], fd = 1e9, st = 0, px = ball.posX, py = ball.posY
  for (; f < maxF; ++f) {
    gameMechanics()
    if (portalState.teleports.length > tps.length) tps = portalState.teleports.map(t => t.from + t.to)  // reset by a restart
    if (levelStarted) fd = Math.min(fd, Math.hypot(ball.posX - lv.flagX, ball.posY - lv.flagY))
    if (levelCompletedWindow) { win = f + 1; end = 'win'; ++f; break }
    if (!levelStarted) { end = 'off'; ++f; break }
    if (Math.abs(ball.posX - px) < 0.01 && Math.abs(ball.posY - py) < 0.01) { if (++st >= still) { end = 'still'; ++f; break } } else st = 0
    px = ball.posX; py = ball.posY
  }
  out.push({c, valid: 1, lines: placed, win, end, frames: f, teleports: tps, minFlagDist: Math.round(fd * 10) / 10})
}
editorMode = false; playtestLevel = null; physics = false; levelStarted = false; levelCompletedWindow = false; line = false
levelChoosed(idx)
return out }"""

INJECT_JS = r"""([idx, d]) => {
const L = editorLevelFromData(d)
if (!L) return 'invalid level json'
const lv = {ballX: L.ballX, ballY: L.ballY, flagX: L.flagX, flagY: L.flagY, flagRotate: L.flagRotate, lineK: L.lineK,
            lines: L.lines, portals: L.portals, unlock: 1}
if (idx > levels.length) return 'index beyond levels.length'
levels[idx] = lv
return 'ok' }"""

INFO_JS = r"""(idx) => { const L = levels[idx]; return L ? {nLevels: levels.length, lineK: L.lineK, ballX: L.ballX, ballY: L.ballY,
    flagX: L.flagX, flagY: L.flagY, portals: (L.portals || []).length, cyclesPerTact} : {nLevels: levels.length} }"""


def open_page(pw, args):
    b = pw.chromium.launch()
    pg = b.new_page(viewport={'width': FIELD[0], 'height': FIELD[1]})
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(URL)
    pg.wait_for_load_state('load')
    pg.evaluate("new Promise(r => requestAnimationFrame(() => r()))")
    pg.evaluate("() => { window.requestAnimationFrame = () => 0 }")  # stop the live loop; frames are stepped here
    if args['level_json']:
        res = pg.evaluate(INJECT_JS, [args['level'], args['level_json']])
        if res != 'ok':
            raise SystemExit('level json: ' + res)
    return b, pg, errors


def job(a):
    """Worker: evaluates its slice of candidates in its own browser; returns rows in slice order."""
    wid, cands, args = a
    from playwright.sync_api import sync_playwright
    rows = []
    t0 = time.time()
    with sync_playwright() as pw:
        b, pg, errors = open_page(pw, args)
        B = args['batch']
        for i in range(0, len(cands), B):
            rows += pg.evaluate(EVAL_JS, [args['level'], cands[i:i + B], args['max_frames'], args['still'], args['simulate']])
            if args['progress'] and (i // B) % args['progress'] == 0 and i:
                print('  worker %d: %d/%d (%.0f s)' % (wid, i + B, len(cands), time.time() - t0), file=sys.stderr, flush=True)
        b.close()
    if errors:
        raise RuntimeError('page errors: %s' % errors[:3])
    return rows


def evaluate(cands, args, simulate=True):
    """Runs candidates over args.workers processes (strided slices), returns rows in candidate order."""
    if not cands:
        return []
    W = max(1, min(args['workers'], len(cands)))
    a = dict(args, simulate=simulate)
    slices = [(w, cands[w::W], a) for w in range(W)]
    if W == 1:
        parts = [job(slices[0])]
    else:
        with Pool(W) as pool:
            parts = pool.map(job, slices)
    rows = [None] * len(cands)
    for w, part in enumerate(parts):
        for j, r in enumerate(part):
            rows[w + j * W] = r
    return rows


def level_info(args):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, pg, errors = open_page(pw, args)
        info = pg.evaluate(INFO_JS, args['level'])
        b.close()
    return info


def parse_solution(s):
    nums = [float(x) for x in s.replace(';', ',').split(',') if x.strip()]
    if not nums or len(nums) % 4:
        raise SystemExit('--solution needs 4 numbers per line')
    nums = [int(x) if x == int(x) else x for x in nums]
    return [nums[i:i + 4] for i in range(0, len(nums), 4)]


def single_coord_variants(sol, deltas):
    out = []
    for li in range(len(sol)):
        for ci in range(4):
            for d in deltas:
                v = [list(l) for l in sol]
                v[li][ci] += d
                out.append(v)
    return out


def bounds_of(args):
    if args['bounds']:
        x0, y0, x1, y1 = [float(v) for v in args['bounds'].split(',')]
    else:
        x0, y0, x1, y1 = 0, 0, FIELD[0], FIELD[1]
    return x0, y0, x1, y1


def dense1_cands(args):
    st = args['step']
    x0, y0, x1, y1 = bounds_of(args)
    xs = [x for x in range(int(x0 + st // 2), int(x1), st)]
    ys = [y for y in range(int(y0 + st // 2), int(y1), st)]
    pts = [(x, y) for x in xs for y in ys]
    c = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            (a, b), (p, q) = pts[i], pts[j]
            L = math.hypot(p - a, q - b)
            if L < args['min_len'] or (args['max_len'] and L > args['max_len']):
                continue
            c.append([[a, b, p, q]])
    return c


def random_line(R, args):
    x0, y0, x1, y1 = bounds_of(args)
    while True:
        l = [round(R.uniform(x0, x1)), round(R.uniform(y0, y1)), round(R.uniform(x0, x1)), round(R.uniform(y0, y1))]
        L = math.hypot(l[2] - l[0], l[3] - l[1])
        if L >= args['min_len'] and (not args['max_len'] or L <= args['max_len']):
            return l


def load_around(path):
    txt = open(path).read().strip()
    sols = []
    try:
        d = json.loads(txt)
        if isinstance(d, dict):
            d = d.get('winLines') or d.get('solutions') or []
        for s in d:
            if isinstance(s, dict):
                s = s.get('lines') or s.get('c')
            sols.append([list(l) for l in s])
    except json.JSONDecodeError:
        for ln in txt.splitlines():
            r = json.loads(ln)
            sols.append([list(l) for l in (r.get('lines') or r.get('c'))])
    return sols


def key(c):
    return json.dumps(c, separators=(',', ':'))


def summarize(rows, args, extra):
    valid = [r for r in rows if r.get('valid')]
    sim = [r for r in valid if 'win' in r]
    wins = sorted([r for r in sim if r['win'] > 0], key=lambda r: r['win'])
    ends = collections.Counter(r['end'] for r in sim)
    routes = collections.Counter(','.join(r['teleports']) or '-' for r in sim)
    nonwin = sorted([r for r in sim if r['win'] <= 0], key=lambda r: r['minFlagDist'])
    s = {'mode': args['mode'], 'level': args['level'], 'levelJson': args.get('level_json_path'), 'lines': args['lines'],
         'maxFrames': args['max_frames'], 'candidates': len(rows), 'valid': len(valid), 'simulated': len(sim),
         'wins': len(wins), 'winRate': round(len(wins) / len(sim), 5) if sim else None,
         'winsWithoutTeleport': sum(1 for r in wins if not r['teleports']),
         'winLines': [{'lines': r['lines'], 'win': r['win'], 'teleports': ','.join(r['teleports']) or '-'} for r in wins[:50]],
         'ends': dict(ends), 'routes': dict(routes.most_common(20)),
         'bestNonWin': nonwin and {'lines': nonwin[0]['lines'], 'minFlagDist': nonwin[0]['minFlagDist'],
                                   'teleports': ','.join(nonwin[0]['teleports']) or '-', 'end': nonwin[0]['end']} or None}
    s.update(extra)
    return s


def write_out(path, rows, summ):
    if not path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)) or '.', exist_ok=True)
    jl = path[:-5] + '.jsonl' if path.endswith('.json') else path + '.jsonl'
    if rows is not None:
        with open(jl, 'w') as f:
            for r in rows:
                f.write(json.dumps(r, separators=(',', ':')) + '\n')
    with open(path, 'w') as f:
        json.dump(summ, f, separators=(',', ':'))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--level', type=int, required=False, help='levels[] index (0-based)')
    ap.add_argument('--level-json', help='editor export injected as levels[INDEX] (test only)')
    ap.add_argument('--lines', type=int, default=1, help='player lines per candidate (k)')
    ap.add_argument('--mode', required=True, choices=['dense1', 'sample', 'local', 'necessity', 'merge'])
    ap.add_argument('--workers', type=int, default=7)
    ap.add_argument('--max-frames', type=int, default=2000)
    ap.add_argument('--still', type=int, default=60, help='stop after the ball stood still this many frames')
    ap.add_argument('--step', type=int, default=40, help='dense1 lattice step / sample --around shift')
    ap.add_argument('--bounds', help='x0,y0,x1,y1 area for lattice / random endpoints (default the whole field)')
    ap.add_argument('--min-len', type=float, default=20, help='minimum requested line length')
    ap.add_argument('--max-len', type=float, default=0, help='maximum requested line length (0 = none)')
    ap.add_argument('--refine', type=int, default=20, help='dense1: refine around this many closest candidates')
    ap.add_argument('--random', type=int, default=0, help='sample: number of valid random candidates')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--around', help='sample: seed solutions file')
    ap.add_argument('--solution', help='local/necessity: x1,y1,x2,y2[,...]')
    ap.add_argument('--delta', type=float, default=2, help='local: shift in px')
    ap.add_argument('--shard', help='i/n: keep candidates i, i+n, ...')
    ap.add_argument('--inputs', nargs='*', help='merge: jsonl files')
    ap.add_argument('--batch', type=int, default=20, help='candidates per page.evaluate call')
    ap.add_argument('--progress', type=int, default=0, help='print worker progress every N batches (stderr)')
    ap.add_argument('--out', help='summary PATH.json (+ PATH.jsonl rows)')
    ns = ap.parse_args()
    args = vars(ns)
    args['level_json_path'] = ns.level_json
    t0 = time.time()

    if ns.mode == 'merge':
        rows = []
        for p in ns.inputs or []:
            with open(p) as f:
                rows += [json.loads(l) for l in f if l.strip()]
        summ = summarize(rows, args, {'inputs': ns.inputs, 'elapsed_s': round(time.time() - t0, 1), 'workers': 0})
        write_out(ns.out, None, summ)
        print(json.dumps({k: v for k, v in summ.items() if k != 'winLines'}, separators=(',', ':')))
        return 0

    if ns.level is None:
        ap.error('--level is required')
    args['level_json'] = json.load(open(ns.level_json)) if ns.level_json else None
    info = level_info(args)
    if 'lineK' not in info:
        raise SystemExit('no level at index %d (levels.length %d)' % (ns.level, info['nLevels']))
    k = ns.lines
    extra = {'levelInfo': info}

    def shard(c):
        if not ns.shard:
            return c
        i, n = [int(v) for v in ns.shard.split('/')]
        return c[i::n]

    if ns.mode == 'dense1':
        if k != 1:
            ap.error('dense1 is a one-line mode (--lines 1)')
        cands = shard(dense1_cands(args))
        rows = evaluate(cands, args)
        extra['lattice'] = {'step': ns.step, 'bounds': bounds_of(args), 'candidates': len(cands)}
        if ns.refine:
            seen = {key(r['c']) for r in rows}
            best = sorted([r for r in rows if r.get('valid')], key=lambda r: r['minFlagDist'])[:ns.refine]
            ref = []
            for r in best:
                for v in single_coord_variants(r['c'], [-8, -4, 4, 8]):
                    if key(v) not in seen:
                        seen.add(key(v))
                        ref.append(v)
            rrows = evaluate(ref, args)
            for r in rrows:
                r['refine'] = 1
            rows += rrows
            extra['refine'] = {'around': len(best), 'candidates': len(ref), 'valid': sum(1 for r in rrows if r.get('valid')),
                               'wins': sum(1 for r in rrows if r.get('win', -1) > 0)}
    elif ns.mode == 'sample':
        cands = []
        if ns.around:
            for sol in load_around(ns.around):
                if len(sol) != k:
                    continue
                cands.append(sol)
                cands += single_coord_variants(sol, [-ns.step, ns.step])
        if ns.random:
            R = random.Random(ns.seed)
            chosen, generated, rounds = [], 0, 0
            while len(chosen) < ns.random:
                need = ns.random - len(chosen)
                gen = [[random_line(R, args) for _ in range(k)] for _ in range(int(need * 1.3) + 20)]
                generated += len(gen)
                rounds += 1
                vrows = evaluate(gen, args, simulate=False)
                chosen += [g for g, r in zip(gen, vrows) if r['valid']]
                if rounds > 50:
                    raise SystemExit('could not find %d valid random candidates' % ns.random)
            chosen = chosen[:ns.random]
            extra['random'] = {'requested': ns.random, 'generated': generated, 'seed': ns.seed,
                               'validPlacementRate': round(len(chosen) / generated, 4)}
            cands += chosen
        cands = shard(cands)
        rows = evaluate(cands, args)
    elif ns.mode == 'local':
        if not ns.solution:
            ap.error('local needs --solution')
        sol = parse_solution(ns.solution)
        d = ns.delta if ns.delta != int(ns.delta) else int(ns.delta)
        cands = [sol] + single_coord_variants(sol, [-d, d])
        rows = evaluate(cands, args)
        rows[0]['centre'] = 1
        var = rows[1:]
        extra.update({'solution': sol, 'delta': d, 'centre': {k2: rows[0].get(k2) for k2 in ('valid', 'win', 'end', 'teleports', 'lines')},
                      'variants': len(var), 'variantsValid': sum(1 for r in var if r.get('valid')),
                      'variantsWin': sum(1 for r in var if r.get('win', -1) > 0),
                      'results': [{'c': r['c'], 'valid': r['valid'], 'win': r.get('win'), 'end': r.get('end'),
                                   'teleports': ','.join(r.get('teleports', [])) or '-', 'minFlagDist': r.get('minFlagDist')} for r in rows]})
    elif ns.mode == 'necessity':
        if not ns.solution:
            ap.error('necessity needs --solution')
        sol = parse_solution(ns.solution)
        cands = [sol] + [sol[:i] + sol[i + 1:] for i in range(len(sol))]
        rows = evaluate(cands, args)
        rows[0]['full'] = 1
        for i, r in enumerate(rows[1:]):
            r['dropped'] = i
        extra.update({'solution': sol, 'full': {k2: rows[0].get(k2) for k2 in ('valid', 'win', 'end', 'teleports')},
                      'dropOne': [{'dropped': i, 'valid': r['valid'], 'win': r.get('win'), 'end': r.get('end'),
                                   'teleports': ','.join(r.get('teleports', [])) or '-', 'minFlagDist': r.get('minFlagDist')}
                                  for i, r in enumerate(rows[1:])],
                      'allDropsLose': all(r.get('valid') and r.get('win', -1) <= 0 for r in rows[1:])})
    extra.update({'elapsed_s': round(time.time() - t0, 1), 'workers': ns.workers, 'shard': ns.shard})
    summ = summarize(rows, args, extra)
    summ['validPerSecond'] = round(summ['simulated'] / max(summ['elapsed_s'], 1e-9), 2)
    write_out(ns.out, rows, summ)
    show = {k2: v for k2, v in summ.items() if k2 not in ('winLines', 'results', 'routes')}
    print(json.dumps(show, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
