'use strict'
// Measurement annotations in the 07 "Engineering Pad" style (purely visual, no gameplay values):
//  - every player line: offset dimension line with arrowheads + rotated '<len> mm @ <deg>°' label
//  - a 'target' leader next to the flag
//  - an angle callout (dash-dot horizontal reference + arc + '<deg>°') on the first sloped level line
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
    const L = levels[thisLevel].lines
    for (let i = 0; i < L.length; ++i)
        if (L[i].posX != L[i].posX2 && L[i].posY != L[i].posY2)
            return L[i]
    return null
}
function drawAngleCallout(l)
{
    if (!l)
        return null
    // vertex = left endpoint; reference line points right, arc sweeps to the line
    let x1 = l.posX, y1 = l.posY, x2 = l.posX2, y2 = l.posY2
    if (x2 < x1) [x1, y1, x2, y2] = [x2, y2, x1, y1]
    const a = Math.atan2(y2 - y1, x2 - x1), len = Math.hypot(x2 - x1, y2 - y1)
    const r = Math.min(45, len * .4), deg = lineSlopeDeg(x1, y1, x2, y2)
    const label = deg.toFixed(1) + '°'
    ctx.save()
    ctx.strokeStyle = THEME.soft; ctx.globalAlpha = .75; ctx.lineWidth = 1
    ctx.setLineDash([6, 3, 1, 3])
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1 + r + 40, y1); ctx.stroke()
    ctx.setLineDash([])
    ctx.beginPath(); ctx.arc(x1, y1, r, 0, a, a < 0); ctx.stroke()
    ctx.restore()
    const m = a / 2, lr = r + 20
    annotText(label, x1 + Math.cos(m) * lr + 6, y1 + Math.sin(m) * lr, 22, THEME.soft)
    return label
}
function drawAnnotations()
{
    const labels = []
    const callout = drawAngleCallout(firstSlopedLevelLine())
    if (callout) labels.push(callout)
    const target = drawTargetLeader(levels[thisLevel].flagX, levels[thisLevel].flagY)
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
