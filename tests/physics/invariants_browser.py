#!/usr/bin/env python3
"""Browser mode of the invariant checker (TASK-198, TASK-201): ball runs inside the game, every step checked.

  python3 tests/physics/invariants_browser.py [--levels 12,13,...] [--frames N]
  python3 tests/physics/invariants_browser.py --portal-fuzz SEED [--cases N] [--frames F]

Loads index.html (file://, Playwright chromium) and injects tests/physics/invariants_core.js. The shared run
loop (LOOP_JS, window.__invRun) steps the game's own gamePhysics() parts (ball.physics(), ball.move(),
portalStep()) exactly as gameMechanics() does, every step through the checker, until the flag is reached
(levels), the ball leaves the map (the game restarts the level there) or the frame cap (500 steps a frame).
Levels: for every level with a shoot levelNN scenario (tests/visual/shoot.py LEVELnn_LINE / LEVELnn_LINES,
srcId nn) the level is reset (levelReset), the solution lines added as player lines, LEVELnn_MAX_FRAMES frames.
Portal fuzz (TASK-201): N scenes (default 200) from the tests/portal/fuzz.py generators in turn (default,
--crossing, --backside, --touching; random.Random(0x9F0000 + SEED)), set up with window.__portalTest.setup,
F frames (default 300).
Contacts: every line at the step's start position (the contact model resolves there), plus the normals that
portalStep() used after the move in that step: every rim within the radius of the final centre when a rim
bounce happened (portalState.rimHits grew) and the portals' front normals when a teleport was refused
(blockedExits grew). I1 depth uses the lines with each wall portal's opening (c +- h t) cut out of its host
line. A step counts as a teleport (T rule: speed preserved) when portalState.teleports grows.
Prints one compact JSON object on stdout ({levels: [...]} or {seed, scenes: [...]}).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tests', 'visual'))
import shoot  # noqa: E402  (LEVELnn_LINE(S) / LEVELnn_MAX_FRAMES only)

# Shared in-page run loop (levels and portal fuzz scenes): checker geometry from the current lines and portals,
# then the game's own gamePhysics() parts, every step through the checker, until the flag (levels only), the
# ball leaving the map, or maxSteps.
LOOP_JS = r"""window.__invRun = (label, maxSteps, flag) => {
    const P = currentPortals() || []
    const all = lines.map(l => [l.posX, l.posY, l.posX2, l.posY2])
    // solid geometry for I1: host lines minus their openings
    const cut = {}
    P.forEach(p => { if (typeof p.line == 'number') (cut[p.line] = cut[p.line] || []).push(p) })
    const solid = [], solidOwner = []
    const push = (s, k) => { solid.push(s); solidOwner.push(k) }
    all.forEach((s, k) => {
        if (!cut[k]) { push(s, k); return }
        const dx = s[2] - s[0], dy = s[3] - s[1], L = Math.hypot(dx, dy)
        const iv = cut[k].map(p => { const u = ((p.x - s[0]) * dx + (p.y - s[1]) * dy) / (L * L), w = p.h / L; return [u - w, u + w] })
            .sort((a, b) => a[0] - b[0])
        let t = 0
        iv.forEach(([a, b]) => { if (a > t) push([s[0] + t * dx, s[1] + t * dy, s[0] + a * dx, s[1] + a * dy], k); t = Math.max(t, b) })
        if (t < 1) push([s[0] + t * dx, s[1] + t * dy, s[2], s[3]], k)
    })
    const points = []
    P.forEach(p => portalRims(p).forEach(q => points.push(q)))
    // TASK-201: the portal capture zone (TASK-074 / TASK-173 rule, from the portal geometry): a ball in front of wall
    // portal P (d > 0) moving toward it (v.n < 0) whose closest point q on P's host line lies within h + r of P's
    // centre along t (q a host line end: the centre within h + r / 2) is being captured, unless the touch exit is
    // refused (portalTouchExitBlocked, a line at the exit spot). That host line is not a contact for it (zone).
    const R = ball.radius, hostOf = P.map(p => typeof p.line == 'number' ? p.line : -1)
    // I1 (post-step state, post = true) also skips host line k for a ball in front of a portal on it moving away from
    // that front, unless its closest solid point is a real end of the line: the portal's exit placement (local
    // (-clamp(s), d) with the entry depth d < r) may leave the ball overlapping the host line next to the opening,
    // and the game lets it move out freely (only the host line's own ends stay solid for it, js/ball.js contacts()).
    const isEnd = (c, s) => (c[0] === s[0] && c[1] === s[1]) || (c[0] === s[2] && c[1] === s[3])
    const zone = (x, y, vx, vy, post) => {
        let out = null
        for (let i = 0; i < P.length; ++i) {
            const k = hostOf[i]
            if (k < 0 || (out && out.indexOf(k) >= 0)) continue
            const p = P[i], f = portalFrame(p), d = (x - p.x) * f.nx + (y - p.y) * f.ny, vn = vx * f.nx + vy * f.ny
            if (!(d > 0)) continue
            if (post && vn > 0) {
                let best = null
                solid.forEach((s, j) => { if (solidOwner[j] === k) { const c = InvariantsCore.closest(x, y, s); if (!best || c[2] < best[2]) best = c } })
                if (best && !isEnd(best, all[k])) (out = out || []).push(k)
                continue
            }
            if (!(vn < 0)) continue
            const c = InvariantsCore.closest(x, y, all[k])
            if (!(c[2] < R + 1e-9)) continue
            const end = isEnd(c, all[k])
            if (Math.abs((c[0] - p.x) * f.tx + (c[1] - p.y) * f.ty) > p.h + R) continue
            if (end && Math.abs((x - p.x) * f.tx + (y - p.y) * f.ty) > p.h + 0.5 * R) continue
            if (portalTouchExitBlocked(p, { posX: x, posY: y, speedX: vx, speedY: vy, radius: R }, f)) continue
            (out = out || []).push(k)
        }
        return out
    }
    const chk = InvariantsCore.makeChecker({ g: gravitationalAcceleration, r: R, segs: all, points, solid, solidOwner, zone, label })
    const S = portalState
    // normals of this step's portalStep bounces (only on steps where S.rimHits / S.blockedExits grew),
    // from the geometry, not from portal.js' own records: a rim bounce about (centre - rim) / |..| for every rim
    // within ball.radius of the final centre (rims do not move the ball); a refused teleport (blocked exit) about
    // a portal's front normal (the entry plane; the entry is not known, both portals are candidates).
    const postNormals = (rim, blocked) => {
        const out = []
        if (rim)
            points.forEach((q, k) => {
                const dx = ball.posX - q[0], dy = ball.posY - q[1], d = Math.hypot(dx, dy)
                if (d < ball.radius && d > 0) out.push([dx / d, dy / d, 'rim' + k])
            })
        if (blocked)
            P.forEach(A => { const f = portalFrame(A); out.push([f.nx, f.ny, 'blocked' + A.name]) })
        return out
    }
    let won = false, offMap = false, steps = 0
    for (; steps < maxSteps; ) {
        const x0 = ball.posX, y0 = ball.posY, vx0 = ball.speedX, vy0 = ball.speedY, t0 = S.teleports.length
        ball.physics()
        ball.move()
        const vmx = ball.speedX, vmy = ball.speedY, r0 = S.rimHits, b0 = S.blockedExits
        portalStep()
        ++steps
        chk.step(x0, y0, vx0, vy0, ball.posX, ball.posY, ball.speedX, ball.speedY, S.teleports.length !== t0, vmx, vmy,
            S.rimHits === r0 && S.blockedExits === b0 ? null : postNormals(S.rimHits !== r0, S.blockedExits !== b0))
        if (flag && flagCollision(curLevel().flagX, curLevel().flagY)) { won = true; break }
        if (!ball.onMap()) { offMap = true; break }
    }
    return { lines: all.length, portals: P.length, rims: points.length, solidPieces: solid.length, won, offMap,
        frames: +(steps / cyclesPerTact).toFixed(3), end: [ball.posX, ball.posY], blockedExits: portalState.blockedExits,
        hostHits: portalState.hostHits, ...chk.result() }
}"""

RUN_JS = r"""([src, segs, maxFrames]) => {
    const i = levelBySrc(src)
    if (i < 0) return { src, error: 'no level' }
    thisLevel = i
    levelReset(i)
    physics = false   // the page's own loop must not step this ball between evaluates
    const n0 = lines.length
    for (const s of segs) lines.push(new Line(s[0], s[1], s[2], s[3], dotRadius, '#0000ff', 'player'))
    const r = window.__invRun('level' + src, maxFrames * cyclesPerTact, true)
    const out = { src, index: i, playerLines: lines.length - n0, maxFrames, ...r }
    levelReset(i)
    return out
}"""

# TASK-201: one portal fuzz scene (tests/portal/fuzz.py case config) on the __portalTest scratch level
FUZZ_JS = r"""([cfg, label, maxFrames]) => {
    window.__portalTest.setup(cfg)
    physics = false
    return window.__invRun(label, maxFrames * cyclesPerTact, false)
}"""


def solutions():
    out = []
    for n in range(1, 100):
        segs = getattr(shoot, 'LEVEL%d_LINES' % n, None)
        if segs is None and hasattr(shoot, 'LEVEL%d_LINE' % n):
            segs = [getattr(shoot, 'LEVEL%d_LINE' % n)]
        if segs is None:
            continue
        out.append((n, [[a, b, c, d] for (a, b), (c, d) in segs], getattr(shoot, 'LEVEL%d_MAX_FRAMES' % n)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--levels', default=None, help='comma-separated srcIds (default: every shoot levelNN solution)')
    ap.add_argument('--frames', type=int, default=None, help='frame cap override (preview)')
    ap.add_argument('--portal-fuzz', type=int, default=None, help='TASK-201: portal fuzz seed (scenes from tests/portal/fuzz.py)')
    ap.add_argument('--cases', type=int, default=200, help='portal fuzz scenes per seed')
    a = ap.parse_args()
    if a.portal_fuzz is not None:
        return portal_fuzz(a.portal_fuzz, a.cases, a.frames or 300)
    sols = solutions()
    if a.levels:
        want = {int(x) for x in a.levels.split(',')}
        sols = [s for s in sols if s[0] in want]
    from playwright.sync_api import sync_playwright
    core = open(os.path.join(HERE, 'invariants_core.js')).read()
    res = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1280, 'height': 800})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('file://' + os.path.join(ROOT, 'index.html'))
        page.wait_for_function('typeof gamePhysics === "function"')
        page.add_script_tag(content=core)
        page.evaluate(LOOP_JS)
        for n, segs, mf in sols:
            r = page.evaluate(RUN_JS, [n, segs, a.frames or mf])
            r['solution'] = segs
            res.append(r)
            print('level%d: won=%s frames=%s counts=%s' % (n, r.get('won'), r.get('frames'), r.get('counts')), file=sys.stderr)
        browser.close()
    json.dump({'levels': res, 'pageErrors': errors}, sys.stdout, separators=(',', ':'))


PORTAL_KINDS = ('default', 'crossing', 'backside', 'touching')


def portal_cases(seed, n):
    """TASK-201: n scenes for one seed, the four tests/portal/fuzz.py generators in turn (scene i: kind i % 4;
    default / crossing alternate their 'aimed' and 'random' balls), from random.Random(0x9F0000 + seed)."""
    import random
    sys.path.insert(0, os.path.join(ROOT, 'tests', 'portal'))
    import fuzz
    rng = random.Random(0x9F0000 + seed)
    out = []
    for i in range(n):
        kind = PORTAL_KINDS[i % 4]
        aimed = (i // 4) % 2 == 0
        cfg = (fuzz.make_case(rng, aimed) if kind == 'default' else fuzz.make_crossing_case(rng, aimed) if kind == 'crossing'
               else fuzz.make_backside_case(rng) if kind == 'backside' else fuzz.make_touching_case(rng))
        out.append((kind, cfg))
    return out


def portal_fuzz(seed, n, frames):
    """TASK-201: browser-mode invariants on portal fuzz scenes; one compact JSON {seed, scenes: [...]} on stdout."""
    import time
    from playwright.sync_api import sync_playwright
    core = open(os.path.join(HERE, 'invariants_core.js')).read()
    cases = portal_cases(seed, n)
    res = []
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1280, 'height': 800})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('file://' + os.path.join(ROOT, 'index.html'))
        page.wait_for_function('typeof gamePhysics === "function"')
        page.add_script_tag(content=core)
        page.evaluate(LOOP_JS)
        for i, (kind, cfg) in enumerate(cases):
            label = 'p%d#%d' % (seed, i)
            r = page.evaluate(FUZZ_JS, [cfg, label, frames])
            r.update({'scene': i, 'kind': kind})
            for k in ('I1', 'I2', 'I3', 'T'):
                for e in r['examples'][k]:
                    e['cfg'] = cfg   # replayable
            res.append(r)
            if (i + 1) % 20 == 0:
                print('portal fuzz seed %d: %d/%d scenes' % (seed, i + 1, n), file=sys.stderr, flush=True)
        browser.close()
    json.dump({'seed': seed, 'scenes': res, 'frames': frames, 'pageErrors': errors, 'seconds': time.time() - t0},
              sys.stdout, separators=(',', ':'))


if __name__ == '__main__':
    main()
