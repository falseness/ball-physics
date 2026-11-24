function collisionCircleWithLine(x1, y1, x2, y2, x0, y0, r)
{
    let k = (y1 - y2) / (x1 - x2)
    let b = y1 - k * x1
    /*
    ax^2 + bx + c = 0
    */
    let a = k * k + 1
    let c = x0 * x0 + b * b - 2 * y0 * b + y0 * y0 - r * r
    b = 2 * k * b - 2 * x0 - 2 * y0 * k
    let D = b * b - 4 * a * c
    if (D >= 0)
    {
        D = Math.sqrt(D)
        let root1 = (-b - D) / (2 * a)
        let root2 = (-b + D) / (2 * a)
        // x2 > x1
        if (root1 < x2 && x1 < root1 || 
            root2 < x2 && x1 < root2 ||
            root1 < x1 && x2 < root1 ||
            root2 < x1 && x2 < root2)
            return true
    }
    return false
}

// Contact model constants (TASK-199)
const CONTACT_ITERATIONS = 4
const CONTACT_SLOP = 1e-9        // px: a ball touching a line (distance == radius, up to rounding) is in contact
// px/step (~250 px/s, the normal speed of a ~17 px drop): a slower normal approach is a resting contact, not a
// bounce (like the restitution velocity threshold of Box2D): the ball settles instead of bouncing forever in a V.
// Rolling (normal speeds ~g) is unaffected. It sits between 0.008 (a ball sliding into the 90 degree V of
// edge_cases v_corner reaches the other wall at ~0.0079 and must not bounce back up) and 0.0087 (the lowest
// normal speed of edge_cases graze, d = 9, which must still reflect); see TASK-199.
const REST_SPEED = 0.0083

class Ball extends Sprite
{
    constructor(radius, posX, posY, speedX, speedY, color, type)
    {
        super(posX, posY, speedX, speedY, color, type)
        this.radius = radius
        this.angle = 1
    }
    // Compass-drawn circle in ice ink: hatch shading on the lower-right half, small centre cross, soft glow.
    // rng is seeded from the radius only, so the stroke is identical every frame and just travels with the ball.
    draw()
    {
        const x = this.posX, y = this.posY, r = this.radius, R = sketchRng(sketchSeed([r, 61]))
        hatch(ctx, () => { ctx.beginPath(); ctx.arc(x, y, r, -Math.PI / 4, Math.PI * 3 / 4); ctx.closePath() },
            x - r, y - r, r * 2, r * 2, -Math.PI / 4, 3.2, THEME.ink, 1, .8)
        ctx.save()
        ctx.shadowColor = 'rgba(190,230,255,0.55)'; ctx.shadowBlur = 8
        handCircle(ctx, R, x, y, r, THEME.ink, 2, 1.05)
        ctx.strokeStyle = THEME.ink; ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(x - 4, y); ctx.lineTo(x + 4, y)
        ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4)
        ctx.stroke()
        ctx.restore()
    }
    // collisionWithDot's test alone (no side effects)
    dotHit(x, y)
    {
        return Math.pow(this.posX - x, 2) + Math.pow(this.posY - y, 2) < Math.pow(this.radius, 2) - 1
    }
    collisionWithDot(x, y)
    {
        if (this.dotHit(x, y))
        {//-1 - костыль, который чинит физику при колизии при скатывании
            this.speedX *= -1
            this.speedY *= -1
            return true
        }
        return false
    }
    // Collision with the segment (x1, y1)-(x2, y2) (the original per-line code); true = it reflected
    collisionWithSegment(x1, y1, x2, y2)
    {
        let x0 = this.posX
        let y0 = this.posY
        let r = this.radius
        
        if (x1 == x2)
        {
            let root1 = y0 + Math.sqrt(Math.pow(r, 2) - Math.pow(x1 - x0, 2))
            let root2 = y0 - Math.sqrt(Math.pow(r, 2) - Math.pow(x1 - x0, 2))
            //if (Math.pow(y1 - y0, 2) + Math.pow(x1 - x0, 2) <= Math.pow(this.radius, 2) && this.speedY > 0 ||
             //  Math.pow(y2 - y0, 2) + Math.pow(x2 - x0, 2) <= Math.pow(this.radius, 2) && this.speedY < 0)
             //   this.speedY *= -1
            if (root1 < y1 && y2 < root1 ||
                    root1 < y2 && y1 < root1 ||
                    root2 < y1 && y2 < root2 ||
                    root2 < y2 && y1 < root2)
            {
                this.speedX *= -1
                return true
            }
        }
        else if (collisionCircleWithLine(x1, y1, x2, y2, x0, y0, r))
        {
            let lineAngle = Math.atan((y1 - y2) / (x1 - x2))

            let xn = -this.speedX
            let yn = -this.speedY

            let x = xn * Math.cos(lineAngle) + yn * Math.sin(lineAngle)
            let y = yn * Math.cos(lineAngle) - xn * Math.sin(lineAngle)

            x = -x

            xn = x * Math.cos(lineAngle) - y * Math.sin(lineAngle)
            yn = y * Math.cos(lineAngle) + x * Math.sin(lineAngle)

            this.speedX = xn
            this.speedY = yn
            this.speedX += gravitationalAcceleration * Math.cos(lineAngle) * Math.sin(lineAngle)
            this.speedY -= gravitationalAcceleration * Math.pow(Math.cos(lineAngle), 2)
            return true
        }
        return false
    }
    // Ball-line contacts (TASK-199), for every line that is not a wall-portal host.
    // For each line the closest point q on the segment (end points included), n = (c - q)/|c - q|; a contact is
    // |c - q| < radius (+ CONTACT_SLOP, so a ball lying exactly on a line keeps its contact).
    // 1. Velocity, from the contacts at the start of the step (normals fixed), deepest first, re-tested after each
    //    resolution, up to CONTACT_ITERATIONS:
    //    - approaching (v.n < -REST_SPEED): reflect v' = v - 2 (v.n) n, once per line per step;
    //    - resting (-REST_SPEED <= v.n <= 0, or a line already reflected this step): the normal force: v.n becomes
    //      -g.n when gravity points into the line (else 0), so after gravity() the ball neither sinks nor hops and
    //      rolls along the line; when that pushes v back into the previously resolved line (a wedge), both are
    //      solved at once (v' = v + a n1 + b n2, a, b >= 0);
    //    - moving away (v.n > 0): untouched.
    // 2. Position: the deepest overlap is pushed out to exactly radius along its n, re-tested, up to
    //    CONTACT_ITERATIONS times (two overlapping lines at once: both solved together, p' = p + a n1 + b n2).
    // 3. Energy: a contact never adds energy (E = |v|^2/2 + g vy/2 - g y, the integrator's free-flight invariant):
    //    if E grew, the outgoing normal speed along the last resolved normal is lowered until E is back at E0.
    contactCollision(segs)
    {
        const r = this.radius, g = gravitationalAcceleration, n = segs.length
        const E0 = 0.5 * (this.speedX * this.speedX + this.speedY * this.speedY) + 0.5 * g * this.speedY - g * this.posY
        // contacts at the start position: normal, distance, closest point (scratch arrays reused)
        const cn = Ball.scratch(n)
        let k = 0
        for (let i = 0; i < n; ++i)
            if (this.segContact(segs[i], cn, k))
                ++k
        if (k === 0)
            return
        // ---- 1. velocity
        let hitMask = 0, lnx = 0, lny = 0, last = -1
        for (let it = 0; it < CONTACT_ITERATIONS; ++it)
        {
            const vx = this.speedX, vy = this.speedY
            let best = -1, bd = Infinity
            for (let j = 0; j < k; ++j)
            {
                const o = j * 5
                if (cn[o + 2] < bd && vx * cn[o] + vy * cn[o + 1] <= 0)
                {
                    best = j; bd = cn[o + 2]
                }
            }
            if (best < 0)
                break
            const bnx = cn[best * 5], bny = cn[best * 5 + 1], vn = vx * bnx + vy * bny
            const bit = best < 30 ? (1 << best) : 0
            if (vn < -REST_SPEED && !(hitMask & bit))
            {
                this.speedX = vx - 2 * vn * bnx
                this.speedY = vy - 2 * vn * bny
                hitMask |= bit
            }
            else
            {
                const gn = g * bny, target = gn < 0 ? -gn : 0
                let nvx = vx + (target - vn) * bnx, nvy = vy + (target - vn) * bny
                if (last >= 0 && last !== best)
                {
                    const gp = g * lny, tp = gp < 0 ? -gp : 0
                    if (nvx * lnx + nvy * lny < tp)
                    {
                        const c = lnx * bnx + lny * bny, det = 1 - c * c
                        const r1 = tp - (vx * lnx + vy * lny), r2 = target - vn
                        const a = (r1 - c * r2) / det, b = (r2 - c * r1) / det
                        if (det > 1e-9 && a >= 0 && b >= 0)
                        {
                            nvx = vx + a * lnx + b * bnx
                            nvy = vy + a * lny + b * bny
                        }
                    }
                }
                if (nvx === vx && nvy === vy)
                    break
                this.speedX = nvx
                this.speedY = nvy
            }
            lnx = bnx; lny = bny; last = best
        }
        // ---- 2. position
        let pi = -1
        for (let it = 0; it < CONTACT_ITERATIONS; ++it)
        {
            k = 0
            let best = -1, bd = r
            for (let i = 0; i < n; ++i)
                if (this.segContact(segs[i], cn, k))
                {
                    const d = cn[k * 5 + 2]
                    if (d < bd)
                    {
                        best = k; bd = d
                    }
                    cn[(n + k) * 5] = i     // which line contact k belongs to
                    ++k
                }
            if (best < 0)
                break
            const o = best * 5, nx = cn[o], ny = cn[o + 1], seg = cn[(n + best) * 5]
            let dx = (r - bd) * nx, dy = (r - bd) * ny
            // still touching the line pushed out just before (the push into this one came from there): push out of
            // both at once, keeping that one at radius
            if (pi >= 0 && pi !== seg)
            {
                let other = -1
                for (let j = 0; j < k; ++j)
                    if (cn[(n + j) * 5] === pi)
                        other = j
                if (other >= 0)
                {
                    const ux = cn[other * 5], uy = cn[other * 5 + 1], c = ux * nx + uy * ny, det = 1 - c * c
                    const r1 = r - cn[other * 5 + 2], r2 = r - bd
                    const a = (r1 - c * r2) / det, b = (r2 - c * r1) / det
                    if (det > 1e-9 && a >= 0 && b >= 0)
                    {
                        dx = a * ux + b * nx
                        dy = a * uy + b * ny
                    }
                }
            }
            this.posX += dx
            this.posY += dy
            pi = seg
        }
        // ---- 3. energy (only after a velocity change: a ball moving away keeps its velocity, its push-out is a
        // second-order sliver)
        if (last >= 0)
        {
            const vx = this.speedX, vy = this.speedY, vn = vx * lnx + vy * lny
            const E1 = 0.5 * (vx * vx + vy * vy) + 0.5 * g * vy - g * this.posY
            if (E1 > E0 && vn > 0)
            {
                // E(w) for v = vt + w n: 0.5 w^2 + b w + C, b = g n_y / 2
                const tx = vx - vn * lnx, ty = vy - vn * lny, b = 0.5 * g * lny
                const C = 0.5 * (tx * tx + ty * ty) + 0.5 * g * ty - g * this.posY - E0
                const D = b * b - 2 * C
                let w = D > 0 ? -b + Math.sqrt(D) : 0
                if (!(w < vn)) w = vn
                if (w < 0) w = 0
                this.speedX = tx + w * lnx
                this.speedY = ty + w * lny
            }
        }
    }
    // Contact of this ball with segment l at its current position: when |c - q| < radius + CONTACT_SLOP, writes
    // [nx, ny, dist, qx, qy] at out[k * 5] and returns true
    segContact(l, out, k)
    {
        const x0 = this.posX, y0 = this.posY, x1 = l.posX, y1 = l.posY, ex = l.posX2 - x1, ey = l.posY2 - y1
        const L2 = ex * ex + ey * ey
        let t = L2 > 0 ? ((x0 - x1) * ex + (y0 - y1) * ey) / L2 : 0
        if (t < 0) t = 0; else if (t > 1) t = 1
        const qx = x1 + t * ex, qy = y1 + t * ey, dx = x0 - qx, dy = y0 - qy
        const d = Math.hypot(dx, dy)
        if (!(d < this.radius + CONTACT_SLOP))
            return false
        let nx, ny
        if (d > 1e-12)
        {
            nx = dx / d; ny = dy / d
        }
        else
        {
            // centre exactly on the line: the segment normal facing against the motion (or up)
            const L = Math.sqrt(L2) || 1
            nx = -ey / L; ny = ex / L
            if (this.speedX * nx + this.speedY * ny > 0 || (this.speedX === 0 && this.speedY === 0 && ny > 0))
            {
                nx = -nx; ny = -ny
            }
        }
        const o = k * 5
        out[o] = nx; out[o + 1] = ny; out[o + 2] = d; out[o + 3] = qx; out[o + 4] = qy
        return true
    }
    // shared scratch buffer: 5 numbers per contact + 5 per line index slot
    static scratch(n)
    {
        if (!Ball._scratch || Ball._scratch.length < (2 * n + 2) * 5)
            Ball._scratch = new Float64Array((2 * n + 8) * 5)
        return Ball._scratch
    }
    collision()
    {
        // wall-portal host lines (null when the level has none): line object -> its resolved portals
        const hosts = portalHosts()
        const segs = []
        let hostDot = false
        const m = this.radius + 1, x0 = this.posX, y0 = this.posY
        for (let i = 0; i < lines.length; ++i)
        {
            const l = lines[i]
            const host = hosts && hosts.get(l)
            // exact broadphase (TASK-122): a line cannot touch the ball when its centre lies outside the line's
            // bounding box grown by radius + 1
            if (!host)
            {
                if (x0 < (l.posX < l.posX2 ? l.posX : l.posX2) - m || x0 > (l.posX > l.posX2 ? l.posX : l.posX2) + m ||
                    y0 < (l.posY < l.posY2 ? l.posY : l.posY2) - m || y0 > (l.posY > l.posY2 ? l.posY : l.posY2) + m)
                    continue
                segs.push(l)
                continue
            }
            // portal host lines keep the original per-line code until TASK-201 (an end-point hit still ends the
            // host-line pass, as the old loop's break did):
            if (hostDot)
                continue
            // a ball being captured by a portal on this line ignores a line end next to the opening (TASK-074; true: a line end, TASK-173)
            // (dotHit first: when it is false collisionWithDot would do nothing, so the capture zone is not needed)
            if ((this.dotHit(l.posX, l.posY) && !portalCaptureZone(this, host, l.posX, l.posY, true) && this.collisionWithDot(l.posX, l.posY)) ||
                (this.dotHit(l.posX2, l.posY2) && !portalCaptureZone(this, host, l.posX2, l.posY2, true) && this.collisionWithDot(l.posX2, l.posY2)))
            {
                hostDot = true
                continue
            }
            portalHostCollision(this, l, host)
        }
        if (segs.length)
            this.contactCollision(segs)
    }
    gravity()
    {
        this.speedY += gravitationalAcceleration
    }
    physics()
    {
        this.collision()
        this.gravity()
    }
    onMap()
    {
        return !(this.posX > GAME_W || this.posX < 0 || this.posY > GAME_H || this.posY < 0)
    }
}