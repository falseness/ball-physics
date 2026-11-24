#!/usr/bin/env python3
"""Browser mode of the invariant checker (TASK-198): the portal levels' reference solutions inside the game.

  python3 tests/physics/invariants_browser.py [--levels 11,12,...] [--frames N]

Loads index.html (file://, Playwright chromium), injects tests/physics/invariants_core.js and, for every
level with a shoot levelNN scenario (tests/visual/shoot.py LEVELnn_LINE / LEVELnn_LINES, srcId nn), resets the
level (levelReset), adds the solution lines as player lines and steps the game's own gamePhysics() parts
(ball.physics(), ball.move(), portalStep()) exactly as gameMechanics() does, every step through the checker,
until the flag is reached, the ball leaves the map, or LEVELnn_MAX_FRAMES frames of 500 steps.
Contacts: every line plus the portal rims (portalStep collides at the post-move position); I1 depth uses the
lines with each wall portal's opening (c +- h t) cut out of its host line. A step counts as a teleport when
portalState.teleports grows. Prints one compact JSON object {levels: [...]} on stdout.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tests', 'visual'))
import shoot  # noqa: E402  (LEVELnn_LINE(S) / LEVELnn_MAX_FRAMES only)

RUN_JS = r"""([src, segs, maxFrames]) => {
    const i = levelBySrc(src)
    if (i < 0) return { src, error: 'no level' }
    thisLevel = i
    levelReset(i)
    physics = false   // the page's own loop must not step this ball between evaluates
    const n0 = lines.length
    for (const s of segs) lines.push(new Line(s[0], s[1], s[2], s[3], dotRadius, '#0000ff', 'player'))
    const P = currentPortals() || []
    const all = lines.map(l => [l.posX, l.posY, l.posX2, l.posY2])
    // solid geometry for I1: host lines minus their openings
    const cut = {}
    P.forEach(p => { if (typeof p.line == 'number') (cut[p.line] = cut[p.line] || []).push(p) })
    const solid = []
    all.forEach((s, k) => {
        if (!cut[k]) { solid.push(s); return }
        const dx = s[2] - s[0], dy = s[3] - s[1], L = Math.hypot(dx, dy)
        const iv = cut[k].map(p => { const u = ((p.x - s[0]) * dx + (p.y - s[1]) * dy) / (L * L), w = p.h / L; return [u - w, u + w] })
            .sort((a, b) => a[0] - b[0])
        let t = 0
        iv.forEach(([a, b]) => { if (a > t) solid.push([s[0] + t * dx, s[1] + t * dy, s[0] + a * dx, s[1] + a * dy]); t = Math.max(t, b) })
        if (t < 1) solid.push([s[0] + t * dx, s[1] + t * dy, s[2], s[3]])
    })
    const points = []
    P.forEach(p => portalRims(p).forEach(q => points.push(q)))
    const chk = InvariantsCore.makeChecker({ g: gravitationalAcceleration, r: ball.radius, segs: all, points, solid,
        postMoveContacts: true, label: 'level' + src })
    let won = false, offMap = false, steps = 0
    const total = maxFrames * cyclesPerTact
    for (; steps < total; ) {
        const x0 = ball.posX, y0 = ball.posY, vx0 = ball.speedX, vy0 = ball.speedY, t0 = portalState.teleports.length
        ball.physics()
        ball.move()
        const vmx = ball.speedX, vmy = ball.speedY
        portalStep()
        ++steps
        chk.step(x0, y0, vx0, vy0, ball.posX, ball.posY, ball.speedX, ball.speedY, portalState.teleports.length !== t0, vmx, vmy)
        if (flagCollision(curLevel().flagX, curLevel().flagY)) { won = true; break }
        if (!ball.onMap()) { offMap = true; break }
    }
    const res = chk.result()
    const out = { src, index: i, lines: all.length, playerLines: lines.length - n0, portals: P.length, rims: points.length,
        solidPieces: solid.length, won, offMap, frames: +(steps / cyclesPerTact).toFixed(3), maxFrames,
        end: [ball.posX, ball.posY], ...res }
    levelReset(i)
    return out
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
    a = ap.parse_args()
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
        for n, segs, mf in sols:
            r = page.evaluate(RUN_JS, [n, segs, a.frames or mf])
            r['solution'] = segs
            res.append(r)
            print('level%d: won=%s frames=%s counts=%s' % (n, r.get('won'), r.get('frames'), r.get('counts')), file=sys.stderr)
        browser.close()
    json.dump({'levels': res, 'pageErrors': errors}, sys.stdout, separators=(',', ':'))


if __name__ == '__main__':
    main()
