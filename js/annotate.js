'use strict'
// Measurement annotations in the 07 "Engineering Pad" style (purely visual, no gameplay values):
//  - every player line: offset dimension line with arrowheads + rotated '<len> mm @ <deg>°' label
//  - a 'target' leader next to the flag
//  - an angle callout (dash-dot horizontal reference + filled circle sector on the free side + '<deg>°')
//    on the first sloped level line
// annotationLabels() returns the label strings drawn in the most recent frame.
const DIM_OFFSET = 20
let lastAnnotationLabels = []

// Acute angle to the horizontal, degrees
function lineSlopeDeg(x1, y1, x2, y2)
{
    return Math.atan2(Math.abs(y2 - y1), Math.abs(x2 - x1)) * 180 / Math.PI
}
function dimensionLabel(x1, y1, x2, y2)
{
    return Math.round(Math.hypot(x2 - x1, y2 - y1)) + ' mm @ ' + lineSlopeDeg(x1, y1, x2, y2).toFixed(1) + '°'
}
function annotText(t, x, y, size, color, rot = 0, align = 'center')
{
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot)
    ctx.font = size + 'px ' + THEME.fontStack; ctx.fillStyle = color
    ctx.textAlign = align; ctx.textBaseline = 'middle'
    ctx.fillText(t, 0, 0); ctx.restore()
}
function drawDimension(l)
{
    let x1 = l.posX, y1 = l.posY, x2 = l.posX2, y2 = l.posY2
    if (Math.hypot(x2 - x1, y2 - y1) < 1)
        return null
    // orient left -> right so the label reads upright and the offset sits above the line
    if (x2 < x1 || (x2 == x1 && y2 > y1)) [x1, y1, x2, y2] = [x2, y2, x1, y1]
    const a = Math.atan2(y2 - y1, x2 - x1), nx = Math.sin(a) * DIM_OFFSET, ny = -Math.cos(a) * DIM_OFFSET
    const R = sketchRng(sketchSeed([x1, y1, x2, y2, 7]))
    const label = dimensionLabel(l.posX, l.posY, l.posX2, l.posY2)
    // quiet, soft-ink dimension (coral stays reserved for the player's line itself)
    ctx.save()
    ctx.globalAlpha = .26
    ctx.lineWidth = .8
    // extension lines (start just off the ring ends) and the dimension line itself
    handLine(ctx, R, x1 + nx * .3, y1 + ny * .3, x1 + nx * 1.15, y1 + ny * 1.15, THEME.soft, .8, 1, 0.4, 1)
    handLine(ctx, R, x2 + nx * .3, y2 + ny * .3, x2 + nx * 1.15, y2 + ny * 1.15, THEME.soft, .8, 1, 0.4, 1)
    handLine(ctx, R, x1 + nx, y1 + ny, x2 + nx, y2 + ny, THEME.soft, .8, 1, 0.4, 0)
    arrowHead(ctx, x1 + nx, y1 + ny, a + Math.PI, 5, THEME.soft)
    arrowHead(ctx, x2 + nx, y2 + ny, a, 5, THEME.soft)
    ctx.restore()
    ctx.save()
    ctx.globalAlpha = .45
    annotText(label, (x1 + x2) / 2 + nx * 1.45, (y1 + y2) / 2 + ny * 1.45, 17, THEME.soft, a)
    ctx.restore()
    return label
}
function drawTargetLeader(x, y)
{
    if (flag.length < 5)
        return null
    // leader from the pennant centroid, pointing diagonally away from the pole (works for any flagRotate)
    const tx = x + (flag[2][0] + flag[3][0] + flag[4][0]) / 3, ty = y + (flag[2][1] + flag[3][1] + flag[4][1]) / 3
    const px = x + flag[2][0] / 2, py = y + flag[2][1] / 2
    let sx = tx >= px ? 1 : -1, sy = ty > py ? 1 : -1
    if (tx + sx * 140 > GAME_W - 40 || tx + sx * 140 < 40) sx = -sx
    if (ty + sy * 70 < 40 || ty + sy * 70 > GAME_H - 40) sy = -sy
    const ex = tx + sx * 70, ey = ty + sy * 60
    const R = sketchRng(sketchSeed([x, y, tx, ty, 11]))
    ctx.save()
    ctx.globalAlpha = .8
    handLine(ctx, R, tx + sx * 6, ty + sy * 5, ex, ey, THEME.soft, 1, 1, 0.5, 0)
    ctx.fillStyle = THEME.soft
    ctx.beginPath(); ctx.arc(tx + sx * 6, ty + sy * 5, 2, 0, Math.PI * 2); ctx.fill()
    ctx.restore()
    annotText('target', ex + sx * 6, ey, 26, THEME.ink, 0, sx > 0 ? 'left' : 'right')
    return 'target'
}
function firstSlopedLevelLine()
{
    const L = curLevel().lines
    for (let i = 0; i < L.length; ++i)
        if (L[i].posX != L[i].posX2 && L[i].posY != L[i].posY2)
            return L[i]
    return null
}
// Angle callout geometry: a circle sector between the dash-dot horizontal reference and the line,
// on the line's free side (opposite the hatching, lineSolidNormal). The reference points away from
// the solid side (h.x = -sign(n.x)); the vertex is the end from which the line runs along h, so the
// acute sector (bisector . n < 0) lies on the free side. The label sits centred on the bisector at
// r + 16 and is pushed outward (up to +30 px) while its box crosses the line, its hatch band or
// leaves the field; if still blocked (very shallow sector) it then shifts along -n (free side).
const CALLOUT_LABEL_GAP = 16, CALLOUT_PUSH_MAX = 30, CALLOUT_SHIFT_MAX = 60, CALLOUT_FONT = 22
function calloutGeom(l)
{
    if (l === undefined)
        l = firstSlopedLevelLine()
    if (!l)
        return null
    const L = curLevel()
    const n = lineSolidNormal(l, L.ballX, L.ballY, currentPortals(), L.lines)
    const hx = n[0] > 0 ? -1 : 1
    let x1 = l.posX, y1 = l.posY, x2 = l.posX2, y2 = l.posY2
    if ((x2 - x1) * hx < 0) [x1, y1, x2, y2] = [x2, y2, x1, y1]
    const len = Math.hypot(x2 - x1, y2 - y1)
    const dx = (x2 - x1) / len, dy = (y2 - y1) / len
    const r = Math.min(45, len * .4), deg = lineSlopeDeg(x1, y1, x2, y2)
    const a0 = hx > 0 ? 0 : Math.PI, a1 = Math.atan2(dy, dx)
    let sweep = a1 - a0
    while (sweep > Math.PI) sweep -= 2 * Math.PI
    while (sweep <= -Math.PI) sweep += 2 * Math.PI
    const bm = a0 + sweep / 2, bx = Math.cos(bm), by = Math.sin(bm)
    const label = deg.toFixed(1) + '°'
    ctx.save(); ctx.font = CALLOUT_FONT + 'px ' + THEME.fontStack
    const w = ctx.measureText(label).width; ctx.restore()
    const h = CALLOUT_FONT
    const d = LINE_HATCH_DEPTH
    const band = [[x1, y1], [x2, y2], [x2 + n[0] * d, y2 + n[1] * d], [x1 + n[0] * d, y1 + n[1] * d]]
    const boxAt = (cx, cy) => ({ x: cx - w / 2, y: cy - h / 2, w: w, h: h })
    let box = null, push = 0, shift = 0
    for (push = 0; push <= CALLOUT_PUSH_MAX; push += 2)
    {
        box = boxAt(x1 + bx * (r + CALLOUT_LABEL_GAP + push), y1 + by * (r + CALLOUT_LABEL_GAP + push))
        if (!calloutBoxBlocked(box, band))
            break
    }
    if (push > CALLOUT_PUSH_MAX)
    {
        // very shallow sector on a short line (e.g. 7.1 deg on 80 px): the bisector stays within a few
        // px of the line, so after the +30 px push the label moves further onto the free side (-n)
        push = CALLOUT_PUSH_MAX
        const cx = x1 + bx * (r + CALLOUT_LABEL_GAP + push), cy = y1 + by * (r + CALLOUT_LABEL_GAP + push)
        for (shift = 2; shift <= CALLOUT_SHIFT_MAX; shift += 2)
        {
            box = boxAt(cx - n[0] * shift, cy - n[1] * shift)
            if (!calloutBoxBlocked(box, band))
                break
        }
    }
    return { vertex: [x1, y1], r: r, a0: a0, a1: a0 + sweep, ccw: sweep < 0, bisector: [bx, by],
        labelBox: box, push: push, shift: shift, label: label, deg: deg, solidNormal: n, line: [x1, y1, x2, y2] }
}
// true when the box crosses the line segment / hatch parallelogram band, or leaves the field
function calloutBoxBlocked(b, band)
{
    if (b.x < 0 || b.y < 0 || b.x + b.w > GAME_W || b.y + b.h > GAME_H)
        return true
    return convexOverlap([[b.x, b.y], [b.x + b.w, b.y], [b.x + b.w, b.y + b.h], [b.x, b.y + b.h]], band)
}
// separating-axis test for two convex polygons (touching counts as overlap)
function convexOverlap(P, Q)
{
    for (const poly of [P, Q])
        for (let i = 0; i < poly.length; ++i)
        {
            const p = poly[i], q = poly[(i + 1) % poly.length], ax = q[1] - p[1], ay = p[0] - q[0]
            if (ax == 0 && ay == 0) continue
            let pmin = Infinity, pmax = -Infinity, qmin = Infinity, qmax = -Infinity
            for (const v of P) { const t = v[0] * ax + v[1] * ay; pmin = Math.min(pmin, t); pmax = Math.max(pmax, t) }
            for (const v of Q) { const t = v[0] * ax + v[1] * ay; qmin = Math.min(qmin, t); qmax = Math.max(qmax, t) }
            if (pmax < qmin || qmax < pmin)
                return false
        }
    return true
}
function drawAngleCallout(l)
{
    const g = calloutGeom(l)
    if (!g)
        return null
    const [x1, y1] = g.vertex, refDir = Math.cos(g.a0) > 0 ? 1 : -1
    ctx.save()
    ctx.strokeStyle = THEME.soft; ctx.fillStyle = THEME.soft
    // dash-dot horizontal reference
    ctx.globalAlpha = .75; ctx.lineWidth = 1
    ctx.setLineDash([6, 3, 1, 3])
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1 + refDir * (g.r + 40), y1); ctx.stroke()
    ctx.setLineDash([])
    // filled sector + arc
    ctx.globalAlpha = .12
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.arc(x1, y1, g.r, g.a0, g.a1, g.ccw); ctx.closePath(); ctx.fill()
    ctx.globalAlpha = .9; ctx.lineWidth = 1.2
    ctx.beginPath(); ctx.arc(x1, y1, g.r, g.a0, g.a1, g.ccw); ctx.stroke()
    ctx.restore()
    const b = g.labelBox
    annotText(g.label, b.x + b.w / 2, b.y + b.h / 2, CALLOUT_FONT, THEME.soft)
    return g.label
}
window.angleCalloutGeom = function() { return calloutGeom() }
function drawAnnotations()
{
    const labels = []
    const callout = drawAngleCallout(firstSlopedLevelLine())
    if (callout) labels.push(callout)
    const target = drawTargetLeader(curLevel().flagX, curLevel().flagY)
    if (target) labels.push(target)
    for (let i = 0; i < lines.length; ++i)
        if (lines[i].type == 'player')
        {
            const d = drawDimension(lines[i])
            if (d) labels.push(d)
        }
    lastAnnotationLabels = labels
}
function annotationLabels()
{
    return lastAnnotationLabels.slice()
}
window.annotationLabels = annotationLabels
