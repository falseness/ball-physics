// Ball trail: a two-strand helix along the last TRAIL_MAX recorded ball positions.
//
// Recording (trailRecord, called at the end of gameMechanics() while physics is on): one sample
// {x, y, frame, seg} per frame. `frame` is a global counter (the helix phase is taken from it,
// so the twist stays fixed to the path instead of sliding). `seg` changes after a portal
// teleport so no stroke joins the two sides. trailReset() is called by levelChoosed().
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
    const vmax = Math.hypot(H[n - 1].x - H[n - 2].x, H[n - 1].y - H[n - 2].y)
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
}
