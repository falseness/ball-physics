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

let portalState = { prevD: [], teleports: [], rimHits: 0, steps: 0 }

function portalReset()
{
    portalState = { prevD: [], teleports: [], rimHits: 0, steps: 0 }
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
            ball.speedX -= 2 * vn * nx
            ball.speedY -= 2 * vn * ny
            ++portalState.rimHits
        }
    }
}

// Test API (tests/portal/sim.py)
window.__portalTest = {
    setup(cfg)
    {
        physics = false
        levelStarted = false
        const level = levels[thisLevel]
        level.portals = (cfg.portals || []).map(p => Object.assign({ h: 45 }, p))
        if (!level.portals.length)
            delete level.portals
        lines = (cfg.lines || []).map(l => new Line(l[0], l[1], l[2], l[3], dotRadius, levelLineColor, 'line'))
        const b = cfg.ball || {}
        ball.posX = b.x; ball.posY = b.y
        ball.speedX = b.vx || 0; ball.speedY = b.vy || 0
        if (b.r !== undefined)
            ball.radius = b.r
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
            teleports: portalState.teleports
        }
    }
}
