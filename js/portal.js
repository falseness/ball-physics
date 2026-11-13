// Portal physics core.
//
// levels[i].portals = [A, B] (optional): each {x, y, angle, h, name, color}.
// Front normal n = (cos angle, sin angle), tangent t = (-n.y, n.x); the opening is the
// segment c ± h·t. For the ball centre p: d = (p - c)·n (signed distance), s = (p - c)·t.
// A crossing = d changed sign since the previous step (either side) while |s| <= h.
// Teleport = rotation by (angleExit - angleEntry + PI): local (s, d) at the entry maps to
// (-s, -d) at the exit and the velocity is rotated by the same angle, so entering a
// front leaves through the other portal's front, a back leaves through its back.
// The rims (c ± h·t) are solid points; the portal body is not a collider.

// rims: the first RIM_LOG_MAX rim bounces {step, rim, n, before:[vx,vy], after:[vx,vy]}
const RIM_LOG_MAX = 64
let portalState = { prevD: [], teleports: [], rimHits: 0, rims: [], steps: 0 }

function portalReset()
{
    portalState = { prevD: [], teleports: [], rimHits: 0, rims: [], steps: 0 }
}

// The path preview (Bounce.calc) runs gamePhysics() too: it must start from the same portal
// state as the real run and must not leave its own state (stored sides, teleport log) behind.
function portalSave()
{
    const saved = portalState
    portalState = {
        prevD: saved.prevD.slice(), teleports: saved.teleports.slice(),
        rimHits: saved.rimHits, rims: saved.rims.slice(), steps: saved.steps
    }
    return saved
}

function portalRestore(saved)
{
    portalState = saved
}

function currentPortals()
{
    const level = levels[thisLevel]
    return level && level.portals && level.portals.length ? level.portals : null
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
        const crossed = (prev > 0 && L.d <= 0) || (prev < 0 && L.d >= 0)
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

// Test API (tests/portal/sim.py)
window.__portalTest = {
    setup(cfg)
    {
        physics = false
        levelStarted = false
        levelCompletedWindow = false
        line = false
        linesK = 0
        const level = levels[thisLevel]
        level.portals = (cfg.portals || []).map(p => Object.assign({ h: 45 }, p))
        if (!level.portals.length)
            delete level.portals
        lines = (cfg.lines || []).map(l => new Line(l[0], l[1], l[2], l[3], dotRadius, levelLineColor, 'line'))
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
            teleports: portalState.teleports, rims: portalState.rims
        }
    }
}
