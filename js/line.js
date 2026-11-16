let levelLineColor = '#3e1170'
let lines = []

let line = false
let dotRadius = 5
const LINE_HATCH_DEPTH = 14
const LINE_GLOW_INK = 'rgba(190,230,255,0.55)'
const LINE_GLOW_CORAL = 'rgba(255,106,85,0.6)'
class Line extends Sprite
{
    constructor(posX, posY, posX2, posY2, radius, color, type)
    {
        super(posX, posY, 0, 0, color, type)
        this.posX2 = posX2
        this.posY2 = posY2
        this.radius = radius
    }
    // Stable per-line rng: seeded from the line's own coordinates, so every frame draws the same stroke
    sketchR()
    {
        return sketchRng(sketchSeed([this.posX, this.posY, this.posX2, this.posY2]))
    }
    // Level line: ice ink, hand-drawn, soft glow, solid end dots, hatching on the solid side n
    // (lineSolidNormal) at every slope: the band p1, p2, p2 + n*d, p1 + n*d.
    // gaps: [[u0, u1], ...] parts of the line (0..1 along posX,posY -> posX2,posY2) left open for
    // wall portals; the line is drawn as the pieces between them (end dots only at the real ends).
    drawLevel(gaps, n)
    {
        const R = this.sketchR(), X1 = this.posX, Y1 = this.posY, X2 = this.posX2, Y2 = this.posY2
        const pieces = lineGapPieces(gaps)
        for (const [a, b] of pieces)
            this.drawLevelPiece(R, X1 + a * (X2 - X1), Y1 + a * (Y2 - Y1), X1 + b * (X2 - X1), Y1 + b * (Y2 - Y1), n)
        ctx.save()
        ctx.shadowColor = LINE_GLOW_INK; ctx.shadowBlur = 10
        ctx.fillStyle = THEME.ink
        ctx.beginPath(); ctx.arc(X1, Y1, 3.5, 0, Math.PI * 2); ctx.arc(X2, Y2, 3.5, 0, Math.PI * 2); ctx.fill()
        ctx.restore()
    }
    drawLevelPiece(R, x1, y1, x2, y2, n)
    {
        if (n && Math.hypot(x2 - x1, y2 - y1) > 1)
        {
            const d = LINE_HATCH_DEPTH, ox = n[0] * d, oy = n[1] * d
            let a = Math.atan2(y2 - y1, x2 - x1)          // hatch at 45 deg to the line itself
            if (a > Math.PI / 2) a -= Math.PI
            if (a <= -Math.PI / 2) a += Math.PI
            const bx = Math.min(x1, x2, x1 + ox, x2 + ox), by = Math.min(y1, y2, y1 + oy, y2 + oy)
            const bw = Math.max(x1, x2, x1 + ox, x2 + ox) - bx, bh = Math.max(y1, y2, y1 + oy, y2 + oy) - by
            hatch(ctx, () => { ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.lineTo(x2 + ox, y2 + oy); ctx.lineTo(x1 + ox, y1 + oy); ctx.closePath() },
                bx, by, bw, bh, a + Math.PI * .75, 7, THEME.ink, 1.1, .6)
        }
        ctx.save()
        ctx.shadowColor = LINE_GLOW_INK; ctx.shadowBlur = 10
        handLine(ctx, R, x1, y1, x2, y2, THEME.ink, 2.6, 2, 0.6, 4)
        ctx.restore()
    }
    // Player line: coral, hand-drawn, same glow, hollow ring ends
    drawPlayer()
    {
        const R = this.sketchR(), x1 = this.posX, y1 = this.posY, x2 = this.posX2, y2 = this.posY2
        ctx.save()
        ctx.shadowColor = LINE_GLOW_CORAL; ctx.shadowBlur = 10
        handLine(ctx, R, x1, y1, x2, y2, THEME.coral, 2.8, 1, 0.5, 2)
        handCircle(ctx, R, x1, y1, 6, THEME.coral, 1.8)
        handCircle(ctx, R, x2, y2, 6, THEME.coral, 1.8)
        ctx.restore()
    }
    draw(gaps, n)
    {
        if (this.type == 'player')
            this.drawPlayer()
        else
            this.drawLevel(gaps, n)
    }
}

// [0, 1] minus the (clamped, merged) gap intervals -> the drawn pieces [[a, b], ...]
function lineGapPieces(gaps)
{
    const g = (gaps || []).map(([a, b]) => [Math.max(0, Math.min(a, b)), Math.min(1, Math.max(a, b))])
        .filter(([a, b]) => b > a).sort((p, q) => p[0] - q[0])
    const pieces = []
    let from = 0
    for (const [a, b] of g)
    {
        if (a > from)
            pieces.push([from, a])
        from = Math.max(from, b)
    }
    if (from < 1)
        pieces.push([from, 1])
    return pieces
}

// Wall-portal openings on `host` (u ± h / length) from resolved portals whose host line is
// levelLines[P.line] (identity, so it works for the game's `lines` and the editor's copy)
function lineGaps(host, portals, levelLines)
{
    const gaps = []
    if (!portals)
        return gaps
    const len = Math.hypot(host.posX2 - host.posX, host.posY2 - host.posY)
    for (const P of portals)
        if (typeof P.line == 'number' && levelLines[P.line] === host && len > 0)
            gaps.push([P.u - P.h / len, P.u + P.h / len])
    return gaps
}

// Unit normal of level line l pointing to its solid (hatched) side: the side that does NOT contain
// the ball start (bx, by). Ball start on the line's extension (|signed distance| < 1 px): the
// normal with positive y, or positive x for an exactly vertical line. A line hosting a wall portal
// (levelLines[P.line] === l) hatches the portal's back side: -n of portalFrame(P).
const LINE_SOLID_ON_LINE = 1
function lineSolidNormal(l, bx, by, portals, levelLines)
{
    if (portals && levelLines)
        for (const P of portals)
            if (typeof P.line == 'number' && levelLines[P.line] === l)
            {
                const f = portalFrame(P)
                return [-f.nx, -f.ny]
            }
    const dx = l.posX2 - l.posX, dy = l.posY2 - l.posY, len = Math.hypot(dx, dy)
    if (!(len > 0))
        return [0, 1]
    const nx = -dy / len, ny = dx / len
    const s = (bx - l.posX) * nx + (by - l.posY) * ny
    if (Math.abs(s) < LINE_SOLID_ON_LINE)
    {
        const flip = dx == 0 ? nx < 0 : ny < 0
        return flip ? [-nx, -ny] : [nx, ny]
    }
    return s > 0 ? [-nx, -ny] : [nx, ny]
}

// list / levelLines / portals / ball start default to the game's lines, the current level's
// lines, portals and ball start (the editor passes its working copy's)
function drawLines(list = lines, levelLines = curLevel().lines, portals = currentPortals(), ballXY = null)
{
    const L = curLevel(), bx = ballXY ? ballXY[0] : L.ballX, by = ballXY ? ballXY[1] : L.ballY
    for (let i = 0; i < list.length; ++i)
    {
        const l = list[i]
        l.draw(lineGaps(l, portals, levelLines), l.type == 'player' ? null : lineSolidNormal(l, bx, by, portals, levelLines))
    }
}

// Test hook: solid-side normal of every level line of the current level (the editor's working copy
// while editing); ballSide = sign of the ball start's signed distance along n (-1 = ball on the
// open side), onLine = the fallback applied, host = the line hosts a wall portal
window.lineHatchSides = function()
{
    const ed = editorMode && editor.level
    const W = ed ? editor.level : curLevel(), portals = ed ? editorPortals() : currentPortals()
    return W.lines.map(function(l, i)
    {
        const n = lineSolidNormal(l, W.ballX, W.ballY, portals, W.lines)
        const s = (W.ballX - l.posX) * n[0] + (W.ballY - l.posY) * n[1]
        const host = !!(portals && portals.some(P => typeof P.line == 'number' && W.lines[P.line] === l))
        return { i: i, n: n, ballSide: s < 0 ? -1 : 1, onLine: Math.abs(s) < LINE_SOLID_ON_LINE && !host, host: host }
    })
}
