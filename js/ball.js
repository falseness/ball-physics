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

// Contact model constants (TASK-199, TASK-270)
// reflections per step: a ball in a narrow V can need several (about 180 / opening angle) to leave both walls
const CONTACT_ITERATIONS = 16
// position push-out passes per step
const PUSH_ITERATIONS = 4
const CONTACT_SLOP = 1e-9        // px: a ball touching a line (distance == radius, up to rounding) is in contact
// px: line end points closer than this form a joint (a chain), = dotRadius of js/line.js, the editor's snap radius
const CHAIN_JOIN = 5
// contact record in the scratch buffer: nx, ny, dist, qx, qy, line index (in segs), end (0 interior, 1 start, 2 end)
const CS = 7

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
    // Ball-line contacts (TASK-199, elastic since TASK-270), for every line; a wall-portal host line takes part as its
    // solid pieces (portalHostSegs, TASK-201: host-piece contacts a portal capture covers are dropped in contacts()).
    // For each line the closest point q on the segment (end points included), n = (c - q)/|c - q|; a contact is
    // |c - q| < radius (+ CONTACT_SLOP, so a ball lying exactly on a line keeps its contact).
    // 1. Velocity, from the contacts at the start of the step (normals fixed): every approaching contact (v.n < 0)
    //    reflects elastically, v' = v - 2 (v.n) n (tangential part kept, normal part reversed), deepest first,
    //    re-tested after each reflection, up to CONTACT_ITERATIONS (a V reflects off its walls in turn until the
    //    ball leaves both). There is no resting contact: a ball on a floor bounces back to the height it fell from,
    //    and a ball rolling on a line makes gravity-sized elastic micro-bounces (TASK-270, the user's rule: "dont
    //    loose and dont gain the energy"). Moving away (v.n >= 0): untouched. Should the iterations run out with
    //    the ball still approaching a wall, the approaching parts are removed (step 3 gives the energy back).
    // 2. Position: the deepest overlap is pushed out to exactly radius along its n, re-tested, up to
    //    PUSH_ITERATIONS times (two overlapping lines at once: both solved together, p' = p + a n1 + b n2).
    // Joints (TASK-200, ghost vertices): lines whose end points coincide within CHAIN_JOIN form chains. A contact
    // whose closest point is a joint end is ignored when its normal lies outside the cone between the outward
    // normals of the joined segments (the Box2D chain rule, https://box2d.org/posts/2020/06/ghost-collisions/),
    // i.e. when the centre projects into a joined segment that is at least as close: that segment's own contact
    // then carries the collision, so a ball sliding over a seam or into a concave joint never gets an internal normal.
    // 3. Energy: a contact neither adds nor removes energy (E = |v|^2/2 + g vy/2 - g y, the integrator's free-flight
    //    invariant). A reflection changes the g vy/2 term and a push-out changes the height, so after steps 1-2 the
    //    outgoing normal speed along the last resolved normal is set so that E equals E0 again (setEnergy).
    contactCollision(segs)
    {
        const r = this.radius, n = segs.length
        const E0 = this.energy()
        // contacts at the start position: normal, distance, closest point (scratch arrays reused)
        const cn = Ball.scratch(n)
        let k = this.contacts(segs, cn)
        if (k === 0)
            return
        // ---- 1. velocity
        let lnx = 0, lny = 0, last = -1
        // the first wall-portal host piece that changes the velocity (portalState.hostHit, TASK-201)
        let hostSeg = null, hvx = 0, hvy = 0
        for (let it = 0; it <= CONTACT_ITERATIONS; ++it)
        {
            const vx = this.speedX, vy = this.speedY
            let best = -1, bd = Infinity
            for (let j = 0; j < k; ++j)
            {
                const o = j * CS
                if (cn[o + 2] < bd && vx * cn[o] + vy * cn[o + 1] < 0)
                {
                    best = j; bd = cn[o + 2]
                }
            }
            if (best < 0)
                break
            const bnx = cn[best * CS], bny = cn[best * CS + 1], vn = vx * bnx + vy * bny
            if (it < CONTACT_ITERATIONS)
            {
                this.speedX = vx - 2 * vn * bnx
                this.speedY = vy - 2 * vn * bny
            }
            else
            {
                // out of reflections (a jammed wedge): drop every approaching normal part
                for (let p = 0; p < CONTACT_ITERATIONS; ++p)
                {
                    let worst = -1, wv = 0
                    for (let j = 0; j < k; ++j)
                    {
                        const u = this.speedX * cn[j * CS] + this.speedY * cn[j * CS + 1]
                        if (u < wv)
                        {
                            worst = j; wv = u
                        }
                    }
                    if (worst < 0)
                        break
                    this.speedX -= wv * cn[worst * CS]
                    this.speedY -= wv * cn[worst * CS + 1]
                }
            }
            const bs = segs[cn[best * CS + 5]]
            if (hostSeg === null && bs.hostList !== undefined)
            {
                hostSeg = bs; hvx = vx; hvy = vy
            }
            lnx = bnx; lny = bny; last = best
        }
        if (hostSeg !== null)
            portalHostHit(hostSeg, hvx, hvy)
        // ---- 2. position
        let pi = -1, pnx = 0, pny = 0
        for (let it = 0; it < PUSH_ITERATIONS; ++it)
        {
            k = this.contacts(segs, cn)
            let best = -1, bd = r
            for (let j = 0; j < k; ++j)
                if (cn[j * CS + 2] < bd)
                {
                    best = j; bd = cn[j * CS + 2]
                }
            if (best < 0)
                break
            const o = best * CS, nx = cn[o], ny = cn[o + 1], seg = cn[o + 5]
            let dx = (r - bd) * nx, dy = (r - bd) * ny
            // still touching the line pushed out just before (the push into this one came from there): push out of
            // both at once, keeping that one at radius
            if (pi >= 0 && pi !== seg)
            {
                let other = -1
                for (let j = 0; j < k; ++j)
                    if (cn[j * CS + 5] === pi)
                        other = j
                if (other >= 0)
                {
                    const ux = cn[other * CS], uy = cn[other * CS + 1], c = ux * nx + uy * ny, det = 1 - c * c
                    const r1 = r - cn[other * CS + 2], r2 = r - bd
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
            pnx = nx; pny = ny
        }
        // ---- 3. energy: back to E0 along the last reflected normal (else the last push-out normal)
        if (last >= 0)
            this.setEnergy(E0, lnx, lny)
        else if (pi >= 0)
            this.setEnergy(E0, pnx, pny)
    }
    // E = |v|^2/2 + g vy/2 - g y, the integrator's free-flight invariant (constant between steps without contact)
    energy()
    {
        const g = gravitationalAcceleration
        return 0.5 * (this.speedX * this.speedX + this.speedY * this.speedY) + 0.5 * g * this.speedY - g * this.posY
    }
    // E = E0 exactly (TASK-270; contactCollision step 3 and portalTeleport's refused-exit bounce, TASK-201): the normal part w of v along (nx, ny) is set to the root w >= 0 of E(vt + w n) = E0
    // (E(w) = 0.5 w^2 + (g n_y / 2) w + C). When no such root exists (the step's push-out alone lifted the ball
    // above E0 even with w = 0, e.g. a ball started inside a line), w is 0 and, if that is still above E0, the whole
    // velocity is scaled down towards 0 (the start state was not a reachable one); when the ball holds no
    // velocity to give, E stays where the push-out put it.
    setEnergy(E0, nx, ny)
    {
        const g = gravitationalAcceleration
        const vx = this.speedX, vy = this.speedY, vn = vx * nx + vy * ny
        const tx = vx - vn * nx, ty = vy - vn * ny, b = 0.5 * g * ny
        const C = 0.5 * (tx * tx + ty * ty) + 0.5 * g * ty - g * this.posY - E0
        const D = b * b - 2 * C
        if (D >= 0 && -b + Math.sqrt(D) >= 0)
        {
            const w = -b + Math.sqrt(D)
            this.speedX = tx + w * nx
            this.speedY = ty + w * ny
            return
        }
        this.speedX = tx
        this.speedY = ty
        // 0.5 s^2 |t|^2 + 0.5 g s t_y - g y - E0 = 0, the largest root s in [0, 1]
        const A = 0.5 * (tx * tx + ty * ty), B = 0.5 * g * ty, C2 = -g * this.posY - E0
        if (A > 0)
        {
            const D2 = B * B - 4 * A * C2
            let s = D2 >= 0 ? (-B + Math.sqrt(D2)) / (2 * A) : 0
            if (!(s >= 0)) s = 0
            if (s > 1) s = 1
            this.speedX = s * tx
            this.speedY = s * ty
        }
    }
    // Contacts with segs at the current position, ghost joint contacts removed (see contactCollision); returns
    // their count, records at out[j * CS]
    contacts(segs, out)
    {
        const n = segs.length
        let k = 0
        for (let i = 0; i < n; ++i)
        {
            const s = segs[i]
            if (!this.segContact(s, out, k))
                continue
            // TASK-201 (TASK-074/173): a wall-portal host piece (portalHostSegs): a ball being captured by a portal
            // ignores a host-line contact in its capture zone (portalCaptureZone); a ball moving away from the portal's
            // front ignores the pieces (as the old portalHostCollision did: an exit placed next to a rim may overlap
            // them, it moves out freely) except at the host line's own ends
            if (s.hostList !== undefined)
            {
                const e = out[k * CS + 6], hostEnd = (e === 1 && s.endA) || (e === 2 && s.endC)
                if (s.away ? !hostEnd
                           : portalCaptureZone(this, s.hostList, out[k * CS + 3], out[k * CS + 4], hostEnd))
                    continue
            }
            out[k * CS + 5] = i
            ++k
        }
        let m = 0
        for (let j = 0; j < k; ++j)
        {
            if (out[j * CS + 6] !== 0 && this.ghostContact(segs, out, j))
                continue
            if (m !== j)
                for (let q = 0; q < CS; ++q)
                    out[m * CS + q] = out[j * CS + q]
            ++m
        }
        return m
    }
    // Contact j lies on an end V of its line: it is a ghost when another line joined at V (an end within CHAIN_JOIN)
    // has the centre projecting into it (past its joined end: the normal (c - V) is outside the joint's cone) and is
    // at least as close as V and itself a contact (with exactly shared ends it always is; for ends up to CHAIN_JOIN
    // apart, a V that sticks out deeper is a real step and stays)
    ghostContact(segs, out, j)
    {
        const o = j * CS, l = segs[out[o + 5]], d = out[o + 2], x0 = this.posX, y0 = this.posY
        const vx = out[o + 6] === 1 ? l.posX : l.posX2, vy = out[o + 6] === 1 ? l.posY : l.posY2
        const J2 = CHAIN_JOIN * CHAIN_JOIN
        for (let i = 0; i < segs.length; ++i)
        {
            const s = segs[i]
            if (s === l)
                continue
            for (let e = 0; e < 2; ++e)
            {
                const ex = e ? s.posX2 : s.posX, ey = e ? s.posY2 : s.posY
                if ((ex - vx) * (ex - vx) + (ey - vy) * (ey - vy) > J2)
                    continue
                const fx = (e ? s.posX : s.posX2) - ex, fy = (e ? s.posY : s.posY2) - ey
                const p = (x0 - ex) * fx + (y0 - ey) * fy
                if (!(p > 0))
                    continue
                // the joined line must itself be a contact (so it carries the collision) and not farther than V
                const L2 = fx * fx + fy * fy, t = p < L2 ? p / L2 : 1
                const dO = Math.hypot(x0 - ex - t * fx, y0 - ey - t * fy)
                if (dO <= d + CONTACT_SLOP && dO < this.radius + CONTACT_SLOP)
                    return true
            }
        }
        return false
    }
    // Contact of this ball with segment l at its current position: when |c - q| < radius + CONTACT_SLOP, writes
    // [nx, ny, dist, qx, qy, -, end] at out[k * CS] (end: 1 = q is the start point, 2 = the end point, else 0)
    // and returns true
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
        const o = k * CS
        out[o] = nx; out[o + 1] = ny; out[o + 2] = d; out[o + 3] = qx; out[o + 4] = qy
        out[o + 6] = L2 > 0 && t > 0 && t < 1 ? 0 : (t <= 0 ? 1 : 2)
        return true
    }
    // shared scratch buffer: CS numbers per contact
    static scratch(n)
    {
        if (!Ball._scratch || Ball._scratch.length < (n + 2) * CS)
            Ball._scratch = new Float64Array((n + 8) * CS)
        return Ball._scratch
    }
    collision()
    {
        // wall-portal host lines (null when the level has none): line object -> its resolved portals
        const hosts = portalHosts()
        const segs = []
        const m = this.radius + 1, x0 = this.posX, y0 = this.posY
        for (let i = 0; i < lines.length; ++i)
        {
            const l = lines[i]
            // exact broadphase (TASK-122): a line cannot touch the ball when its centre lies outside the line's
            // bounding box grown by radius + 1 (a host line's pieces lie inside its box)
            if (x0 < (l.posX < l.posX2 ? l.posX : l.posX2) - m || x0 > (l.posX > l.posX2 ? l.posX : l.posX2) + m ||
                y0 < (l.posY < l.posY2 ? l.posY : l.posY2) - m || y0 > (l.posY > l.posY2 ? l.posY : l.posY2) + m)
                continue
            const host = hosts && hosts.get(l)
            if (!host)
                segs.push(l)
            else
                // TASK-201: a wall-portal host line takes part in the same contact model as its solid pieces
                // (the whole line from behind, the pieces outside the open gaps from the front), see portalHostSegs
                portalHostSegs(this, l, host, segs)
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