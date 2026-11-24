// Ball physics invariant checker core (TASK-198). A classic script (no import/export) so the same
// code runs in node (tests/physics/invariants.mjs loads it with new Function) and inside the game page
// (tests/physics/invariants_browser.py injects it for the portal levels). Defines InvariantsCore.
//
// One checker per simulated ball. Feed it every step, in order (no sampling):
//   chk.step(x0, y0, vx0, vy0, x1, y1, vx1, vy1, tele, vmx, vmy, post)
// (x0, y0, vx0, vy0) = ball state before the step, (x1, ...) = after it; tele = a portal teleport
// happened in this step, (vmx, vmy) = the velocity right before portalStep() (teleport steps only);
// post (optional) = [[nx, ny, src], ...] the normals portalStep() reflected about after the move in this
// step (rim bounces, refused teleports bouncing off the entry plane; TASK-201), taken as contacts.
//
// Geometry (opts): segs [[x1,y1,x2,y2]] = contact candidates (every line), points [[x,y]] = point
// colliders (portal rims), solid [[x1,y1,x2,y2]] = what the ball must never sink into (default segs;
// the portal levels pass the host lines minus their openings), postMoveContacts = also take contacts at
// the post-move position (lines and points). The browser mode does not use it (TASK-201): lines are only
// resolved at the step's start position (ball.physics() runs before ball.move()), so a ball that merely
// moves into a line's reach is a free step, and portalStep's rims / openings only act in some states
// (front side, not refused by a line); it passes the normals portalStep actually used (post) instead.
//
// I1 'no stuck': (a) depth: the centre is more than STUCK_DEPTH inside a solid line (distance <
//    R - 0.5) for more than 2 consecutive steps (one violation per episode, at its 3rd step);
//    (b) livelock: >= 20 velocity sign flips (v_before . v_after < 0, both speeds >= FLIP_MIN_SPEED)
//    within 200 steps while the centre stays inside a 0.5 px box over those 200 steps (one per episode).
//    FLIP_MIN_SPEED = 1e-4 px/step = 50 g: a ball micro-bouncing on a floor under gravity alone flips
//    at most once per 2|v|/g steps, so 20 flips in 200 steps needs |v| <= 10 g; such gravity jitter is
//    not a livelock, flips at >= 50 g are made by the contact itself.
// I2 'plausible velocity': without contact (centre farther than R from every line and point) the
//    velocity change is exactly the gravity step: vx1 === vx0 and vy1 === vy0 + g. On a contact step
//    the contact impulse J = (v1 - v0) - (0, g) must be explained by one contact normal n (from the
//    closest point of a touched line / point to the centre):
//      tangential: |J.t| <= 1e-9 * max(|v0|, |v1|, g)
//      vn_grow:    |v1.n| <= |v0.n| + |g.n| (+ tol)  (the contact may absorb gravity's normal part)
//      vn_into:    v1.n - min(g.n, 0) >= -tol      (after the contact the ball leaves the line; gravity
//                  added in the same step may point it back in by at most g.n)
//      away:       v0.n > tol (already moving away) => |J| <= tol (left unchanged)
//    or, with 2+ contacts, J is a non-negative combination a n1 + b n2 of two touched normals with v1
//    leaving both (vn_into on each) - a corner resolved in one step.
// I3 'energy': on a contact step E1 - E0 <= 1e-6 * |E0| with E = |v|^2/2 + g vy/2 + g (H - y), H = 800.
//    E is the exact free-flight invariant of the game's integrator (v += g, then x += v), so a free
//    step keeps it to rounding and a contact may only keep or lower it.
// T  'teleport': portal teleport steps are exempt from I2/I3; instead |v after portalStep| equals
//    |v before portalStep| within 1e-9 relative.
var InvariantsCore = (function ()
{
    var STUCK_DEPTH = 0.5, STUCK_STEPS = 2
    var LIVELOCK_FLIPS = 20, LIVELOCK_WINDOW = 200, LIVELOCK_BOX = 0.5, FLIP_MIN_SPEED = 1e-4
    var REL_TOL = 1e-9, ENERGY_REL = 1e-6, TELE_REL = 1e-9, H = 800, CONTACT_EPS = 1e-9
    var KINDS = ['I1', 'I2', 'I3', 'T']

    function r(v) { return typeof v === 'number' && isFinite(v) ? +v.toPrecision(10) : v }

    // closest point on a segment -> [cx, cy, dist]
    function closest(px, py, s)
    {
        var x1 = s[0], y1 = s[1], dx = s[2] - x1, dy = s[3] - y1, L2 = dx * dx + dy * dy
        var t = L2 > 0 ? ((px - x1) * dx + (py - y1) * dy) / L2 : 0
        if (t < 0) t = 0; else if (t > 1) t = 1
        var cx = x1 + t * dx, cy = y1 + t * dy
        return [cx, cy, Math.hypot(px - cx, py - cy)]
    }

    function makeChecker(opts)
    {
        var G = opts.g, R = opts.r
        var segs = opts.segs || [], points = opts.points || [], solid = opts.solid || segs
        var postMove = !!opts.postMoveContacts, maxEx = opts.maxExamples === undefined ? 5 : opts.maxExamples
        var label = opts.label === undefined ? null : opts.label
        // bounding boxes grown by R + 1 for a cheap reject
        function boxes(list)
        {
            return list.map(function (s)
            {
                var m = R + 1
                return [Math.min(s[0], s[2]) - m, Math.max(s[0], s[2]) + m, Math.min(s[1], s[3]) - m, Math.max(s[1], s[3]) + m]
            })
        }
        var segBox = boxes(segs), solidBox = boxes(solid)
        var counts = { I1: 0, I2: 0, I3: 0, T: 0 }, sub = {}, examples = { I1: [], I2: [], I3: [], T: [] }
        var steps = 0, contactSteps = 0, teleports = 0
        var insideRun = 0
        var flipRing = new Uint8Array(LIVELOCK_WINDOW), xr = new Float64Array(LIVELOCK_WINDOW), yr = new Float64Array(LIVELOCK_WINDOW)
        var flips = 0, filled = 0, llQuiet = 0

        function report(kind, subkind, data)
        {
            ++counts[kind]
            sub[kind + ':' + subkind] = (sub[kind + ':' + subkind] || 0) + 1
            if (examples[kind].length < maxEx)
            {
                var e = { kind: subkind, step: steps }
                if (label !== null) e.scene = label
                for (var k in data) e[k] = Array.isArray(data[k]) ? data[k].map(r) : r(data[k])
                examples[kind].push(e)
            }
        }

        // contact normals at (px, py): [nx, ny, dist, src]
        function contactsAt(px, py, out)
        {
            for (var i = 0; i < segs.length; ++i)
            {
                var b = segBox[i]
                if (px < b[0] || px > b[1] || py < b[2] || py > b[3]) continue
                var c = closest(px, py, segs[i])
                if (c[2] < R + CONTACT_EPS && c[2] > 0)
                    out.push([(px - c[0]) / c[2], (py - c[1]) / c[2], c[2], 'line' + i])
            }
            for (var j = 0; j < points.length; ++j)
            {
                var d = Math.hypot(px - points[j][0], py - points[j][1])
                if (d < R + CONTACT_EPS && d > 0)
                    out.push([(px - points[j][0]) / d, (py - points[j][1]) / d, d, 'point' + j])
            }
            return out
        }

        function minSolidDist(px, py)
        {
            var best = Infinity
            for (var i = 0; i < solid.length; ++i)
            {
                var b = solidBox[i]
                if (px < b[0] || px > b[1] || py < b[2] || py > b[3]) continue
                var d = closest(px, py, solid[i])[2]
                if (d < best) best = d
            }
            return best
        }

        // single-normal test; returns null when plausible, else the list of failed conditions
        function failsFor(n, vx0, vy0, vx1, vy1, Jx, Jy, tol)
        {
            var nx = n[0], ny = n[1], f = null
            var Jt = -Jx * ny + Jy * nx
            var vnb = vx0 * nx + vy0 * ny, vna = vx1 * nx + vy1 * ny, gn = G * ny
            if (Math.abs(Jt) > tol) (f = f || []).push('tangential')
            if (Math.abs(vna) > Math.abs(vnb) + Math.abs(gn) + tol) (f = f || []).push('vn_grow')
            if (vna - Math.min(gn, 0) < -tol) (f = f || []).push('vn_into')
            if (vnb > tol && Math.hypot(Jx, Jy) > tol) (f = f || []).push('away_changed')
            return f
        }

        function energy(y, vx, vy) { return 0.5 * (vx * vx + vy * vy) + 0.5 * G * vy + G * (H - y) }

        function step(x0, y0, vx0, vy0, x1, y1, vx1, vy1, tele, vmx, vmy, post)
        {
            ++steps
            // ---- I1a depth (post-step position)
            if (minSolidDist(x1, y1) < R - STUCK_DEPTH)
            {
                ++insideRun
                if (insideRun === STUCK_STEPS + 1)
                    report('I1', 'stuck', { pos: [x1, y1], v: [vx1, vy1], depth: R - minSolidDist(x1, y1) })
            }
            else insideRun = 0
            // ---- I1b livelock
            var slot = steps % LIVELOCK_WINDOW
            var s0 = Math.hypot(vx0, vy0), s1 = Math.hypot(vx1, vy1)
            var flip = (vx0 * vx1 + vy0 * vy1 < 0 && s0 >= FLIP_MIN_SPEED && s1 >= FLIP_MIN_SPEED) ? 1 : 0
            flips += flip - flipRing[slot]
            flipRing[slot] = flip; xr[slot] = x1; yr[slot] = y1
            if (filled < LIVELOCK_WINDOW) ++filled
            if (llQuiet > 0) --llQuiet
            else if (flips >= LIVELOCK_FLIPS && filled === LIVELOCK_WINDOW)
            {
                var ax = Infinity, bx = -Infinity, ay = Infinity, by = -Infinity
                for (var k = 0; k < LIVELOCK_WINDOW; ++k)
                {
                    if (xr[k] < ax) ax = xr[k]; if (xr[k] > bx) bx = xr[k]
                    if (yr[k] < ay) ay = yr[k]; if (yr[k] > by) by = yr[k]
                }
                if (bx - ax < LIVELOCK_BOX && by - ay < LIVELOCK_BOX)
                {
                    report('I1', 'livelock', { pos: [x1, y1], v: [vx1, vy1], flips: flips, box: Math.max(bx - ax, by - ay) })
                    llQuiet = LIVELOCK_WINDOW   // one report per episode window
                }
            }
            // ---- teleport rule
            if (tele)
            {
                ++teleports
                var sm = Math.hypot(vmx, vmy)
                if (Math.abs(s1 - sm) > TELE_REL * Math.max(sm, 1e-300))
                    report('T', 'speed', { vBefore: [vmx, vmy], vAfter: [vx1, vy1], rel: Math.abs(s1 - sm) / sm })
                return
            }
            // ---- I2 / I3
            var cs = contactsAt(x0, y0, [])
            if (postMove) contactsAt(x1, y1, cs)
            if (post)
                for (var pi = 0; pi < post.length; ++pi)
                    cs.push([post[pi][0], post[pi][1], 0, post[pi][2]])
            if (cs.length === 0)
            {
                if (vx1 !== vx0 || vy1 !== vy0 + G)
                    report('I2', 'free_dv', { pos: [x0, y0], v0: [vx0, vy0], v1: [vx1, vy1], dv: [vx1 - vx0, vy1 - vy0], g: G })
                return
            }
            ++contactSteps
            var Jx = vx1 - vx0, Jy = vy1 - vy0 - G
            var tol = REL_TOL * Math.max(s0, s1, G)
            var ok = false, best = null, bestFails = null
            for (var i = 0; i < cs.length && !ok; ++i)
            {
                var f = failsFor(cs[i], vx0, vy0, vx1, vy1, Jx, Jy, tol)
                if (!f) ok = true
                else if (!best || cs[i][2] < best[2]) { best = cs[i]; bestFails = f }
            }
            if (!ok && cs.length >= 2)
            {
                // corner: J = a n1 + b n2, a, b >= 0, v1 leaving both
                for (var p = 0; p < cs.length && !ok; ++p)
                    for (var q = p + 1; q < cs.length && !ok; ++q)
                    {
                        var n1 = cs[p], n2 = cs[q], det = n1[0] * n2[1] - n1[1] * n2[0]
                        if (Math.abs(det) < 1e-9) continue
                        var a = (Jx * n2[1] - Jy * n2[0]) / det, b = (n1[0] * Jy - n1[1] * Jx) / det
                        if (a < -tol || b < -tol) continue
                        var into = false
                        for (var m = 0; m < 2; ++m)
                        {
                            var n = m ? n2 : n1, vna = vx1 * n[0] + vy1 * n[1]
                            if (vna - Math.min(G * n[1], 0) < -tol) into = true
                        }
                        if (!into) ok = true
                    }
            }
            if (!ok)
            {
                // sub-counts per failed condition of the deepest contact (I2:contact = steps)
                for (var u = 0; u < bestFails.length; ++u) sub['I2:' + bestFails[u]] = (sub['I2:' + bestFails[u]] || 0) + 1
                report('I2', 'contact', { fails: bestFails.join('+'), pos: [x0, y0], v0: [vx0, vy0], v1: [vx1, vy1], n: [best[0], best[1]],
                    dist: best[2], src: best[3], contacts: cs.length })
            }
            var E0 = energy(y0, vx0, vy0), E1 = energy(y1, vx1, vy1)
            if (E1 - E0 > ENERGY_REL * Math.abs(E0))
                report('I3', 'gain', { pos: [x0, y0], v0: [vx0, vy0], v1: [vx1, vy1], E0: E0, rel: (E1 - E0) / Math.abs(E0), contacts: cs.length })
        }

        function result()
        {
            return { steps: steps, contactSteps: contactSteps, teleports: teleports, counts: counts, sub: sub, examples: examples }
        }
        return { step: step, result: result }
    }

    // Merge per-ball results: counts and sub-counts add up, examples keep the first maxEx per invariant.
    function merge(list, maxEx)
    {
        maxEx = maxEx === undefined ? 5 : maxEx
        var out = { runs: 0, steps: 0, contactSteps: 0, teleports: 0, counts: { I1: 0, I2: 0, I3: 0, T: 0 }, sub: {}, examples: { I1: [], I2: [], I3: [], T: [] } }
        list.forEach(function (x)
        {
            out.runs += x.runs === undefined ? 1 : x.runs
            out.steps += x.steps; out.contactSteps += x.contactSteps; out.teleports += x.teleports
            KINDS.forEach(function (k)
            {
                out.counts[k] += x.counts[k]
                for (var i = 0; i < x.examples[k].length && out.examples[k].length < maxEx; ++i) out.examples[k].push(x.examples[k][i])
            })
            for (var s in x.sub) out.sub[s] = (out.sub[s] || 0) + x.sub[s]
        })
        return out
    }

    return { makeChecker: makeChecker, merge: merge, closest: closest, KINDS: KINDS,
        params: { STUCK_DEPTH: STUCK_DEPTH, STUCK_STEPS: STUCK_STEPS, LIVELOCK_FLIPS: LIVELOCK_FLIPS, LIVELOCK_WINDOW: LIVELOCK_WINDOW,
            LIVELOCK_BOX: LIVELOCK_BOX, FLIP_MIN_SPEED: FLIP_MIN_SPEED, REL_TOL: REL_TOL, ENERGY_REL: ENERGY_REL, TELE_REL: TELE_REL, H: H } }
})()
