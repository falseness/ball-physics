// Ball vs line-end (point) edge cases, headless (TASK-197). Runs the real js/ball.js through
// tests/physics/harness.mjs (physics() then move(), 500 steps per frame, g = 0.001/500 px/step^2).
// Every expectation is a physical one (reflection about the contact normal, no energy from nowhere,
// no livelock); none is taken from the current behaviour.
// Usage: node tests/physics/edge_cases.mjs [--out FILE] [--only name,name]
// Exit 0 when every case passes, 1 otherwise (each failing case is named on stdout).
import fs from 'node:fs'
import { execSync } from 'node:child_process'
import * as h from './harness.mjs'
import { makeChecker as stuckChecker } from './stuck.mjs'

const { R, G, FPS, STEPS_PER_FRAME, STEPS_PER_SECOND } = h
const r6 = h.round
const CLEAR_MARGIN = 0.5    // contact is over once the centre is more than R + 0.5 px from every segment

// Step until contact (centre within R of a segment), then until clear; returns contact centre / point,
// velocities before contact and at clear, flips of the velocity sign during contact.
function contactPass(w, b, maxSteps, contactCap = 3000)
{
    let vin = null, cpos = null, flips = 0, contactSteps = 0, cleared = false, vout = null
    let pvx = b.speedX, pvy = b.speedY
    for (let s = 0; s < maxSteps; ++s)
    {
        const bx = b.speedX, by = b.speedY
        w.step(b)
        const d = h.distToSegments(b.posX, b.posY, w.segments)
        if (!cpos && d <= R)
        {
            vin = [bx, by]
            cpos = [b.posX, b.posY]
        }
        if (cpos)
        {
            ++contactSteps
            if (Math.sign(b.speedX) * Math.sign(pvx) < 0 || Math.sign(b.speedY) * Math.sign(pvy) < 0) ++flips
            if (d > R + CLEAR_MARGIN) { cleared = true; vout = [b.speedX, b.speedY]; break }
            if (contactSteps >= contactCap) break
        }
        pvx = b.speedX; pvy = b.speedY
    }
    return { vin, cpos, flips, contactSteps, cleared, vout, end: [b.posX, b.posY], vend: [b.speedX, b.speedY] }
}

function nearestPoint(cpos, pts)
{
    let best = null
    for (const p of pts)
        if (!best || Math.hypot(cpos[0] - p[0], cpos[1] - p[1]) < Math.hypot(cpos[0] - best[0], cpos[1] - best[1])) best = p
    return best
}

const CASES = {
    // A ball moving right grazes the free left end (400,300) of (400,300)-(700,300), centre 1..9 px above it.
    graze()
    {
        const seg = [400, 300, 700, 300], P = [400, 300], sub = []
        for (let d = 1; d <= 9; ++d)
        {
            const w = h.makeWorld([seg])
            const b = w.ball(P[0] - Math.sqrt(R * R - d * d) - 2, P[1] - d, 0.02, 0)
            const c = contactPass(w, b, 2000)
            let row = { d, contact: !!c.cpos, cleared: c.cleared, contactSteps: c.contactSteps, flips: c.flips }
            if (c.cpos)
            {
                const nx0 = c.cpos[0] - P[0], ny0 = c.cpos[1] - P[1], nl = Math.hypot(nx0, ny0)
                const n = [nx0 / nl, ny0 / nl], want = h.reflect(c.vin[0], c.vin[1], n[0], n[1])
                const got = c.cleared ? c.vout : c.vend
                const wl = Math.hypot(...want), gl = Math.hypot(...got)
                row = { ...row, n: n.map(v => r6(v, 4)), want: [r6(want[0] / wl, 4), r6(want[1] / wl, 4)],
                    got: [r6(got[0] / gl, 4), r6(got[1] / gl, 4)], errDeg: r6(h.angleBetween(...want, ...got), 3) }
            }
            row.pass = row.cleared && row.errDeg <= 2
            sub.push(row)
        }
        return { pass: sub.every(s => s.pass), limitDeg: 2, maxErrDeg: Math.max(...sub.map(s => (s.errDeg === undefined ? 180 : s.errDeg))), sub }
    },
    // Dropped 3 px right of the tip (400,300) of the vertical line (400,300)-(400,500): leaves with vx > 0.
    spike()
    {
        const w = h.makeWorld([[400, 300, 400, 500]])
        const b = w.ball(403, 270, 0, 0)
        const c = contactPass(w, b, 2 * STEPS_PER_SECOND)
        h.runFrames(w, b, FPS)   // one more second
        const vxClear = c.cleared ? c.vout[0] : null
        return { pass: c.cleared && vxClear > 0, cleared: c.cleared, contactSteps: c.contactSteps, flips: c.flips,
            vxAtClear: r6(vxClear, 8), vAtClear: c.vout && c.vout.map(v => r6(v, 8)), after1s: { x: r6(b.posX, 3), y: r6(b.posY, 3), vx: r6(b.speedX, 8), vy: r6(b.speedY, 8) } }
    },
    // Overlapping the end (400,300) by 1 px and moving straight away from it: no flips, it clears the point.
    moving_away()
    {
        const w = h.makeWorld([[400, 300, 700, 300]])
        const u = [-0.6, -0.8], b = w.ball(400 + 9 * u[0], 300 + 9 * u[1], 0.02 * u[0], 0.02 * u[1])
        let flips = 0, pvx = b.speedX, pvy = b.speedY, steps = 0, cleared = false
        for (; steps < 3000; )
        {
            w.step(b); ++steps
            if (Math.sign(b.speedX) * Math.sign(pvx) < 0 || Math.sign(b.speedY) * Math.sign(pvy) < 0) ++flips
            pvx = b.speedX; pvy = b.speedY
            if (Math.hypot(b.posX - 400, b.posY - 300) > R + CLEAR_MARGIN) { cleared = true; break }
        }
        return { pass: flips === 0 && cleared, flips, steps, cleared, distToPoint: r6(Math.hypot(b.posX - 400, b.posY - 300), 4) }
    },
    // Rolling down (100,200)-(400,300) onto (400,300)-(700,300): passes x = 450, never back to x < 380.
    // Run from rest at 3 places on the slope, with the lines in both array orders (the game's line order is
    // arbitrary: level lines then player lines, so the outcome must not depend on it).
    joint()
    {
        const slope = [100, 200, 400, 300], floor = [400, 300, 700, 300], sub = []
        for (const order of ['slope_first', 'floor_first'])
            for (const t of [0, 0.1, 0.5])
            {
                const w = h.makeWorld(order === 'slope_first' ? [slope, floor] : [floor, slope])
                const [x, y] = h.restingOn(slope, t), b = w.ball(x, y, 0, 0)
                let reached450 = null, passedJoint = null, minXAfter = Infinity, backUps = 0, wasRight = false
                h.runFrames(w, b, 10 * FPS, (bb, s) =>
                {
                    if (passedJoint === null && bb.posX >= 400) passedJoint = s
                    if (passedJoint !== null)
                    {
                        minXAfter = Math.min(minXAfter, bb.posX)
                        if (bb.posX >= 400) wasRight = true
                        if (wasRight && bb.posX < 380) { ++backUps; wasRight = false }
                    }
                    if (reached450 === null && bb.posX >= 450) reached450 = s
                    return bb.posX > 700 || bb.posY > 1000
                })
                sub.push({ order, t, pass: reached450 !== null && minXAfter >= 380, reached450Step: reached450, passedJointStep: passedJoint,
                    minXAfterJoint: r6(minXAfter, 3), throwsBackUpSlope: backUps, end: { x: r6(b.posX, 3), y: r6(b.posY, 3), vx: r6(b.speedX, 6), vy: r6(b.speedY, 6) } })
            }
        return { pass: sub.every(s => s.pass), failingSub: sub.filter(s => !s.pass).map(s => `${s.order}@t=${s.t}`), sub }
    },
    // Rolling along (100,300)-(400,300) + (400,300)-(700,300): the seam adds no vy kick above 1e-6 per step
    // (kick = largest |vy| within R + 2 px of the seam minus the largest |vy| on the plain floor, x 200..300).
    seam()
    {
        const w = h.makeWorld([[100, 300, 400, 300], [400, 300, 700, 300]])
        const b = w.ball(200, 290, 0.02, 0)
        let refVy = 0, seamVy = 0, seamDv = 0, refDv = 0, minVx = Infinity, pvy = b.speedY
        h.runFrames(w, b, 2 * FPS, (bb) =>
        {
            const dv = Math.abs(bb.speedY - pvy); pvy = bb.speedY
            if (bb.posX >= 200 && bb.posX <= 300) { refVy = Math.max(refVy, Math.abs(bb.speedY)); refDv = Math.max(refDv, dv) }
            if (Math.abs(bb.posX - 400) < R + 2) { seamVy = Math.max(seamVy, Math.abs(bb.speedY)); seamDv = Math.max(seamDv, dv); minVx = Math.min(minVx, bb.speedX) }
            return bb.posX > 600
        })
        const kick = seamVy - refVy
        return { pass: kick <= 1e-6 && minVx > 0, limit: 1e-6, kick: r6(kick, 9), seamMaxAbsVy: r6(seamVy, 9), floorMaxAbsVy: r6(refVy, 9),
            seamMaxDvyPerStep: r6(seamDv, 9), floorMaxDvyPerStep: r6(refDv, 9), minVxAtSeam: r6(minVx, 6), endX: r6(b.posX, 3) }
    },
    // TASK-200 ghost vertices: a straight slope split in two at its middle (shared end point) must act like one
    // line: every contact impulse J = (v1 - v0) - (0, g) is along the slope normal, so |J . t| (t = slope
    // direction) <= 1e-12 px/step on every step. An end-point contact at the joint (normal (c - V)/|c - V|, outside
    // the joint's cone) would be a tangential kick. Slopes of 8, 20 and 40 degrees, both line orders and one line
    // reversed; balls dropped 15 / 40 px above the slope 2 / 4 / 8 px either side of the joint, and one released
    // 60 px up the slope; each runs until its centre projects past an outer free end of the slope (|s| >= 250 px
    // from the joint along the slope, max 4 s) and must end below-left of the joint. TASK-270: the run used to end at
    // x 120..680, past the outer ends; with elastic contacts a dropped ball keeps bouncing down the slope instead of
    // settling into a roll, so it can land on the free outer end (152, 335) itself, a real corner whose end-point
    // normal is meant to kick (edge_cases graze / spike); this case is about the joint, so it stops at the ends.
    slope_seam()
    {
        const sub = []
        let worst = 0
        for (const deg of [8, 20, 40])
        {
            const a = deg * Math.PI / 180, c = Math.cos(a), sn = Math.sin(a)
            const P0 = [400 - 250 * c, 300 + 250 * sn], V = [400, 300], P1 = [400 + 250 * c, 300 - 250 * sn]
            const nx = -sn, ny = -c   // upward normal of the slope
            const starts = []
            for (const dx of [-8, -4, -2, 2, 4, 8])
                for (const hgt of [15, 40])
                    starts.push([V[0] + dx * c + (R + hgt) * nx, V[1] - dx * sn + (R + hgt) * ny])
            starts.push([V[0] + 60 * c + R * nx, V[1] - 60 * sn + R * ny])
            for (const order of ['low_first', 'high_first', 'reversed'])
            {
                const A = [...P0, ...V], B = order === 'reversed' ? [...P1, ...V] : [...V, ...P1]
                const w = h.makeFastWorld(order === 'high_first' ? [B, A] : [A, B])
                let maxJt = 0, kicks = 0, rolledDown = true, first = null
                for (const st of starts)
                {
                    const b = w.ball(st[0], st[1], 0, 0)
                    for (let s = 0; s < 4 * STEPS_PER_SECOND; ++s)
                    {
                        const vx0 = b.speedX, vy0 = b.speedY
                        w.step(b)
                        const jt = Math.abs((b.speedX - vx0) * c - (b.speedY - vy0 - G) * sn)
                        if (jt > maxJt) maxJt = jt
                        if (jt > 1e-12) { ++kicks; if (!first) first = { start: st.map(v => r6(v, 3)), step: s, jt, at: [r6(b.posX, 4), r6(b.posY, 4)] } }
                        if (Math.abs((b.posX - V[0]) * c - (b.posY - V[1]) * sn) >= 250) break
                    }
                    // downhill of the joint along the slope (a bouncing ball may be above the joint's height there)
                    if (!((b.posX - V[0]) * c - (b.posY - V[1]) * sn < 0)) rolledDown = false
                }
                worst = Math.max(worst, maxJt)
                sub.push({ deg, order, starts: starts.length, maxTangentialJ: maxJt, kickSteps: kicks, first, rolledDown, pass: maxJt <= 1e-12 && rolledDown })
            }
        }
        return { pass: sub.every(s => s.pass), limit: 1e-12, maxTangentialJ: worst, failingSub: sub.filter(s => !s.pass).map(s => `${s.deg}deg/${s.order}`), sub }
    },
    // Dropped into the V (300,200)-(500,400)-(700,200) (TASK-270, the user's rule replaces TASK-197's 'comes to rest
    // within 2 s'): "lets fix the physcis so we dont loose and dont gain the energy (without portals)", answered
    // "Yes, bounce forever (Recommended)" (with no loss a ball never comes to rest: it bounces back to the same height
    // on a floor and rocks in a V forever). Over 10 s the ball rocks in the V: it never leaves it (centre inside the
    // V's walls, below the arms' top y = 200, |x - 500| < 200), keeps E within the TASK-266 (tests/physics/energy.mjs)
    // tolerance (every step |dE| <= 1e-9 E_ref, end drift <= 1e-7 E_ref, E = |v|^2/2 + g vy/2 + g (800 - y)) and is
    // never stuck (tests/physics/stuck.mjs checks a-d: depth, tunnelling, livelock, freeze), and it keeps moving
    // (each 1 s window spans more than 1 px).
    v_corner()
    {
        const segs = [[300, 200, 500, 400], [500, 400, 700, 200]]
        const E = (y, vx, vy) => 0.5 * (vx * vx + vy * vy) + 0.5 * G * vy + G * (800 - y)
        const w2 = h.makeWorld(segs), b2 = w2.ball(495, 360, 0, 0), frames = []
        const st = stuckChecker(segs, b2.posX, b2.posY)
        const Estart = E(b2.posY, b2.speedX, b2.speedY)
        let maxKE = 0, maxStepDE = 0, left = 0, x0, y0, vx0, vy0
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
        for (let s = 0; s < 10 * STEPS_PER_SECOND; ++s)
        {
            x0 = b2.posX; y0 = b2.posY; vx0 = b2.speedX; vy0 = b2.speedY
            w2.step(b2)
            const ke = 0.5 * (b2.speedX * b2.speedX + b2.speedY * b2.speedY)
            if (ke > maxKE) maxKE = ke
            maxStepDE = Math.max(maxStepDE, Math.abs(E(b2.posY, b2.speedX, b2.speedY) - E(y0, vx0, vy0)))
            st.step(x0, y0, b2.posX, b2.posY, b2.speedX, b2.speedY)
            // inside the V: the centre stays above both walls (y < 400 - |x - 500|), between the arms' tops
            if (!(b2.posY > 200 - R && b2.posY < 400 - Math.abs(b2.posX - 500) + 1e-6 && Math.abs(b2.posX - 500) < 200)) ++left
            minX = Math.min(minX, b2.posX); maxX = Math.max(maxX, b2.posX); minY = Math.min(minY, b2.posY); maxY = Math.max(maxY, b2.posY)
            if ((s + 1) % STEPS_PER_SECOND === 0)
            {
                frames.push(Math.max(maxX - minX, maxY - minY))
                minX = Infinity; maxX = -Infinity; minY = Infinity; maxY = -Infinity
            }
        }
        const Eref = G * 800 + maxKE, drift = E(b2.posY, b2.speedX, b2.speedY) - Estart
        const sr = st.result(), moving = frames.every(f => f > 1)
        const pass = left === 0 && maxStepDE <= 1e-9 * Eref && Math.abs(drift) <= 1e-7 * Eref && sr.pass && moving
        return { pass, seconds: 10, stepsOutsideV: left, maxStepDERel: r6(maxStepDE / Eref, 15), endDriftRel: r6(drift / Eref, 15),
            tol: { step: 1e-9, scene: 1e-7 }, stuck: { pass: sr.pass, counts: sr.counts, maxDepth: sr.maxDepth },
            spanPerSecondPx: frames.map(f => r6(f, 3)), moving, end: { x: r6(b2.posX, 3), y: r6(b2.posY, 3) } }
    },
    // The srcId-10 pocket from artifacts/edges_bug.png (level 10 lines, ball launched up at ~967 px/s under the
    // shelf end (200,200) as in the screenshot): 10 s with no livelock window (1 s inside a 2 px box at >= 60 px/s).
    shelf_pocket()
    {
        const lines = [[100, 10, 100, 300], [100, 300, 300, 300], [300, 200, 200, 200], [200, 200, 200, 150], [200, 150, 300, 150], [300, 200, 300, 10]]
        const sub = []
        for (const [x, y, vx, vy] of POCKET_STARTS)
        {
            const w = h.makeWorld(lines), b = w.ball(x, y, vx, vy)
            const fr = h.runFrames(w, b, 10 * FPS)
            const ll = h.livelockWindows(fr)
            sub.push({ start: [x, y, vx, vy], livelockWindows: ll.length, first: ll[0] || null, end: { x: r6(b.posX, 3), y: r6(b.posY, 3) }, pass: ll.length === 0 })
        }
        return { pass: sub.every(s => s.pass), rule: { boxPx: h.LIVELOCK_BOX_PX, meanSpeedPxPerStep: h.LIVELOCK_MEAN_SPEED, windowS: 1 }, sub }
    },
    // A ball moving right along y = 300 hits the end (400,300) straight on: it reverses (within 2 degrees).
    head_on()
    {
        const w = h.makeWorld([[400, 300, 700, 300]])
        const b = w.ball(388, 300, 0.02, 0)
        const c = contactPass(w, b, 2000)
        const got = c.cleared ? c.vout : c.vend
        const err = h.angleBetween(got[0], got[1], -c.vin[0], -c.vin[1])
        return { pass: c.cleared && err <= 2, cleared: c.cleared, contactSteps: c.contactSteps, flips: c.flips,
            vin: c.vin.map(v => r6(v, 8)), vout: got.map(v => r6(v, 8)), errDeg: r6(err, 3), speedRatio: r6(Math.hypot(...got) / Math.hypot(...c.vin), 4) }
    },
}
// [x, y, vx, vy]: the screenshot start (under the shelf end, moving up at 0.03224 px/step = 967 px/s), a ball aimed
// at the shelf end (200,200) from below-left at 0.015 px/step, and one moving right just under the shelf
const POCKET_STARTS = [[207, 285, 0, -0.03224], [182.322, 217.678, 0.010607, -0.010607], [150, 195, 0.02, 0]]

const args = process.argv.slice(2)
const outI = args.indexOf('--out'), out = outI >= 0 ? args[outI + 1] : null
const onlyI = args.indexOf('--only'), only = onlyI >= 0 ? args[onlyI + 1].split(',') : null
let head = null
try { head = execSync('git rev-parse --short HEAD', { cwd: h.ROOT }).toString().trim() } catch (e) { }
let dirty = null
try { dirty = execSync('git status --porcelain js/ball.js js/sprite.js', { cwd: h.ROOT }).toString().trim() !== '' } catch (e) { }
const results = []
for (const name of Object.keys(CASES))
{
    if (only && !only.includes(name)) continue
    const t0 = Date.now(), res = CASES[name]()
    results.push({ name, ...res, ms: Date.now() - t0 })
    console.log(`${res.pass ? 'PASS' : 'FAIL'} ${name}`)
}
const failing = results.filter(r => !r.pass).map(r => r.name)
const exit = failing.length ? 1 : 0
const report = { head, ballJsDirty: dirty, stepsPerFrame: STEPS_PER_FRAME, g: G, radius: R, exit, failing, cases: results }
if (out) fs.writeFileSync(out, JSON.stringify(report) + '\n')
console.log(failing.length ? `FAILING: ${failing.join(', ')}` : 'ALL PASS')
process.exit(exit)
