// Portal physics core.
//
// levels[i].portals = [A, B] (optional): wall portals {line, u, side, h, name} on the level's own
// lines (see portalResolve); currentPortals() returns them resolved to {x, y, angle, h, ...}.
// Front normal n = (cos angle, sin angle), tangent t = (-n.y, n.x); the opening is the
// segment c ± h·t. For the ball centre p: d = (p - c)·n (signed distance), s = (p - c)·t.
// Capture by touch (TASK-074, 'generous' edge): a ball on a portal's front (d > 0) moving toward
// it (v·n < 0) teleports in the first step it touches the opening segment c ± h·t
// (pointSegDist(centre, opening) <= ball.radius, rims included), so |s| up to h + ball.radius
// is captured; it is placed at local (-clamp(s, -h, h), d) in front of the exit ('touch').
// TASK-201: also in the first step it touches the host line next to the opening (contact point within
// h + ball.radius of c along t) on a straight path that would touch the opening (portalZoneTouch); the
// ball no longer sinks into the host line until it touches the opening itself.
// Fallback crossing ('cross', e.g. a ball faster than its radius per step): d went from > 0 to
// <= 0 since the previous step while |s| <= h (a legacy free-standing portal without `line`
// also back -> front); it maps (s, d) -> (-s, -d).
// Both rotate the velocity by (angleExit - angleEntry + PI), so a ball entering a front leaves
// through the other portal's front, moving away from it.
// The rims (c ± h·t) are solid points for balls that are not being captured (moving away, or behind
// a legacy free-standing portal); behind a wall portal (d <= 0) the rims are skipped because the
// whole host line already collides there (TASK-164); the portal body is not a collider. A wall portal's
// host line takes part in the ball's contact model (TASK-201, portalHostSegs): as the pieces outside the
// opening while the ball centre is in front of the portal (d > 0), without the gap edges while the ball
// moves away from that front, and as the whole line from behind. A ball being captured ignores a host-line
// contact the capture covers (portalCaptureZone / portalZoneTouch) and is teleported at the step's end;
// other contacts are resolved like any line (closest point, deepest first, push-out, no energy gain).
// Other lines may cross an opening (TASK-104) and stay solid: no capture through such a line
// (portalTouches), and a teleport whose exit centre would be on the far side of a line other than
// the exit's host line is refused, the ball bounces off the entry plane instead (portalTeleport).

// blockedExits / blocked (TASK-104): teleports refused because a line blocks the exit spot (count /
// the first RIM_LOG_MAX records, teleport records with blocked: true and the bounced state in after)
// rims: the first RIM_LOG_MAX rim bounces {step, rim, n, before:[vx,vy], after:[vx,vy]}
// hostHits: host-line collisions so far; hostHit: the latest {step, line, v: [vx, vy] before}
// grace (TASK-201): the portal the ball last came out of while the ball still touches its opening (else null):
// it cannot capture the ball by touch again (the 'cross' fallback stays). A ball leaving an exit with a tiny
// normal speed (it entered grazing) was pulled back by gravity into the exit's touch in the next step and
// thrown between the two portals every 2 steps (fuzz --crossing --seed 3 case 1231: 671 teleports in a row).
const RIM_LOG_MAX = 64
const PORTAL_EXIT_MIN_D = 1e-6   // touch teleport: minimum exit distance in front of the exit plane
const PORTAL_DEFAULT_H = 45      // half-width h of a newly placed portal (physics/drawing always read P.h)
let portalState = { prevD: [], teleports: [], rimHits: 0, rims: [], steps: 0, hostHits: 0, hostHit: null, blockedExits: 0, blocked: [], grace: null }

function portalReset()
{
    portalState = { prevD: [], teleports: [], rimHits: 0, rims: [], steps: 0, hostHits: 0, hostHit: null, blockedExits: 0, blocked: [], grace: null }
}

// The path preview (Bounce.calc) runs gamePhysics() too: it must start from the same portal
// state as the real run and must not leave its own state (stored sides, teleport log) behind.
function portalCopy(s)
{
    return {
        prevD: s.prevD.slice(), teleports: s.teleports.slice(),
        rimHits: s.rimHits, rims: s.rims.slice(), steps: s.steps,
        hostHits: s.hostHits, hostHit: s.hostHit,
        blockedExits: s.blockedExits || 0, blocked: (s.blocked || []).slice(), grace: s.grace || null
    }
}

function portalSave()
{
    const saved = portalState
    portalState = portalCopy(saved)
    return saved
}

function portalRestore(saved)
{
    portalState = saved
}

// ---- Wall portals ----
// A level portal sits on one of the level's own lines: {line: i, u: 0..1, side: +1|-1, h, name}.
// portalResolve(P, lines) derives the free-standing frame the physics and drawing work on:
// t = the host line's unit direction (posX,posY) -> (posX2,posY2), front normal n = side * (-ty, tx),
// centre c = lerp(line ends, u) and angle = atan2(n). u is clamped so the opening c ± h·t plus
// ball.radius stays inside the line (u = 0.5 when the line is too short for that).
// A portal without a numeric `line` (legacy {x, y, angle, h}, e.g. the portal tests' setup) is
// returned as a plain copy.
function portalClampU(u, len, h)
{
    const m = h + ball.radius
    if (!(len > 0) || len < 2 * m)
        return 0.5
    return Math.min(Math.max(u, m / len), 1 - m / len)
}

function portalResolve(P, lines)
{
    if (typeof P.line != 'number')
        return portalWithFrame(Object.assign({}, P))
    const l = lines[P.line]
    const dx = l.posX2 - l.posX, dy = l.posY2 - l.posY, len = Math.hypot(dx, dy)
    const tx = len > 0 ? dx / len : 1, ty = len > 0 ? dy / len : 0
    const side = P.side < 0 ? -1 : 1, u = portalClampU(P.u, len, P.h)
    return portalWithFrame({
        x: l.posX + u * dx, y: l.posY + u * dy, angle: Math.atan2(side * tx, side * -ty),
        h: P.h, name: P.name, line: P.line, u: u, side: side
    })
}

// A resolved portal keeps its frame (portalFrame's values for its angle) in `frame`, so the
// per-step physics does not recompute cos/sin or allocate; portalFrame only uses it while P.angle
// is still the angle it was computed for.
function portalWithFrame(R)
{
    R.frame = portalFrameOf(R.angle)
    return R
}

function portalResolveAll(list, lines)
{
    return (list || []).map(P => portalResolve(P, lines))
}

// Resolved portals of the current level, cached per level object, portal list and host line
// coordinates: levelChoosed() refreshes it and any change to a host line re-resolves it.
// vals holds the numbers the cache was resolved from (per portal: a host-line flag, then the host
// line's posX, posY, posX2, posY2, u, side, h, or x, y, angle, h for a legacy portal); portalRefresh
// compares them in place every call (no strings, no allocation) and re-resolves when one differs.
const PORTAL_VALS_PER = 8
let portalCache = { level: null, src: null, vals: [], list: null, hosts: null }

// same value: === plus NaN == NaN (the old string key treated NaN as equal to itself)
function portalSame(a, b)
{
    return a === b || (a !== a && b !== b)
}

// Writes (store) or compares (!store) the cache numbers of src; returns true when they all match
function portalVals(src, lines, vals, store)
{
    if (!store && vals.length !== src.length * PORTAL_VALS_PER)
        return false
    if (store)
        vals.length = src.length * PORTAL_VALS_PER
    let k = 0
    for (let i = 0; i < src.length; ++i)
    {
        const P = src[i]
        const l = typeof P.line == 'number' ? lines[P.line] : null
        const a = l ? 1 : 0
        const v0 = l ? l.posX : P.x, v1 = l ? l.posY : P.y, v2 = l ? l.posX2 : P.angle, v3 = l ? l.posY2 : P.h
        const v4 = l ? P.u : 0, v5 = l ? P.side : 0, v6 = l ? P.h : 0
        if (store)
        {
            vals[k] = a; vals[k + 1] = v0; vals[k + 2] = v1; vals[k + 3] = v2
            vals[k + 4] = v3; vals[k + 5] = v4; vals[k + 6] = v5; vals[k + 7] = v6
        }
        else if (vals[k] !== a ||
                 (vals[k + 1] !== v0 && !portalSame(vals[k + 1], v0)) || (vals[k + 2] !== v1 && !portalSame(vals[k + 2], v1)) ||
                 (vals[k + 3] !== v2 && !portalSame(vals[k + 3], v2)) || (vals[k + 4] !== v3 && !portalSame(vals[k + 4], v3)) ||
                 (vals[k + 5] !== v4 && !portalSame(vals[k + 5], v4)) || (vals[k + 6] !== v5 && !portalSame(vals[k + 6], v5)) ||
                 (vals[k + 7] !== v6 && !portalSame(vals[k + 7], v6)))
            return false
        k += PORTAL_VALS_PER
    }
    return true
}

// The cache numbers of src as one string (diagnostics / tests only; portalRefresh does not call it)
function portalHostKey(src, lines)
{
    let key = ''
    for (const P of src)
    {
        const l = typeof P.line == 'number' ? lines[P.line] : null
        key += l ? l.posX + ',' + l.posY + ',' + l.posX2 + ',' + l.posY2 + ',' + P.u + ',' + P.side + ',' + P.h + ';'
                 : P.x + ',' + P.y + ',' + P.angle + ',' + P.h + ';'
    }
    return key
}

// TASK-123: while frozen, portalRefresh() returns the cached list without re-validating it. Set only
// around a run of gamePhysics() steps in which no line or portal can change (a preview slice, the
// test-only calcSync / calcSyncIdle); portalFreeze(true) validates the cache once first. Returns the
// previous flag, so callers restore it in a finally block: portalFreeze(was).
let portalFrozen = false
function portalFreeze(on)
{
    const was = portalFrozen
    portalFrozen = false
    portalExitMemo.P = null
    if (on)
        portalRefresh()
    portalFrozen = !!on
    return was
}

function portalRefresh()
{
    if (portalFrozen)
        return portalCache.list
    const level = curLevel()
    const src = level && level.portals && level.portals.length ? level.portals : null
    if (!src)
    {
        if (portalCache.level !== level || portalCache.src !== null)
            portalCache = { level: level, src: null, vals: [], list: null, hosts: null }
        return null
    }
    if (portalCache.level !== level || portalCache.src !== src || !portalVals(src, level.lines, portalCache.vals, false))
    {
        const list = portalResolveAll(src, level.lines), vals = []
        portalVals(src, level.lines, vals, true)
        portalCache = { level: level, src: src, vals: vals, list: list, hosts: portalHostMap(list, level.lines) }
    }
    return portalCache.list
}

// Map host line object -> [resolved portals cut into it]; null when no portal sits on a line
function portalHostMap(list, levelLines)
{
    let hosts = null
    for (const P of list)
    {
        const l = typeof P.line == 'number' ? levelLines[P.line] : null
        if (!l)
            continue
        hosts = hosts || new Map()
        if (!hosts.has(l))
        {
            const host = []
            host.hostLine = l; host.hostX = l.posX; host.hostY = l.posY; host.hostX2 = l.posX2; host.hostY2 = l.posY2
            host.hostLen = Math.hypot(l.posX2 - l.posX, l.posY2 - l.posY)
            hosts.set(l, host)
        }
        hosts.get(l).push(P)
    }
    return hosts
}

// Host lines of the current level (Ball.collision); null = no wall portals, old code path
function portalHosts()
{
    return portalRefresh() ? portalCache.hosts : null
}

// Ball b against host line l carrying the resolved portals `list` (TASK-201: ported to the contact model of
// Ball.contactCollision, which used to be the per-line portalHostCollision): appends to `out` the solid parts
// of l the ball can touch. Every portal whose front the ball centre is on (d > 0) opens its gap u ± h/len
// and the line is solid as the remaining pieces (lineGapPieces); from behind (no open gap) the whole line
// is solid (wall portals block from behind). The rims are solid points handled in portalStep, only while
// the ball is in front of the portal (d > 0): from behind, the whole line is the only collider (TASK-164).
// For a ball moving away from the front (v·n > 0) the pieces have no gap edges (away: Ball.contacts drops a
// contact whose closest point is a gap edge, i.e. a rim): a ball that leaves the exit portal near a rim
// overlaps the rim end of the piece next to the opening without having travelled into it; that contact
// (normal along the opening) would turn it back through the exit (ping-pong teleport) or push it sideways.
// The rest of the piece stays solid (before TASK-201 the whole line was dropped, and a ball moving away
// from the plane far beside the opening slid into the host line's own end).
// Each piece is {posX, posY, posX2, posY2, hostList, endA, endC, away, open} (endA / endC: that end is an
// end of l itself, not a gap edge); Ball.contacts drops a piece contact in the capture zone of a portal that
// is capturing the ball (portalCaptureZone).
function portalHostSegs(b, l, list, out)
{
    // list.hostLen: the host line length, stored by portalHostMap when the list was built from the
    // same line coordinates (the cache re-resolves on any change), so Math.hypot is not redone
    const dx = l.posX2 - l.posX, dy = l.posY2 - l.posY
    const len = list.hostLine === l && list.hostX === l.posX && list.hostY === l.posY && list.hostX2 === l.posX2 && list.hostY2 === l.posY2
        ? list.hostLen : Math.hypot(dx, dy)
    // the first gap is kept as two numbers; arrays only when a line carries several open portals
    let gaps = null, g0 = 0, g1 = 0, nGaps = 0
    let front = null
    for (let i = 0; i < list.length; ++i)
    {
        // portalLocalD(P, b.posX, b.posY) inline, with the one frame lookup reused for `front` (TASK-124)
        const P = list[i], f = portalFrame(P)
        if (len > 0 && (b.posX - P.x) * f.nx + (b.posY - P.y) * f.ny > 0)
        {
            const lo = P.u - P.h / len, hi = P.u + P.h / len
            if (nGaps++ === 0)
            {
                g0 = lo; g1 = hi
            }
            else
                (gaps = gaps || [[g0, g1]]).push([lo, hi])
            front = front || f
        }
    }
    if (!nGaps)
    {
        out.push(portalHostPiece(l, list, dx, dy, 0, 1, false, false))
        return
    }
    const away = b.speedX * front.nx + b.speedY * front.ny > 0
    if (nGaps === 1)
    {
        // lineGapPieces([g0]) inline: [0, a] when a > 0 and [c, 1] when c < 1, if the gap is non-empty
        const a = Math.max(0, Math.min(g0, g1)), c = Math.min(1, Math.max(g0, g1))
        if (!(c > a))
            out.push(portalHostPiece(l, list, dx, dy, 0, 1, true, away))
        else
        {
            if (a > 0)
                out.push(portalHostPiece(l, list, dx, dy, 0, a, true, away))
            if (c < 1)
                out.push(portalHostPiece(l, list, dx, dy, c, 1, true, away))
        }
    }
    else
        for (const [a, c] of lineGapPieces(gaps))
            out.push(portalHostPiece(l, list, dx, dy, a, c, true, away))
}

// Piece a..c (line parameters) of host line l as a contact segment (portalHostSegs); open: the ball is in
// front of a portal on l (portalState.hostHit.open); away: the ball moves away from that front (no gap edges)
function portalHostPiece(l, list, dx, dy, a, c, open, away)
{
    return {
        posX: a === 0 ? l.posX : l.posX + a * dx, posY: a === 0 ? l.posY : l.posY + a * dy,
        posX2: c === 1 ? l.posX2 : l.posX + c * dx, posY2: c === 1 ? l.posY2 : l.posY + c * dy,
        hostList: list, endA: a === 0, endC: c === 1, open: open, away: away
    }
}

// A host piece changed the ball's velocity (vx, vy before) in this step's contact resolution
function portalHostHit(piece, vx, vy)
{
    ++portalState.hostHits
    portalState.hostHit = { step: portalState.steps + 1, line: piece.hostList[0].line, v: [vx, vy], open: piece.open }
}

// True when ball b is being captured by one of `list` and (qx, qy), a contact point of the ball on that
// portal's host line, is part of the capture (portalZoneTouch): such a contact (the piece next to the
// opening, its rim end, a host line end) does not act on the ball, which is teleported instead (TASK-074).
// end (TASK-173): (qx, qy) is an end point of the host line (see portalZoneTouch).
function portalCaptureZone(b, list, qx, qy, end)
{
    for (let i = 0; i < list.length; ++i)
    {
        // portalLocalD / portalLocalS inline on one frame lookup (TASK-124; same operations)
        const P = list[i], f = portalFrame(P), dx = b.posX - P.x, dy = b.posY - P.y
        if (portalZoneTouch(P, b, f, dx * f.nx + dy * f.ny, dx * f.tx + dy * f.ty, qx, qy, end))
            return true
    }
    return false
}

// TASK-201: capture of a ball touching portal P's host line next to the opening ('generous' edge, TASK-074),
// in the ball's contact model. Ball b (centre local d, ls in P's frame f) touches the host line at the contact
// point (qx, qy) (end: it is an end point of the host line). It is captured when
//  - it is on P's front (d > 0) moving toward it (v·n < 0),
//  - (qx, qy) lies within h + ball.radius of P's centre along t (TASK-074's zone), and for a host line end the
//    centre within h + radius / 2 (TASK-173: a centre farther out reaches the end long before the opening),
//  - its straight path from the centre to the opening plane (d = 0) comes within ball.radius of the opening
//    c ± h·t: it would touch the opening if it went on, so the piece between is not allowed to stop it,
//  - and the touch would not be refused (portalTouchExitBlocked: a line at the exit spot; portalPathBlocked:
//    a line between the centre and the opening), so the host line stays solid where the opening is covered.
// portalStep teleports such a ball ('touch', at the step's end, the same test as Ball.contacts uses to drop the
// contact): before TASK-201 the contact was only ignored and the ball sank into the host line (up to ~r deep)
// until it touched the opening itself, or bounced from inside it when its path missed the opening.
function portalZoneTouch(P, b, f, d, ls, qx, qy, end)
{
    const vn = b.speedX * f.nx + b.speedY * f.ny
    if (!(d > 0) || !(vn < 0) || portalState.grace === P)
        return false
    const r = b.radius
    if (Math.abs((qx - P.x) * f.tx + (qy - P.y) * f.ty) > P.h + r || (end && Math.abs(ls) > P.h + 0.5 * r))
        return false
    // the centre path to the plane: c + k v, k in [0, d / -vn]; the opening c ± h t lies in the plane
    const k = d / -vn, px = b.posX + k * b.speedX, py = b.posY + k * b.speedY
    const sp = (px - P.x) * f.tx + (py - P.y) * f.ty
    if (Math.abs(sp) > P.h)
    {
        // the path ends beside the opening: its distance to the opening is the distance to the nearer rim
        // (the path lies on the front side of the plane, the rim is in it)
        const e = sp > 0 ? 1 : -1, rx = P.x + e * P.h * f.tx, ry = P.y + e * P.h * f.ty
        if (pointSegDist(rx, ry, b.posX, b.posY, px, py) > r)
            return false
    }
    if (portalTouchExitBlocked(P, b, f))
        return false
    const s = Math.max(-P.h, Math.min(P.h, ls))
    return !(portalPathBlocked(b.posX, b.posY, P.x + s * f.tx, P.y + s * f.ty, P) < Infinity)
}

// portalStep's capture through the host line (portalZoneTouch): ball b touches P's host line (the closest point
// within ball.radius, the contact model's test) where the capture applies
function portalHostTouchAt(P, b, f, d, ls)
{
    const l = typeof P.line == 'number' ? curLevel().lines[P.line] : null
    if (!l || !(d > 0) || !(d < b.radius + CONTACT_SLOP))
        return false
    const ex = l.posX2 - l.posX, ey = l.posY2 - l.posY, L2 = ex * ex + ey * ey
    const k = L2 > 0 ? Math.max(0, Math.min(1, ((b.posX - l.posX) * ex + (b.posY - l.posY) * ey) / L2)) : 0
    const qx = l.posX + k * ex, qy = l.posY + k * ey
    if (!(Math.hypot(b.posX - qx, b.posY - qy) < b.radius + CONTACT_SLOP))
        return false
    return portalZoneTouch(P, b, f, d, ls, qx, qy, k === 0 || k === 1)
}

// TASK-124: the last portalTouchExitBlocked result while portalFrozen (cleared by portalFreeze). Its inputs
// are P, the partner, the lines (all fixed while frozen) and the ball centre, which is compared exactly.
const portalExitMemo = { P: null, x: 0, y: 0, r: false }

// TASK-104: true when a touch teleport of ball b through portal P right now would be refused because a
// line lies between the partner's exit opening point and the exit centre (as in portalTeleport). Such
// a spot of the opening is blocked, so it gets no capture zone: the host line's pieces and ends next to
// it stay solid (a ball let deep into a line end there and then refused would be thrown back and forth
// by that end every step). Only called for contacts (portalCaptureZone).
function portalTouchExitBlocked(P, b, fp)
{
    const memo = portalExitMemo
    if (portalFrozen && memo.P === P && memo.x === b.posX && memo.y === b.posY)
        return memo.r
    const list = currentPortals()
    const i = list ? list.indexOf(P) : -1, Q = i >= 0 ? list[i ^ 1] : null
    let r = false
    if (Q)
    {
        // portalLocalS / portalLocalD(P, b.posX, b.posY) inline (fp: P's frame when the caller has it)
        const f = fp || portalFrame(P), dx = b.posX - P.x, dy = b.posY - P.y
        const fq = portalFrame(Q), se = Math.max(-Q.h, Math.min(Q.h, dx * f.tx + dy * f.ty))
        const de = Math.max(dx * f.nx + dy * f.ny, PORTAL_EXIT_MIN_D)
        const ox = Q.x - se * fq.tx, oy = Q.y - se * fq.ty
        // TASK-173: also refused when a ball centre anywhere on the exit segment O + [MIN_D, radius] * n
        // would overlap a line (portalTeleport's TASK-172 'overlap' reason, for every exit depth a touch
        // can produce). The verdict does not depend on the ball's current depth d, so it cannot flip
        // while a captured ball penetrates the plane (which used to drop the capture inside a line end).
        r = portalPathBlocked(ox, oy, ox + de * fq.nx, oy + de * fq.ny, Q) < Infinity ||
            portalExitSweepOverlaps(ox, oy, fq.nx, fq.ny, Q)
    }
    if (portalFrozen)
    {
        memo.P = P; memo.x = b.posX; memo.y = b.posY; memo.r = r
    }
    return r
}

function segClosestPoint(px, py, x1, y1, x2, y2)
{
    const dx = x2 - x1, dy = y2 - y1, L2 = dx * dx + dy * dy
    const k = L2 > 0 ? Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / L2)) : 0
    return [x1 + k * dx, y1 + k * dy]
}

// Ball b touches portal P's opening from its front while moving toward it (capture by touch)
function portalTouches(P, b)
{
    const f = portalFrame(P), dx = b.posX - P.x, dy = b.posY - P.y
    return portalTouchesAt(P, b, f, dx * f.nx + dy * f.ny, dx * f.tx + dy * f.ty)
}

// portalTouches with P's frame f and the ball centre's local d / s already computed (portalStep)
function portalTouchesAt(P, b, f, d, ls)
{
    if (!(d > 0) || !(b.speedX * f.nx + b.speedY * f.ny < 0))
        return false
    // portalRims(P) inline; a centre more than radius + 1 outside the opening's bounding box is
    // farther than radius from it, so pointSegDist (Math.hypot) is skipped there
    const x1 = P.x + P.h * f.tx, y1 = P.y + P.h * f.ty, x2 = P.x - P.h * f.tx, y2 = P.y - P.h * f.ty
    const m = b.radius + 1
    if (b.posX < Math.min(x1, x2) - m || b.posX > Math.max(x1, x2) + m || b.posY < Math.min(y1, y2) - m || b.posY > Math.max(y1, y2) + m)
        return false
    if (pointSegDist(b.posX, b.posY, x1, y1, x2, y2) > b.radius)
        return false
    // TASK-104: a level / player line between the centre and the opening point it touches blocks the
    // capture (the line stays solid across an opening; rare: only a ball overlapping such a line)
    const s = Math.max(-P.h, Math.min(P.h, ls))
    return !(portalPathBlocked(b.posX, b.posY, P.x + s * f.tx, P.y + s * f.ty, P) < Infinity)
}

// TASK-104: smallest fraction k in [0, 1] at which the path (x0, y0) -> (x1, y1) meets a line of
// the play field other than portal P's host line (Infinity: none). Used on a touch capture's entry
// path (centre -> touched opening point) and a teleport's exit path (exit opening point -> exit
// centre) only, so a line crossing an opening stays solid there too.
// Lines outside the path's bounding box are skipped.
function portalPathBlocked(x0, y0, x1, y1, P)
{
    const host = typeof P.line == 'number' ? curLevel().lines[P.line] : null
    const ex = x1 - x0, ey = y1 - y0
    const bx0 = Math.min(x0, x1), bx1 = Math.max(x0, x1), by0 = Math.min(y0, y1), by1 = Math.max(y0, y1)
    let best = Infinity
    for (let i = 0; i < lines.length; ++i)
    {
        const l = lines[i]
        if (l === host || Math.max(l.posX, l.posX2) < bx0 || Math.min(l.posX, l.posX2) > bx1 ||
            Math.max(l.posY, l.posY2) < by0 || Math.min(l.posY, l.posY2) > by1)
            continue
        const fx = l.posX2 - l.posX, fy = l.posY2 - l.posY, den = ex * fy - ey * fx
        if (den === 0)
            continue
        const qx = l.posX - x0, qy = l.posY - y0
        const k = (qx * fy - qy * fx) / den, m = (qx * ey - qy * ex) / den
        if (k >= 0 && k <= 1 && m >= 0 && m <= 1 && k < best)
            best = k
    }
    return best
}

// TASK-172: true when a ball centred at (x, y) would overlap a line of the play field other than
// portal P's host line (point-segment distance below the ball radius). Lines farther than the radius
// from (x, y) along either axis are skipped.
function portalExitOverlaps(x, y, P)
{
    const host = typeof P.line == 'number' ? curLevel().lines[P.line] : null
    const r = ball.radius
    for (let i = 0; i < lines.length; ++i)
    {
        const l = lines[i]
        if (l === host || Math.max(l.posX, l.posX2) <= x - r || Math.min(l.posX, l.posX2) >= x + r ||
            Math.max(l.posY, l.posY2) <= y - r || Math.min(l.posY, l.posY2) >= y + r)
            continue
        if (pointSegDist(x, y, l.posX, l.posY, l.posX2, l.posY2) < r)
            return true
    }
    return false
}

// TASK-173: true when a ball centred anywhere on the segment O + k * n, k in [PORTAL_EXIT_MIN_D, ball.radius]
// (the touch-teleport exit centres in front of portal P's opening point O), would overlap a line of the
// play field other than P's host line: segment-segment distance below the ball radius.
function portalExitSweepOverlaps(ox, oy, nx, ny, P)
{
    const host = typeof P.line == 'number' ? curLevel().lines[P.line] : null
    const r = ball.radius
    const x0 = ox + PORTAL_EXIT_MIN_D * nx, y0 = oy + PORTAL_EXIT_MIN_D * ny, x1 = ox + r * nx, y1 = oy + r * ny
    const bx0 = Math.min(x0, x1) - r, bx1 = Math.max(x0, x1) + r, by0 = Math.min(y0, y1) - r, by1 = Math.max(y0, y1) + r
    const ex = x1 - x0, ey = y1 - y0
    for (let i = 0; i < lines.length; ++i)
    {
        const l = lines[i]
        if (l === host || Math.max(l.posX, l.posX2) <= bx0 || Math.min(l.posX, l.posX2) >= bx1 ||
            Math.max(l.posY, l.posY2) <= by0 || Math.min(l.posY, l.posY2) >= by1)
            continue
        // the two segments intersect: distance 0
        const fx = l.posX2 - l.posX, fy = l.posY2 - l.posY, den = ex * fy - ey * fx
        if (den !== 0)
        {
            const qx = l.posX - x0, qy = l.posY - y0
            const k = (qx * fy - qy * fx) / den, m = (qx * ey - qy * ex) / den
            if (k >= 0 && k <= 1 && m >= 0 && m <= 1)
                return true
        }
        if (pointSegDist(x0, y0, l.posX, l.posY, l.posX2, l.posY2) < r || pointSegDist(x1, y1, l.posX, l.posY, l.posX2, l.posY2) < r ||
            pointSegDist(l.posX, l.posY, x0, y0, x1, y1) < r || pointSegDist(l.posX2, l.posY2, x0, y0, x1, y1) < r)
            return true
    }
    return false
}

function currentPortals()
{
    return portalRefresh()
}

function portalFrameOf(angle)
{
    const nx = Math.cos(angle), ny = Math.sin(angle)
    return { nx: nx, ny: ny, tx: -ny, ty: nx, angle: angle }
}

// Callers only read nx, ny, tx, ty
function portalFrame(P)
{
    const f = P.frame
    return f !== undefined && f.angle === P.angle ? f : portalFrameOf(P.angle)
}

function portalLocal(P, x, y)
{
    const f = portalFrame(P), dx = x - P.x, dy = y - P.y
    return { s: dx * f.tx + dy * f.ty, d: dx * f.nx + dy * f.ny }
}

// portalLocal(P, x, y).d / .s without the result object
function portalLocalD(P, x, y)
{
    const f = portalFrame(P), dx = x - P.x, dy = y - P.y
    return dx * f.nx + dy * f.ny
}

function portalLocalS(P, x, y)
{
    const f = portalFrame(P), dx = x - P.x, dy = y - P.y
    return dx * f.tx + dy * f.ty
}

// kind 'touch': local (s, d) -> (-clamp(s, -h, h), max(d, PORTAL_EXIT_MIN_D)) at the exit (in front of it);
// kind 'cross': (s, d) -> (-s, -d)
function portalTeleport(A, B, s, d, kind)
{
    const fb = portalFrame(B)
    const a = B.angle - A.angle + Math.PI, c = Math.cos(a), sn = Math.sin(a)
    const vx = ball.speedX, vy = ball.speedY
    const record = {
        step: portalState.steps, from: A.name, to: B.name, s: s, d: d, kind: kind,
        before: [ball.posX, ball.posY, vx, vy],
        speedBefore: Math.hypot(vx, vy)
    }
    const se = kind === 'touch' ? Math.max(-B.h, Math.min(B.h, s)) : s
    // touch: never exactly on the exit plane (a rounded d = 0 would count as 'behind' the exit's host line)
    const de = kind === 'touch' ? -Math.max(d, PORTAL_EXIT_MIN_D) : d
    const ox = B.x - se * fb.tx, oy = B.y - se * fb.ty, ex = ox - de * fb.nx, ey = oy - de * fb.ny
    // TASK-104: lines may cross an opening and stay solid there. When a line other than B's host line
    // lies between the exit opening point O and the exit centre (the ball would come out on the far side
    // of it), the ball does not get through at that spot: no teleport, the opening is a solid wall there
    // and the ball bounces off A's plane (velocity's normal component reversed; a 'cross' ball, already
    // up to one step behind A's plane, is mirrored back in front of it). For a line parallel to B's
    // opening this is 'teleport, bounce off the line, teleport back' in one step. (Clipping the exit to
    // the line instead left the centre on the line, where the reflect-on-overlap collision kept the ball
    // stuck.) record.reason = 'path'.
    // TASK-172: an exit centre closer than the ball radius to a line other than B's host line (the exit
    // legitimately sits PORTAL_EXIT_MIN_D in front of that one) is blocked the same way, record.reason =
    // 'overlap'. Before, such an exit teleported and the reflect-on-overlap collision could not push a
    // centre that sat on (or within r/2 of) the line back out: on level 24 the shelf starts at B's centre,
    // a ball entering A near its centre came out on the shelf and slid inside it ('stuck in textures').
    const reason = portalPathBlocked(ox, oy, ex, ey, B) < Infinity ? 'path'
                 : portalExitOverlaps(ex, ey, B) ? 'overlap' : null
    if (reason)
    {
        const fa = portalFrame(A), vn = vx * fa.nx + vy * fa.ny, E0 = ball.energy()
        record.blocked = true
        record.reason = reason
        if (kind === 'cross')
        {
            ball.posX -= 2 * d * fa.nx
            ball.posY -= 2 * d * fa.ny
        }
        if (vn < 0)
        {
            ball.speedX = vx - 2 * vn * fa.nx
            ball.speedY = vy - 2 * vn * fa.ny
            // TASK-176: a blocked 'touch' on the opening face (|s| <= h, so 0 < d <= radius) is a wall contact at
            // d = radius; mirror the centre back about it (like 'cross' about d = 0). portalStep runs after the move,
            // so without this the ball keeps the inward step it made before the bounce. Wedged between that spot and a
            // line end it overlaps (collisionWithDot flips v every step), it then crept 1 inward step per 2 steps into
            // A's plane and stayed there (fuzz --crossing --seed 2 case 1298, embedded).
            // TASK-201: also beside the opening (|s| > h, a touch through the rim or the host line's capture): the
            // centre is then inside the host piece by radius - d and the next step's push-out would lift it.
            if (kind === 'touch' && d < ball.radius)
            {
                ball.posX += 2 * (ball.radius - d) * fa.nx
                ball.posY += 2 * (ball.radius - d) * fa.ny
                record.mirror = true
            }
            // TASK-201: like a contact of the ball's contact model, the bounce never adds energy (the reflection
            // changes the integrator's g vy / 2 term, the mirror the height)
            ball.limitEnergy(E0, fa.nx, fa.ny)
        }
        record.after = [ball.posX, ball.posY, ball.speedX, ball.speedY]
        ++portalState.blockedExits
        if (portalState.blocked.length < RIM_LOG_MAX)
            portalState.blocked.push(record)
        return false
    }
    ball.posX = ex
    ball.posY = ey
    ball.speedX = vx * c - vy * sn
    ball.speedY = vx * sn + vy * c
    record.after = [ball.posX, ball.posY, ball.speedX, ball.speedY]
    record.speedAfter = Math.hypot(ball.speedX, ball.speedY)
    portalState.teleports.push(record)
    return true
}

function portalRims(P)
{
    const f = portalFrame(P)
    return [[P.x + P.h * f.tx, P.y + P.h * f.ty], [P.x - P.h * f.tx, P.y - P.h * f.ty]]
}

// Point-segment distance. Player and level lines may cross portal openings (TASK-105/106):
// the line stays solid, see portalTouches / portalTeleport.
function pointSegDist(px, py, x1, y1, x2, y2)
{
    const dx = x2 - x1, dy = y2 - y1, L2 = dx * dx + dy * dy
    let k = L2 > 0 ? ((px - x1) * dx + (py - y1) * dy) / L2 : 0
    k = Math.max(0, Math.min(1, k))
    return Math.hypot(px - (x1 + k * dx), py - (y1 + k * dy))
}

function portalStep()
{
    const P = currentPortals()
    if (!P)
        return
    ++portalState.steps
    // exit grace: ends once the ball centre is farther than the radius from that portal's opening
    const G = portalState.grace
    if (G !== null)
    {
        const f = portalFrame(G)
        if (P.indexOf(G) < 0 || pointSegDist(ball.posX, ball.posY, G.x + G.h * f.tx, G.y + G.h * f.ty, G.x - G.h * f.tx, G.y - G.h * f.ty) > ball.radius)
            portalState.grace = null
    }
    for (let i = 0; i < P.length; ++i)
    {
        // portalLocalD / portalLocalS inline on one frame lookup, shared with portalTouchesAt (TASK-124)
        const Pi = P[i], f = portalFrame(Pi), dx = ball.posX - Pi.x, dy = ball.posY - Pi.y
        const Ld = dx * f.nx + dy * f.ny, Ls = dx * f.tx + dy * f.ty
        const prev = portalState.prevD[i]
        portalState.prevD[i] = Ld
        // wall portal: front -> back only; legacy free-standing portal: either direction
        const crossed = (prev > 0 && Ld <= 0) || (typeof P[i].line != 'number' && prev < 0 && Ld >= 0)
        // touch: the opening itself, or (TASK-201) the host line where the capture applies (portalHostTouchAt)
        const kind = !P[i ^ 1] ? null
                   : portalState.grace !== Pi && (portalTouchesAt(Pi, ball, f, Ld, Ls) || portalHostTouchAt(Pi, ball, f, Ld, Ls)) ? 'touch'
                   : crossed && Math.abs(Ls) <= P[i].h ? 'cross' : null
        if (kind)
        {
            if (portalTeleport(P[i], P[i ^ 1], Ls, Ld, kind))
                portalState.grace = P[i ^ 1]
            // at most one teleport (or blocked-exit bounce, TASK-104) per step; every stored side
            // (the exit's included) becomes the ball's new side, so the exit cannot re-trigger next step
            for (let k = 0; k < P.length; ++k)
                portalState.prevD[k] = portalLocalD(P[k], ball.posX, ball.posY)
            break
        }
    }
    // rims: solid points, reflect about the contact normal when moving towards them.
    // A wall portal's rims lie on its host line, which is solid as a whole while the ball centre
    // is behind the portal (d <= 0, portalHostSegs): there the rims are skipped, otherwise a
    // ball resting on the back of the line is reflected twice per step (line + rim point, normals
    // a few degrees apart), its velocity turns along the line and it shuttles between the two
    // rims forever (TASK-163/164 rim trap). Legacy free-standing portals keep rims on both sides.
    for (let i = 0; i < P.length; ++i)
    {
        const Q = P[i], f = portalFrame(Q)
        if (typeof Q.line == 'number' && (ball.posX - Q.x) * f.nx + (ball.posY - Q.y) * f.ny <= 0)
            continue
        for (let k = 0; k < 2; ++k)
        {
            // portalRims(Q)[k] inline
            const rx = k === 0 ? Q.x + Q.h * f.tx : Q.x - Q.h * f.tx, ry = k === 0 ? Q.y + Q.h * f.ty : Q.y - Q.h * f.ty
            const dx = ball.posX - rx, dy = ball.posY - ry
            // Math.hypot(dx, dy) >= max(|dx|, |dy|): no contact, skip the hypot
            if (Math.abs(dx) >= ball.radius || Math.abs(dy) >= ball.radius)
                continue
            const dist = Math.hypot(dx, dy)
            if (dist >= ball.radius || dist === 0)
                continue
            const nx = dx / dist, ny = dy / dist
            const vn = ball.speedX * nx + ball.speedY * ny
            if (vn >= 0)
                continue
            const before = [ball.speedX, ball.speedY]
            ball.speedX -= 2 * vn * nx
            ball.speedY -= 2 * vn * ny
            ++portalState.rimHits
            if (portalState.rims.length < RIM_LOG_MAX)
                portalState.rims.push({ step: portalState.steps, rim: [rx, ry], n: [nx, ny],
                    before: before, after: [ball.speedX, ball.speedY] })
        }
    }
}

// ---- Portal rendering (concept artifacts/concepts/72-portals-rings-orangepurple.png, 'rings') ----
// Purely visual; no state is changed. Levels without portals draw nothing here and the ball
// is drawn by the unchanged ball.draw() path.
const PORTAL_STYLE = [
    { label: 'portal A', color: '#ff9a2e', glow: 'rgba(255,154,46,.9)' },
    { label: 'portal B', color: '#b46cff', glow: 'rgba(180,108,255,.95)' }
]
const PORTAL_RING = { rx: 4, ry: 7, outerRx: 11, outerRy: 11, arrowFrom: 8, arrowLen: 16, arrowHead: 6 }

// Screen bounding box of a portal drawing (outer ring + front arrow): [x0, y0, x1, y1]
function portalBounds(P)
{
    const f = portalFrame(P), a = P.angle + Math.PI / 2, c = Math.cos(a), s = Math.sin(a)
    const rx = P.h + PORTAL_RING.outerRx, ry = PORTAL_RING.outerRy
    const wx = Math.hypot(rx * c, ry * s), wy = Math.hypot(rx * s, ry * c)
    let x0 = P.x - wx, x1 = P.x + wx, y0 = P.y - wy, y1 = P.y + wy
    const tip = PORTAL_RING.arrowFrom + PORTAL_RING.arrowLen
    const ax = P.x + f.nx * tip, ay = P.y + f.ny * tip, hs = PORTAL_RING.arrowHead / 2
    x0 = Math.min(x0, ax - hs); x1 = Math.max(x1, ax + hs)
    y0 = Math.min(y0, ay - hs); y1 = Math.max(y1, ay + hs)
    return [x0, y0, x1, y1]
}

// Label anchor: centred above the bounding box, alphabetic baseline 18 px above its top
function portalLabelPos(P)
{
    const b = portalBounds(P)
    return { x: (b[0] + b[2]) / 2, y: b[1] - 18 }
}

function drawPortal(P, st)
{
    const f = portalFrame(P), rot = P.angle + Math.PI / 2
    const rx = P.h + PORTAL_RING.rx, ry = PORTAL_RING.ry
    ctx.save()
    // hatched half-ellipse on the back side (-n)
    hatch(ctx, () => {
        ctx.beginPath(); ctx.ellipse(P.x, P.y, rx, ry, rot, 0, Math.PI); ctx.closePath()
    }, P.x - rx, P.y - rx, rx * 2, rx * 2, P.angle + Math.PI / 4, 3, st.color, 1, .7)
    // fainter outer ring
    ctx.globalAlpha = .45; ctx.strokeStyle = st.color; ctx.lineWidth = 1.2
    ctx.beginPath(); ctx.ellipse(P.x, P.y, P.h + PORTAL_RING.outerRx, PORTAL_RING.outerRy, rot, 0, Math.PI * 2); ctx.stroke()
    // glowing main ring
    ctx.globalAlpha = 1; ctx.lineWidth = 2.4; ctx.shadowColor = st.glow; ctx.shadowBlur = 12
    ctx.beginPath(); ctx.ellipse(P.x, P.y, rx, ry, rot, 0, Math.PI * 2); ctx.stroke()
    // small arrow on the front normal
    const a0 = PORTAL_RING.arrowFrom, a1 = a0 + PORTAL_RING.arrowLen
    ctx.shadowBlur = 6; ctx.lineWidth = 1.6; ctx.lineCap = 'round'
    ctx.beginPath(); ctx.moveTo(P.x + f.nx * a0, P.y + f.ny * a0)
    ctx.lineTo(P.x + f.nx * (a1 - 2), P.y + f.ny * (a1 - 2)); ctx.stroke()
    arrowHead(ctx, P.x + f.nx * a1, P.y + f.ny * a1, P.angle, PORTAL_RING.arrowHead, st.color)
    // handwritten label above the bounding box
    const lp = portalLabelPos(P)
    ctx.shadowBlur = 8; ctx.fillStyle = st.color
    ctx.font = '24px ' + THEME.fontStack; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'
    ctx.fillText(st.label, lp.x, lp.y)
    ctx.restore()
}

// list: portals to draw (the editor's working copy); default = the current level's
function drawPortals(list)
{
    const P = list === undefined ? currentPortals() : (list.length ? list : null)
    if (!P)
        return
    if (P.length >= 2)
    {
        // faint dashed link curve between the pair, bowed to one side of the chord
        const mx = (P[0].x + P[1].x) / 2, my = (P[0].y + P[1].y) / 2
        const dx = P[1].x - P[0].x, dy = P[1].y - P[0].y, L = Math.hypot(dx, dy) || 1
        const bow = Math.min(120, L * .25), sgn = dx >= 0 ? 1 : -1
        ctx.save()
        ctx.globalAlpha = .35; ctx.strokeStyle = THEME.soft; ctx.lineWidth = 1.2; ctx.setLineDash([4, 6])
        ctx.beginPath(); ctx.moveTo(P[0].x, P[0].y)
        ctx.quadraticCurveTo(mx + sgn * dy / L * bow, my - sgn * dx / L * bow, P[1].x, P[1].y)
        ctx.stroke()
        ctx.restore()
    }
    for (let i = 0; i < P.length; ++i)
        drawPortal(P[i], PORTAL_STYLE[i % 2])
}

// Clip to the half-plane on side `side` (+1 front, -1 back) of portal P's plane
function clipPortalSide(P, side)
{
    const f = portalFrame(P), B = 4000
    ctx.beginPath()
    ctx.moveTo(P.x + f.tx * B, P.y + f.ty * B)
    ctx.lineTo(P.x - f.tx * B, P.y - f.ty * B)
    ctx.lineTo(P.x - f.tx * B + side * f.nx * B, P.y - f.ty * B + side * f.ny * B)
    ctx.lineTo(P.x + f.tx * B + side * f.nx * B, P.y + f.ty * B + side * f.ny * B)
    ctx.closePath()
    ctx.clip()
}

// Split ball: while the centre is within ball.radius of a portal plane (|d| < r, |s| <= h)
// the part on the centre's side is drawn at that portal and the part past the plane is drawn
// at the partner (teleport map (s, d) -> (-s, -d)), clipped to the partner's same-sign side,
// which is exactly the image of the far side. At the teleport step the two halves swap
// roles, so the picture is continuous. Returns false (ball not drawn) when no portal is near.
function drawPortalBall()
{
    const P = currentPortals()
    if (!P || P.length < 2)
        return false
    const r = ball.radius
    for (let i = 0; i < P.length; ++i)
    {
        const L = portalLocal(P[i], ball.posX, ball.posY)
        if (!(Math.abs(L.d) < r && Math.abs(L.s) <= P[i].h))
            continue
        const Q = P[i ^ 1], fq = portalFrame(Q), side = L.d >= 0 ? 1 : -1
        ctx.save(); clipPortalSide(P[i], side); ball.draw(); ctx.restore()
        const mapped = { posX: Q.x - L.s * fq.tx - L.d * fq.nx, posY: Q.y - L.s * fq.ty - L.d * fq.ny, radius: r }
        ctx.save(); clipPortalSide(Q, side); Ball.prototype.draw.call(mapped); ctx.restore()
        return true
    }
    return false
}

// Test API (tests/portal/sim.py)
window.__portalTest = {
    setup(cfg)
    {
        physics = false
        levelStarted = false
        levelCompletedWindow = false
        line = false
        linesK = 0
        // cfg.wall: portals are wall portals {line, u, side} on cfg.lines, installed as a
        // scratch play-test level (curLevel()) so the real levels stay untouched
        playtestLevel = null
        const mk = l => new Line(l[0], l[1], l[2], l[3], dotRadius, levelLineColor, 'line')
        const b = cfg.ball || {}
        // the scratch level starts the ball where the test puts it, so restart() / levelChoosed() work on it
        const level = cfg.wall ? { lines: (cfg.lines || []).map(mk), lineK: cfg.lineK || 0, flagX: -1e6, flagY: -1e6, flagRotate: 0,
                                   ballX: b.x, ballY: b.y } : levels[thisLevel]
        level.portals = (cfg.portals || []).map(p => Object.assign({ h: PORTAL_DEFAULT_H }, p))
        if (!level.portals.length)
            delete level.portals
        if (cfg.wall)
            playtestLevel = level
        lines = cfg.wall ? level.lines.slice() : (cfg.lines || []).map(mk)
        ball.posX = b.x; ball.posY = b.y
        ball.speedX = b.vx || 0; ball.speedY = b.vy || 0
        ball.radius = b.r !== undefined ? b.r : 10
        portalReset()
        return this.state()
    },
    step(n)
    {
        for (let i = 0; i < n; ++i)
            gamePhysics()
        return this.state()
    },
    state()
    {
        return {
            x: ball.posX, y: ball.posY, vx: ball.speedX, vy: ball.speedY, r: ball.radius,
            steps: portalState.steps, rimHits: portalState.rimHits,
            teleports: portalState.teleports, rims: portalState.rims,
            hostHits: portalState.hostHits, hostHit: portalState.hostHit
        }
    }
}
