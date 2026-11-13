// Portal physics core.
//
// levels[i].portals = [A, B] (optional): wall portals {line, u, side, h, name} on the level's own
// lines (see portalResolve); currentPortals() returns them resolved to {x, y, angle, h, ...}.
// Front normal n = (cos angle, sin angle), tangent t = (-n.y, n.x); the opening is the
// segment c ± h·t. For the ball centre p: d = (p - c)·n (signed distance), s = (p - c)·t.
// A crossing (wall portal, numeric `line`) = d went from > 0 to <= 0 since the previous step
// (front to back only) while |s| <= h; a legacy free-standing portal (no `line`, test setups)
// still teleports on a crossing in either direction.
// Teleport = rotation by (angleExit - angleEntry + PI): local (s, d) at the entry maps to
// (-s, -d) at the exit and the velocity is rotated by the same angle, so entering a
// front leaves through the other portal's front, a back leaves through its back.
// The rims (c ± h·t) are solid points; the portal body is not a collider. A wall portal's host
// line collides as the pieces outside the opening while the ball centre is in front of the
// portal (d > 0) and as the whole line from behind (portalHostCollision).

// rims: the first RIM_LOG_MAX rim bounces {step, rim, n, before:[vx,vy], after:[vx,vy]}
// hostHits: host-line collisions so far; hostHit: the latest {step, line, v: [vx, vy] before}
const RIM_LOG_MAX = 64
let portalState = { prevD: [], teleports: [], rimHits: 0, rims: [], steps: 0, hostHits: 0, hostHit: null }

function portalReset()
{
    portalState = { prevD: [], teleports: [], rimHits: 0, rims: [], steps: 0, hostHits: 0, hostHit: null }
}

// The path preview (Bounce.calc) runs gamePhysics() too: it must start from the same portal
// state as the real run and must not leave its own state (stored sides, teleport log) behind.
function portalSave()
{
    const saved = portalState
    portalState = {
        prevD: saved.prevD.slice(), teleports: saved.teleports.slice(),
        rimHits: saved.rimHits, rims: saved.rims.slice(), steps: saved.steps,
        hostHits: saved.hostHits, hostHit: saved.hostHit
    }
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
        return Object.assign({}, P)
    const l = lines[P.line]
    const dx = l.posX2 - l.posX, dy = l.posY2 - l.posY, len = Math.hypot(dx, dy)
    const tx = len > 0 ? dx / len : 1, ty = len > 0 ? dy / len : 0
    const side = P.side < 0 ? -1 : 1, u = portalClampU(P.u, len, P.h)
    return {
        x: l.posX + u * dx, y: l.posY + u * dy, angle: Math.atan2(side * tx, side * -ty),
        h: P.h, name: P.name, line: P.line, u: u, side: side
    }
}

function portalResolveAll(list, lines)
{
    return (list || []).map(P => portalResolve(P, lines))
}

// Resolved portals of the current level, cached per level object, portal list and host line
// coordinates: levelChoosed() refreshes it and any change to a host line re-resolves it.
let portalCache = { level: null, src: null, key: '', list: null, hosts: null }

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

function portalRefresh()
{
    const level = curLevel()
    const src = level && level.portals && level.portals.length ? level.portals : null
    if (!src)
    {
        portalCache = { level: level, src: null, key: '', list: null, hosts: null }
        return null
    }
    const key = portalHostKey(src, level.lines)
    if (portalCache.level !== level || portalCache.src !== src || portalCache.key !== key)
    {
        const list = portalResolveAll(src, level.lines)
        portalCache = { level: level, src: src, key: key, list: list, hosts: portalHostMap(list, level.lines) }
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
            hosts.set(l, [])
        hosts.get(l).push(P)
    }
    return hosts
}

// Host lines of the current level (Ball.collision); null = no wall portals, old code path
function portalHosts()
{
    return portalRefresh() ? portalCache.hosts : null
}

// Ball b against host line l carrying the resolved portals `list`: every portal whose front
// the ball centre is on (d > 0) opens its gap u ± h/len, the line collides as the remaining
// pieces (lineGapPieces); from behind (no open gap) the whole line collides. The rims are
// solid points handled in portalStep.
// The pieces only reflect a ball that is not moving away from the front (v·n <= 0): a ball that
// leaves the exit portal near a rim overlaps the piece next to the opening without having
// travelled into it, and the original reflect-on-overlap code would send it straight back
// through the exit (ping-pong teleport). A normal bounce never overlaps a line while moving away,
// so for it the pieces behave exactly like the plain line.
function portalHostCollision(b, l, list)
{
    const dx = l.posX2 - l.posX, dy = l.posY2 - l.posY, len = Math.hypot(dx, dy)
    const gaps = []
    let front = null
    for (const P of list)
        if (len > 0 && portalLocal(P, b.posX, b.posY).d > 0)
        {
            gaps.push([P.u - P.h / len, P.u + P.h / len])
            front = front || portalFrame(P)
        }
    const vx = b.speedX, vy = b.speedY
    let hit = false
    if (!gaps.length)
        hit = b.collisionWithSegment(l.posX, l.posY, l.posX2, l.posY2)
    else if (vx * front.nx + vy * front.ny <= 0)
        for (const [a, c] of lineGapPieces(gaps))
        {
            const x1 = a === 0 ? l.posX : l.posX + a * dx, y1 = a === 0 ? l.posY : l.posY + a * dy
            const x2 = c === 1 ? l.posX2 : l.posX + c * dx, y2 = c === 1 ? l.posY2 : l.posY + c * dy
            if (b.collisionWithSegment(x1, y1, x2, y2))
                hit = true
        }
    if (hit)
    {
        ++portalState.hostHits
        portalState.hostHit = { step: portalState.steps + 1, line: list[0].line, v: [vx, vy], open: gaps.length > 0 }
    }
}

function currentPortals()
{
    return portalRefresh()
}

function portalFrame(P)
{
    const nx = Math.cos(P.angle), ny = Math.sin(P.angle)
    return { nx: nx, ny: ny, tx: -ny, ty: nx }
}

function portalLocal(P, x, y)
{
    const f = portalFrame(P), dx = x - P.x, dy = y - P.y
    return { s: dx * f.tx + dy * f.ty, d: dx * f.nx + dy * f.ny }
}

function portalTeleport(A, B, s, d)
{
    const fb = portalFrame(B)
    const a = B.angle - A.angle + Math.PI, c = Math.cos(a), sn = Math.sin(a)
    const vx = ball.speedX, vy = ball.speedY
    const record = {
        step: portalState.steps, from: A.name, to: B.name, s: s, d: d,
        before: [ball.posX, ball.posY, vx, vy],
        speedBefore: Math.hypot(vx, vy)
    }
    // local (s, d) -> (-s, -d) at the exit portal
    ball.posX = B.x - s * fb.tx - d * fb.nx
    ball.posY = B.y - s * fb.ty - d * fb.ny
    ball.speedX = vx * c - vy * sn
    ball.speedY = vx * sn + vy * c
    record.after = [ball.posX, ball.posY, ball.speedX, ball.speedY]
    record.speedAfter = Math.hypot(ball.speedX, ball.speedY)
    portalState.teleports.push(record)
}

function portalRims(P)
{
    const f = portalFrame(P)
    return [[P.x + P.h * f.tx, P.y + P.h * f.ty], [P.x - P.h * f.tx, P.y - P.h * f.ty]]
}

// Player lines may not touch portals (user decision): a line start within ball.radius of an
// opening segment (c ± h·t, rims included) is rejected, and so is a segment that intersects
// an opening or comes within ball.radius of it. No portals -> always false.
function pointSegDist(px, py, x1, y1, x2, y2)
{
    const dx = x2 - x1, dy = y2 - y1, L2 = dx * dx + dy * dy
    let k = L2 > 0 ? ((px - x1) * dx + (py - y1) * dy) / L2 : 0
    k = Math.max(0, Math.min(1, k))
    return Math.hypot(px - (x1 + k * dx), py - (y1 + k * dy))
}

function segSegDist(ax, ay, bx, by, cx, cy, dx, dy)
{
    const cross = (ox, oy, px, py, qx, qy) => (px - ox) * (qy - oy) - (py - oy) * (qx - ox)
    const d1 = cross(cx, cy, dx, dy, ax, ay), d2 = cross(cx, cy, dx, dy, bx, by)
    const d3 = cross(ax, ay, bx, by, cx, cy), d4 = cross(ax, ay, bx, by, dx, dy)
    if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0)))
        return 0
    return Math.min(
        pointSegDist(ax, ay, cx, cy, dx, dy), pointSegDist(bx, by, cx, cy, dx, dy),
        pointSegDist(cx, cy, ax, ay, bx, by), pointSegDist(dx, dy, ax, ay, bx, by))
}

function portalBlocksPoint(x, y)
{
    const portals = currentPortals()
    if (!portals)
        return false
    for (const P of portals)
    {
        const r = portalRims(P)
        if (pointSegDist(x, y, r[0][0], r[0][1], r[1][0], r[1][1]) <= ball.radius)
            return true
    }
    return false
}

function portalBlocksSegment(x1, y1, x2, y2)
{
    const portals = currentPortals()
    if (!portals)
        return false
    for (const P of portals)
    {
        const r = portalRims(P)
        if (segSegDist(x1, y1, x2, y2, r[0][0], r[0][1], r[1][0], r[1][1]) <= ball.radius)
            return true
    }
    return false
}

function portalStep()
{
    const P = currentPortals()
    if (!P)
        return
    ++portalState.steps
    for (let i = 0; i < P.length; ++i)
    {
        const L = portalLocal(P[i], ball.posX, ball.posY)
        const prev = portalState.prevD[i]
        portalState.prevD[i] = L.d
        // wall portal: front -> back only; legacy free-standing portal: either direction
        const crossed = (prev > 0 && L.d <= 0) || (typeof P[i].line != 'number' && prev < 0 && L.d >= 0)
        if (crossed && Math.abs(L.s) <= P[i].h && P[i ^ 1])
        {
            portalTeleport(P[i], P[i ^ 1], L.s, L.d)
            // at most one teleport per step; every stored side (the exit's included)
            // becomes the ball's new side, so the exit cannot re-trigger next step
            for (let k = 0; k < P.length; ++k)
                portalState.prevD[k] = portalLocal(P[k], ball.posX, ball.posY).d
            break
        }
    }
    // rims: solid points, reflect about the contact normal when moving towards them
    for (let i = 0; i < P.length; ++i)
    {
        const rims = portalRims(P[i])
        for (let k = 0; k < 2; ++k)
        {
            const dx = ball.posX - rims[k][0], dy = ball.posY - rims[k][1]
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
                portalState.rims.push({ step: portalState.steps, rim: rims[k], n: [nx, ny],
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
        const level = cfg.wall ? { lines: (cfg.lines || []).map(mk), lineK: 0, flagX: -1e6, flagY: -1e6 } : levels[thisLevel]
        level.portals = (cfg.portals || []).map(p => Object.assign({ h: 45 }, p))
        if (!level.portals.length)
            delete level.portals
        if (cfg.wall)
            playtestLevel = level
        lines = cfg.wall ? level.lines.slice() : (cfg.lines || []).map(mk)
        const b = cfg.ball || {}
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
