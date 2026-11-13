// Ball trail: a two-strand helix along the last TRAIL_MAX recorded ball positions.
//
// Recording (trailRecord, called at the end of gameMechanics() while physics is on): one sample
// {x, y, frame, seg} per frame. `frame` is a global counter (the helix phase is taken from it,
// so the twist stays fixed to the path instead of sliding). `seg` changes after a portal
// teleport so no stroke joins the two sides. trailReset() is called by levelChoosed().
// trailAnnotate() adds speed arrows/labels, the live 'v = ... mm/s' readout and a coral velocity arrow.
// Drawing only, physics is never touched.

const TRAIL_MAX = 60
const TRAIL_COLOR = 'rgba(130,210,255,1)'
let trail = []
let trailFrame = 0
let trailSeg = 0

function trailReset()
{
    trail = []
    ++trailSeg
}

function trailRecord(teleported)
{
    if (teleported)
        ++trailSeg
    trail.push({ x: ball.posX, y: ball.posY, frame: trailFrame++, seg: trailSeg })
    if (trail.length > TRAIL_MAX)
        trail.shift()
}

// test hook: a copy of the recorded samples
function trailSamples()
{
    return trail.map(s => ({ x: s.x, y: s.y, frame: s.frame, seg: s.seg }))
}

function trailSegments()
{
    const out = []
    for (let i = 0; i < trail.length; ++i)
    {
        if (!i || trail[i].seg !== trail[i - 1].seg)
            out.push([])
        out[out.length - 1].push(trail[i])
    }
    return out
}

// strand points of one segment: per sample i >= 1 {p: [P1, P2], alpha}
function trailStrands(H)
{
    const n = H.length, k = Math.min(n, TRAIL_MAX), s0 = n - k
    // width scale: the fastest step of the segment, so A = 2 + 12 * L / vmax stays in [2, 14]
    let vmax = 0
    for (let i = 1; i < n; ++i)
        vmax = Math.max(vmax, Math.hypot(H[i].x - H[i - 1].x, H[i].y - H[i - 1].y))
    const pts = []
    let nx = 0, ny = 0
    for (let i = 1; i < n; ++i)
    {
        const dx = H[i].x - H[i - 1].x, dy = H[i].y - H[i - 1].y, L = Math.hypot(dx, dy)
        if (L > 0)
        {
            nx = -dy / L
            ny = dx / L
        }
        const A = 2 + (vmax > 0 ? 12 * L / vmax : 0)
        const a = H[i].frame * 0.45
        const f = (i - s0) / k
        const s1 = A * Math.sin(a), s2 = A * Math.sin(a + Math.PI)
        pts.push({
            i: i, frame: H[i].frame,
            p: [[H[i].x + nx * s1, H[i].y + ny * s1], [H[i].x + nx * s2, H[i].y + ny * s2]],
            fade: Math.min(1, f * 5), alpha: Math.min(1, f * 5) * 0.85
        })
    }
    return pts
}

// test hook: per segment (>= 3 samples, as drawn), the max distance between a strand point and its sample H[i]
function trailWidths()
{
    return trailSegments().filter(H => H.length >= 3).map(H => trailStrands(H).reduce((m, q) =>
        Math.max(m, Math.hypot(q.p[0][0] - H[q.i].x, q.p[0][1] - H[q.i].y), Math.hypot(q.p[1][0] - H[q.i].x, q.p[1][1] - H[q.i].y)), 0))
}

function trailDraw()
{
    if (!trail.length)
        return
    ctx.save()
    ctx.strokeStyle = TRAIL_COLOR
    ctx.shadowColor = TRAIL_COLOR
    ctx.lineCap = 'round'
    ctx.setLineDash([])
    const segs = trailSegments()
    for (const H of segs)
    {
        if (H.length < 3)
            continue
        const pts = trailStrands(H)
        // strands: segment by segment, equal brightness for both
        ctx.lineWidth = 1.5
        ctx.shadowBlur = 8
        for (let j = 1; j < pts.length; ++j)
        {
            ctx.globalAlpha = pts[j].alpha
            ctx.beginPath()
            for (let s = 0; s < 2; ++s)
            {
                ctx.moveTo(pts[j - 1].p[s][0], pts[j - 1].p[s][1])
                ctx.lineTo(pts[j].p[s][0], pts[j].p[s][1])
            }
            ctx.stroke()
        }
        // faint rungs every 3 samples
        ctx.lineWidth = 0.7
        ctx.shadowBlur = 0
        for (const q of pts)
        {
            if (q.frame % 3)
                continue
            ctx.globalAlpha = 0.25 * q.fade
            ctx.beginPath()
            ctx.moveTo(q.p[0][0], q.p[0][1])
            ctx.lineTo(q.p[1][0], q.p[1][1])
            ctx.stroke()
        }
    }
    ctx.restore()
    trailAnnotate()
}

// ---- annotations (drawn only while the strands of the current segment are shown) ----
const TRAIL_ARROW_STEP = 7      // frames between speed arrows
const TRAIL_ARROW_MAX = 7
const TRAIL_ARROW_SCALE = 3.2   // arrow length = |H[i] - H[i-1]| * scale
const TRAIL_VEL_LEN = 70        // coral velocity arrow length beyond the ball rim
const TRAIL_ARROW_GAP = 24       // min px between speed-arrow anchors

// test hook + draw data: speed arrows of the newest segment (newest first, every 7 frames, needs H[i-1],
// overlapping anchors dropped),
// the live readout and the velocity direction; null when the trail is not shown
function trailLabels()
{
    if (!trail.length)
        return null
    const segs = trailSegments(), H = segs[segs.length - 1]
    if (H.length < 3)
        return null
    const arrows = []
    for (let c = 0, i = H.length - 1; c < TRAIL_ARROW_MAX && i >= 1; ++c, i -= TRAIL_ARROW_STEP)
    {
        // a retraced path (vertical bounce) puts candidates on top of each other: keep a candidate only
        // when its anchor is >= TRAIL_ARROW_GAP px from every arrow already kept (the newest always is)
        if (arrows.some(a => Math.hypot(a.x - H[i].x, a.y - H[i].y) < TRAIL_ARROW_GAP))
            continue
        const dx = H[i].x - H[i - 1].x, dy = H[i].y - H[i - 1].y
        arrows.push({ x: H[i].x, y: H[i].y, dx: dx, dy: dy, label: Math.round(Math.hypot(dx, dy) * 60), i: i, c: c })
    }
    const v = Math.round(Math.hypot(ball.speedX, ball.speedY) * cyclesPerTact * 60)
    return {
        arrows: arrows, live: 'v = ' + v + ' mm/s', liveValue: v,
        velocityAngle: Math.atan2(ball.speedY, ball.speedX)
    }
}

function trailArrow(x, y, dx, dy, color, w, head)
{
    if (!(Math.hypot(dx, dy) > 0))
        return
    const ex = x + dx * TRAIL_ARROW_SCALE, ey = y + dy * TRAIL_ARROW_SCALE
    ctx.strokeStyle = color
    ctx.lineWidth = w
    ctx.beginPath()
    ctx.moveTo(x, y)
    ctx.lineTo(ex, ey)
    ctx.stroke()
    arrowHead(ctx, ex, ey, Math.atan2(dy, dx), head, color)
}

function trailAnnotate()
{
    const L = trailLabels()
    if (!L)
        return
    ctx.save()
    ctx.lineCap = 'round'
    ctx.setLineDash([])
    ctx.font = '15px ' + THEME.fontStack
    ctx.textAlign = 'right'
    ctx.textBaseline = 'alphabetic'
    // older arrows + their labels first, the newest (coral, glowing) on top
    for (let j = L.arrows.length - 1; j >= 1; --j)
    {
        const a = L.arrows[j], f = 1 - a.c / TRAIL_ARROW_MAX
        ctx.shadowBlur = 0
        ctx.globalAlpha = 0.3 + 0.7 * f
        trailArrow(a.x, a.y, a.dx, a.dy, THEME.soft, 1.2, 6)
        ctx.globalAlpha = 0.15 + 0.55 * f
        ctx.fillStyle = THEME.soft
        ctx.fillText(String(a.label), a.x - 12, a.y - 6)
    }
    const a0 = L.arrows[0]
    ctx.globalAlpha = 1
    ctx.shadowColor = THEME.coral
    ctx.shadowBlur = 8
    trailArrow(a0.x, a0.y, a0.dx, a0.dy, THEME.coral, 1.8, 9)
    // coral velocity arrow from the ball rim
    const sp = Math.hypot(ball.speedX, ball.speedY)
    if (sp > 0)
    {
        const ux = ball.speedX / sp, uy = ball.speedY / sp, r = ball.radius
        const x1 = ball.posX + ux * r, y1 = ball.posY + uy * r
        const x2 = ball.posX + ux * (r + TRAIL_VEL_LEN), y2 = ball.posY + uy * (r + TRAIL_VEL_LEN)
        const R = sketchRng(sketchSeed([trailFrame]))
        handLine(ctx, R, x1, y1, x2, y2, THEME.coral, 1.8, 2, 0.6, 0)
        arrowHead(ctx, x2, y2, L.velocityAngle, 9, THEME.coral)
    }
    // live readout
    ctx.shadowBlur = 0
    ctx.globalAlpha = 1
    ctx.fillStyle = THEME.ink
    ctx.font = '20px ' + THEME.fontStack
    ctx.textAlign = 'left'
    ctx.fillText(L.live, ball.posX + 24, ball.posY - 22)
    ctx.restore()
}
