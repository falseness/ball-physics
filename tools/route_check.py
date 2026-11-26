#!/usr/bin/env python3
"""Route check (TASK-250): replays a level with given player lines headless and tests a per-level route predicate.

Same harness as tools/level_search.py (open_page: index.html via file://, live loop stopped, relay hosts blocked,
lines placed through the game's own handleClick, gameMechanics() stepped frame by frame). Unlike level_search,
--level is the level's srcId (1-based definition number; levelBySrc maps it to the play order).

Trace, one entry per physics frame f (1-based, after gameMechanics()):
  pos      ball centre [x, y]
  speed    |v| in px per frame (|ball.speed| per physics step * cyclesPerTact, after the frame)
  contacts lines whose segment is within radius + CONTACT_TOL px of the ball centre: [lineIndex, kind, angleDeg]
           kind 'player' or 'level'; angleDeg = the segment's direction angle folded to (-90, 90] (0 = horizontal)
  tp       teleports that happened in this frame: {from, to, s (entry offset along A's opening), kind,
           exitS (offset along the exit opening, mirrored: -s, clamped for a 'touch'), before, after}
End: win (levelCompletedWindow), off (ball left the map), still (60 frames at rest), max (--max-frames).

Predicates (PREDICATES below, chosen by srcId; documented in artifacts/TASK-250/predicate.md):
  24 'speed panel'  the win must use a horizontal speed panel: a player line with |angle| <= 15 deg along which the
     ball rolls/slides (a contact run on that line: consecutive contact frames, gaps <= 2 frames merged, of at least
     30 frames or 60 px of travel) and whose run raises the ball's speed (speed at the run's last contact frame minus
     speed at its first >= 2 px/frame), ending before the decisive entry into A (the last A teleport before the win).
  32 'round trip' (TASK-252, artifacts/TASK-252/predicate.md) the designed route of TASK-159, from the teleport log
     alone: the last teleport before the win is B -> A entering B's UPPER half (s < 0) and leaving A on the flag-shaft
     side (exitS > 0, right of the wall x 560), and the teleport right before it is A -> B entering A's LEFT half
     (s < 0, the start side) and leaving B through its LOWER half (exitS > 0). s / exitS are offsets along each
     portal's own tangent t: A t = +x (s < 0 left of the wall), B t = +y (s < 0 above B's centre y 650).

Output (stdout, and --out FILE): compact JSON {win, frame, proper, reasons, end, level, lines, teleports, runs}.
  win: bool, frame: win frame or -1, proper: predicate result (false when not won), reasons: list of strings.
--trace FILE writes the full per-frame trace (compact JSON). --screenshot FILE.png draws the level after the run
with the ball's whole path (cyan polyline, teleports dashed) and the player lines.

Examples:
  python3 tools/route_check.py --level 24 --lines '170,476,620,513;790,610,730,714;1000,140,1024,278'
  python3 tools/route_check.py --level 24 --lines-file wins.jsonl --out res.jsonl   (batch: one result per row)
"""
import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from level_search import open_page, parse_solution  # noqa: E402

CONTACT_TOL = 1.0   # px beyond the radius: a resting/rolling ball sits at exactly radius (CONTACT_SLOP 1e-9)

TRACE_JS = r"""([idx, cands, maxF, still, tol]) => {
const r2 = x => Math.round(x * 100) / 100
const fresh = i => typeof levelReset === 'function' ? levelReset(i) : levelChoosed(i)
const segDist = (l, x, y) => {
  const ax = l.posX, ay = l.posY, dx = l.posX2 - ax, dy = l.posY2 - ay, L2 = dx * dx + dy * dy
  let t = L2 ? ((x - ax) * dx + (y - ay) * dy) / L2 : 0
  t = Math.max(0, Math.min(1, t))
  return Math.hypot(x - ax - t * dx, y - ay - t * dy) }
const ang = l => { let a = Math.atan2(l.posY2 - l.posY, l.posX2 - l.posX) * 180 / Math.PI
  if (a > 90) a -= 180; if (a <= -90) a += 180; return Math.round(a * 100) / 100 }
const res = []
for (const c of cands) {
  editorMode = false; playtestLevel = null; drawMenu = false; levelCompletedWindow = false; line = false
  thisLevel = idx; fresh(idx)
  let ok = true
  for (const s of c) {
    const n0 = lines.length, k0 = linesK
    handleClick([s[0], s[1]])
    if (!line || linesK !== k0 + 1) { ok = false; break }
    handleClick([s[2], s[3]])
    if (line || lines.length !== n0 + 1 || lines[n0].type !== 'player') { ok = false; break }
  }
  if (!ok) { line = false; res.push({c, valid: 0}); continue }
  const placed = lines.filter(l => l.type == 'player').map(l => [r2(l.posX), r2(l.posY), r2(l.posX2), r2(l.posY2)])
  if (!physics) { selectionClear(); physics = true; levelStarted = true }
  const R = ball.radius, angs = lines.map(ang)
  const fr = []
  let win = -1, f = 0, end = 'max', st = 0, px = ball.posX, py = ball.posY, nt = portalState.teleports.length
  for (; f < maxF; ++f) {
    gameMechanics()
    const e = {pos: [r2(ball.posX), r2(ball.posY)], speed: Math.round(Math.hypot(ball.speedX, ball.speedY) * cyclesPerTact * 1000) / 1000, contacts: []}
    for (let i = 0; i < lines.length; ++i)
      if (segDist(lines[i], ball.posX, ball.posY) <= R + tol) e.contacts.push([i, lines[i].type == 'player' ? 'player' : 'level', angs[i]])
    const T = portalState.teleports
    if (T.length > nt) {
      e.tp = T.slice(nt).map(t => { const P = (currentPortals() || []).find(p => p.name === t.to)
        const exitS = t.kind === 'touch' && P ? Math.max(-P.h, Math.min(P.h, t.s)) : t.s
        return {from: t.from, to: t.to, s: r2(t.s), exitS: r2(-exitS), kind: t.kind, before: t.before.map(r2), after: (t.after || []).map(r2)} })
    }
    nt = T.length
    fr.push(e)
    if (levelCompletedWindow) { win = f + 1; end = 'win'; ++f; break }
    if (!levelStarted) { end = 'off'; ++f; break }
    if (Math.abs(ball.posX - px) < 0.01 && Math.abs(ball.posY - py) < 0.01) { if (++st >= still) { end = 'still'; ++f; break } } else st = 0
    px = ball.posX; py = ball.posY
  }
  res.push({c, valid: 1, lines: placed, win, end, frames: f, radius: R, trace: fr})
}
editorMode = false; playtestLevel = null; physics = false; levelStarted = false; levelCompletedWindow = false; line = false
return res }"""

# draws the level (game draw() after a reset with the lines placed) and the ball's whole path over it
SHOT_JS = r"""([idx, c, path, tps]) => {
levelReset(idx)
for (const s of c) { handleClick([s[0], s[1]]); handleClick([s[2], s[3]]) }
selectionClear(); levelCompletedWindow = false; physics = false; levelStarted = false
draw()
ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); applyViewTransform()
ctx.strokeStyle = 'rgba(80,230,255,0.95)'; ctx.lineWidth = 2.5; ctx.beginPath()
let pen = false
for (const p of path) { if (p === null) { pen = false; continue }
  if (!pen) { ctx.moveTo(p[0], p[1]); pen = true } else ctx.lineTo(p[0], p[1]) }
ctx.stroke()
ctx.setLineDash([6, 6]); ctx.strokeStyle = 'rgba(255,120,200,0.9)'; ctx.lineWidth = 1.5
for (const t of tps) { ctx.beginPath(); ctx.moveTo(t[0], t[1]); ctx.lineTo(t[2], t[3]); ctx.stroke() }
ctx.restore(); return true }"""


def contact_runs(trace, gap=2):
    """Contact runs per player line: consecutive contact frames (gaps <= gap frames merged).
    Returns [{line, angle, f0, f1, frames, travel, v0, v1, gain}] (f0/f1 1-based frames of first/last contact)."""
    per = {}
    for f, e in enumerate(trace, 1):
        for i, kind, a in e['contacts']:
            if kind == 'player':
                per.setdefault(i, (a, []))[1].append(f)
    runs = []
    for i, (a, fs) in per.items():
        start = prev = fs[0]
        for f in fs[1:] + [None]:
            if f is not None and f - prev <= gap + 1:
                prev = f
                continue
            seg = trace[start - 1:prev]
            travel = sum(math.dist(seg[j]['pos'], seg[j + 1]['pos']) for j in range(len(seg) - 1)
                         if not seg[j + 1].get('tp'))
            v0, v1 = trace[start - 1]['speed'], trace[prev - 1]['speed']
            runs.append({'line': i, 'angle': a, 'f0': start, 'f1': prev, 'frames': prev - start + 1,
                         'travel': round(travel, 1), 'v0': v0, 'v1': v1, 'gain': round(v1 - v0, 3)})
            if f is not None:
                start = prev = f
    return sorted(runs, key=lambda r: r['f0'])


def teleports(trace):
    out = []
    for f, e in enumerate(trace, 1):
        for t in e.get('tp', []):
            out.append(dict(t, frame=f))
    return out


# srcId 24 thresholds (artifacts/TASK-250/predicate.md)
P24 = {'maxAngle': 15.0, 'minFrames': 30, 'minTravel': 60.0, 'minGain': 2.0, 'gap': 2}


def pred24(row):
    reasons = []
    trace = row['trace']
    if row['win'] <= 0:
        return False, ['not won (end %s)' % row['end']], []
    tps = teleports(trace)
    a_in = [t for t in tps if t['from'] == 'A' and t['frame'] <= row['win']]
    if not a_in:
        return False, ['no teleport from A before the win'], []
    dec = a_in[-1]
    reasons.append('decisive A entry: frame %d s %.1f -> %s exitS %.1f' % (dec['frame'], dec['s'], dec['to'], dec['exitS']))
    runs = contact_runs(trace, P24['gap'])
    panels = []
    for r in runs:
        flat = abs(r['angle']) <= P24['maxAngle']
        long_ = r['frames'] >= P24['minFrames'] or r['travel'] >= P24['minTravel']
        before = r['f1'] < dec['frame']
        gain = r['gain'] >= P24['minGain']
        r['panel'] = flat and long_ and before and gain
        if flat and long_ and before:
            panels.append(r)
        if r['panel']:
            reasons.append('speed panel: line %d angle %.1f frames %d-%d (%d, travel %.0f px) speed %.2f -> %.2f'
                           % (r['line'], r['angle'], r['f0'], r['f1'], r['frames'], r['travel'], r['v0'], r['v1']))
    ok = any(r['panel'] for r in runs)
    if not ok:
        if panels:
            reasons.append('flat long run(s) before A without speed gain >= %.1f: %s'
                           % (P24['minGain'], ['line %d gain %.2f' % (r['line'], r['gain']) for r in panels]))
        else:
            reasons.append('no player line with |angle| <= %g carries the ball >= %d frames or %g px before the decisive A entry'
                           % (P24['maxAngle'], P24['minFrames'], P24['minTravel']))
    return ok, reasons, runs


def pred32(row):
    """srcId 32 'round trip' (artifacts/TASK-252/predicate.md): A-left -> B-lower, then B-upper -> A-shaft, then win."""
    if row['win'] <= 0:
        return False, ['not won (end %s)' % row['end']], []
    tps = [t for t in teleports(row['trace']) if t['frame'] <= row['win']]
    seq = ','.join('%s%s' % (t['from'], t['to']) for t in tps)
    reasons = ['teleports before the win: %d [%s]' % (len(tps), seq)]
    if not tps:
        return False, reasons + ['no teleport before the win'], []
    last = tps[-1]
    ok2 = last['from'] == 'B' and last['to'] == 'A' and last['s'] < 0 and last['exitS'] > 0
    reasons.append('last teleport (frame %d) %s->%s s %.1f exitS %.1f: %s' % (
        last['frame'], last['from'], last['to'], last['s'], last['exitS'],
        'B upper -> A shaft side' if ok2 else 'NOT B upper -> A shaft side'))
    if len(tps) < 2:
        return False, reasons + ['no A -> B teleport before the B -> A return (ball reached B without going through A)'], []
    prev = tps[-2]
    ok1 = prev['from'] == 'A' and prev['to'] == 'B' and prev['s'] < 0 and prev['exitS'] > 0
    reasons.append('teleport before it (frame %d) %s->%s s %.1f exitS %.1f: %s' % (
        prev['frame'], prev['from'], prev['to'], prev['s'], prev['exitS'],
        'A left -> B lower' if ok1 else 'NOT A left -> B lower'))
    return ok1 and ok2, reasons, []


PREDICATES = {24: pred24, 32: pred32}


def check(rows, src):
    out = []
    pred = PREDICATES.get(src)
    for row in rows:
        if not row.get('valid'):
            out.append({'c': row['c'], 'valid': 0, 'win': False, 'frame': -1, 'proper': False, 'reasons': ['invalid placement']})
            continue
        if pred is None:
            ok, reasons, runs = False, ['no route predicate for srcId %d' % src], []
        else:
            ok, reasons, runs = pred(row)
        out.append({'level': src, 'lines': row['lines'], 'win': row['win'] > 0, 'frame': row['win'], 'end': row['end'],
                    'proper': bool(ok and row['win'] > 0), 'reasons': reasons,
                    'teleports': [{k: t[k] for k in ('frame', 'from', 'to', 's', 'exitS', 'kind')} for t in teleports(row['trace'])],
                    'runs': runs})
    return out


def screenshot(pg, idx, row, path):
    if os.path.exists(path):
        raise SystemExit('refusing to overwrite %s (save as -v2, -v3 ...)' % path)
    pts, tps = [], []
    for e in row['trace']:
        for t in e.get('tp', []):
            tps.append(t['before'][:2] + t['after'][:2])
            pts.append(None)
        pts.append(e['pos'])
    pg.evaluate(SHOT_JS, [idx, row['c'], pts, tps])
    pg.screenshot(path=path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--level', type=int, required=True, help='srcId (1-based definition number)')
    ap.add_argument('--lines', help="x1,y1,x2,y2[;x1,y1,x2,y2 ...]")
    ap.add_argument('--lines-file', help='json list / jsonl rows with "lines" or "c" (batch mode)')
    ap.add_argument('--max-frames', type=int, default=2000)
    ap.add_argument('--still', type=int, default=60)
    ap.add_argument('--out', help='write the result JSON (batch: jsonl)')
    ap.add_argument('--trace', help='write the full per-frame trace (single --lines only)')
    ap.add_argument('--screenshot', help='PNG of the level with the ball path (single --lines only; never overwrites)')
    ns = ap.parse_args()
    if not ns.lines and not ns.lines_file:
        ap.error('--lines or --lines-file required')
    if ns.lines:
        cands = [parse_solution(ns.lines)]
    else:
        from level_search import load_around
        cands = load_around(ns.lines_file)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, pg, errors, idx = open_page(pw, {'level': ns.level - 1, 'level_json': None})
        rows = []
        for i in range(0, len(cands), 10):
            rows += pg.evaluate(TRACE_JS, [idx, cands[i:i + 10], ns.max_frames, ns.still, CONTACT_TOL])
        if ns.screenshot and rows[0].get('valid'):
            screenshot(pg, idx, rows[0], ns.screenshot)
        b.close()
    if errors:
        raise SystemExit('page errors: %s' % errors[:3])
    res = check(rows, ns.level)
    if ns.trace and rows:
        with open(ns.trace, 'w') as f:
            json.dump(rows[0], f, separators=(',', ':'))
    if ns.lines:
        txt = json.dumps(res[0], separators=(',', ':'))
    else:
        txt = '\n'.join(json.dumps(r, separators=(',', ':')) for r in res)
    if ns.out:
        with open(ns.out, 'w') as f:
            f.write(txt + '\n')
    print(txt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
