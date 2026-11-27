'use strict'
// Measurement annotations in the 07 "Engineering Pad" style (purely visual, no gameplay values):
//  - every player line: offset dimension line with arrowheads + rotated '<len> mm' label, and at its
//    left end (lower end for vertical lines) a dash-dot horizontal reference + filled circle sector + '<deg>°'
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
    return Math.round(Math.hypot(x2 - x1, y2 - y1)) + ' mm'
}
// Left end first (lower end, larger y, for vertical lines): the dimension label reads upright and the
// angle sector opens from a horizontal reference pointing toward +x.
function orientLeftRight(l)
{
    let x1 = l.posX, y1 = l.posY, x2 = l.posX2, y2 = l.posY2
    if (x2 < x1 || (x2 == x1 && y2 > y1)) [x1, y1, x2, y2] = [x2, y2, x1, y1]
    return [x1, y1, x2, y2]
}
function dimensionLabelBox(l)
{
    const [x1, y1, x2, y2] = orientLeftRight(l)
    const a = Math.atan2(y2 - y1, x2 - x1), nx = Math.sin(a) * DIM_OFFSET, ny = -Math.cos(a) * DIM_OFFSET
    const label = dimensionLabel(x1, y1, x2, y2)
    ctx.save(); ctx.font = '17px ' + THEME.fontStack
    const w = ctx.measureText(label).width; ctx.restore()
    const cx = (x1 + x2) / 2 + nx * 1.45, cy = (y1 + y2) / 2 + ny * 1.45, c = Math.cos(a), s = Math.sin(a)
    const hw = w / 2, hh = 17 / 2
    return [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]].map(([u, v]) => [cx + u * c - v * s, cy + u * s + v * c])
}
// Player line angle mark: vertex at the left end, dash-dot horizontal reference (r + 20) toward +x, filled
// sector between the reference and the line (r = min(28, len*0.4)) and '<deg>°' centred on the bisector at
// r + 12. The label is pushed outward along the bisector (up to +20 px), then shifted perpendicular to the line
// toward +x (reference side, up to 40 px) while its box crosses the line (±5 px), the reference or the
// dimension label, or leaves the field. deg < 1: no reference/sector, label next to the left end.
const PLAYER_ANGLE_GAP = 12, PLAYER_ANGLE_FONT = 17, PLAYER_ANGLE_PUSH = 20, PLAYER_ANGLE_SHIFT = 40
function playerAngleGeom(l)
{
    const [x1, y1, x2, y2] = orientLeftRight(l)
    const len = Math.hypot(x2 - x1, y2 - y1)
    if (len < 1)
        return null
    const dx = (x2 - x1) / len, dy = (y2 - y1) / len
    const deg = lineSlopeDeg(x1, y1, x2, y2), r = Math.min(28, len * .4)
    const sector = deg >= 1
    const a1 = Math.atan2(dy, dx) // in [-90°, 90°]; reference at angle 0
    const label = deg.toFixed(1) + '°'
    ctx.save(); ctx.font = PLAYER_ANGLE_FONT + 'px ' + THEME.fontStack
    const w = ctx.measureText(label).width; ctx.restore()
    const h = PLAYER_ANGLE_FONT
    const T = 5
    const lineBand = [[x1 - dy * T - dx * T, y1 + dx * T - dy * T], [x2 - dy * T + dx * T, y2 + dx * T + dy * T],
        [x2 + dy * T + dx * T, y2 - dx * T + dy * T], [x1 + dy * T - dx * T, y1 - dx * T - dy * T]]
    const obstacles = [lineBand, dimensionLabelBox(l)]
    if (sector)
        obstacles.push([[x1, y1 - 1], [x1 + r + 20, y1 - 1], [x1 + r + 20, y1 + 1], [x1, y1 + 1]])
    const boxAt = (cx, cy) => ({ x: cx - w / 2, y: cy - h / 2, w: w, h: h })
    const blocked = b => {
        if (b.x < 0 || b.y < 0 || b.x + b.w > GAME_W || b.y + b.h > GAME_H)
            return true
        const P = [[b.x, b.y], [b.x + b.w, b.y], [b.x + b.w, b.y + b.h], [b.x, b.y + b.h]]
        return obstacles.some(Q => convexOverlap(P, Q))
    }
    let box = null, push = 0, shift = 0, bx, by, sx, sy
    if (sector)
    {
        bx = Math.cos(a1 / 2); by = Math.sin(a1 / 2)
        // line normal pointing to +x: from the line into the sector (toward the reference)
        sx = -dy; sy = dx
        if (sx < 0) { sx = -sx; sy = -sy }
    }
    else
    {
        // flat line: label to the left of the left end, else below / above it
        bx = -1; by = 0; sx = 0; sy = 1
    }
    const base = sector ? r + PLAYER_ANGLE_GAP : PLAYER_ANGLE_GAP + w / 2
    for (push = 0; push <= PLAYER_ANGLE_PUSH; push += 2)
    {
        box = boxAt(x1 + bx * (base + push), y1 + by * (base + push))
        if (!blocked(box))
            break
    }
    if (push > PLAYER_ANGLE_PUSH)
    {
        push = PLAYER_ANGLE_PUSH
        const cx = x1 + bx * (base + push), cy = y1 + by * (base + push)
        for (shift = 2; shift <= PLAYER_ANGLE_SHIFT; shift += 2)
        {
            box = boxAt(cx + sx * shift, cy + sy * shift)
            if (!blocked(box))
                break
        }
        if (shift > PLAYER_ANGLE_SHIFT)
            shift = PLAYER_ANGLE_SHIFT
    }
    // TASK-264: nothing free (e.g. a steep line at the field edge): mirror the bisector to the other side of the line,
    // and if that is blocked too keep the box inside the field
    if (blocked(box))
    {
        for (let p = 0; p <= PLAYER_ANGLE_PUSH; p += 2)
        {
            const b = boxAt(x1 - bx * (base + p), y1 + by * (base + p))
            if (!blocked(b)) { box = b; push = p; bx = -bx; break }
        }
        box.x = Math.min(Math.max(box.x, 0), GAME_W - box.w)
        box.y = Math.min(Math.max(box.y, 0), GAME_H - box.h)
    }
    return { vertex: [x1, y1], r: r, a0: 0, a1: a1, ccw: a1 < 0, sector: sector, refLen: sector ? r + 20 : 0,
        bisector: [bx, by], labelBox: box, push: push, shift: shift, label: label, deg: deg,
        line: [x1, y1, x2, y2], dimBox: obstacles[1] }
}
function drawPlayerAngle(l)
{
    const g = playerAngleGeom(l)
    if (!g)
        return null
    const [x1, y1] = g.vertex
    if (g.sector)
    {
        ctx.save()
        ctx.strokeStyle = THEME.soft; ctx.fillStyle = THEME.soft
        ctx.globalAlpha = .6; ctx.lineWidth = 1
        ctx.setLineDash([6, 3, 1, 3])
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1 + g.refLen, y1); ctx.stroke()
        ctx.setLineDash([])
        ctx.globalAlpha = .10
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.arc(x1, y1, g.r, g.a0, g.a1, g.ccw); ctx.closePath(); ctx.fill()
        ctx.globalAlpha = .6
        ctx.beginPath(); ctx.arc(x1, y1, g.r, g.a0, g.a1, g.ccw); ctx.stroke()
        ctx.restore()
    }
    ctx.save()
    ctx.globalAlpha = .7
    const b = g.labelBox
    annotText(g.label, b.x + b.w / 2, b.y + b.h / 2, PLAYER_ANGLE_FONT, THEME.soft)
    ctx.restore()
    return g.label
}
window.playerAngleGeoms = function()
{
    return lines.filter(l => l.type == 'player').map(l => playerAngleGeom(l))
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
    // orient left -> right so the label reads upright and the offset sits above the line
    const [x1, y1, x2, y2] = orientLeftRight(l)
    if (Math.hypot(x2 - x1, y2 - y1) < 1)
        return null
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
const TARGET_LABEL_FONT = 26
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
    // TASK-263: the first of (sx, sy), (-sx, sy), (sx, -sy), (-sx, -sy) whose label stays in the field and clear of
    // the fixed labels (fixedLabelBoxes); none free -> the first
    ctx.save(); ctx.font = TARGET_LABEL_FONT + 'px ' + THEME.fontStack
    const tw = ctx.measureText('target').width
    ctx.restore()
    const fixed = fixedLabelBoxes()
    const labelBox = (dx, dy) =>
    {
        const lx = tx + dx * 76, ly = ty + dy * 60
        return dx > 0 ? [lx, ly - TARGET_LABEL_FONT / 2, lx + tw, ly + TARGET_LABEL_FONT / 2] : [lx - tw, ly - TARGET_LABEL_FONT / 2, lx, ly + TARGET_LABEL_FONT / 2]
    }
    const free = ([dx, dy]) => { const b = labelBox(dx, dy)
        return b[0] >= 4 && b[2] <= GAME_W - 4 && b[1] >= 0 && b[3] <= GAME_H && !fixed.some(f => boxesTouch(b, f)) }
    const pick = [[sx, sy], [-sx, sy], [sx, -sy], [-sx, -sy]].find(free)
    if (pick) [sx, sy] = pick
    const ex = tx + sx * 70, ey = ty + sy * 60
    const R = sketchRng(sketchSeed([x, y, tx, ty, 11]))
    ctx.save()
    ctx.globalAlpha = .8
    handLine(ctx, R, tx + sx * 6, ty + sy * 5, ex, ey, THEME.soft, 1, 1, 0.5, 0)
    ctx.fillStyle = THEME.soft
    ctx.beginPath(); ctx.arc(tx + sx * 6, ty + sy * 5, 2, 0, Math.PI * 2); ctx.fill()
    ctx.restore()
    annotText('target', ex + sx * 6, ey, TARGET_LABEL_FONT, THEME.ink, 0, sx > 0 ? 'left' : 'right')
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
    const fixed = fixedLabelBoxes()
    let box = null, push = 0, shift = 0
    for (push = 0; push <= CALLOUT_PUSH_MAX; push += 2)
    {
        box = boxAt(x1 + bx * (r + CALLOUT_LABEL_GAP + push), y1 + by * (r + CALLOUT_LABEL_GAP + push))
        if (!calloutBoxBlocked(box, band, fixed))
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
            if (!calloutBoxBlocked(box, band, fixed))
                break
        }
    }
    return { vertex: [x1, y1], r: r, a0: a0, a1: a0 + sweep, ccw: sweep < 0, bisector: [bx, by],
        labelBox: box, push: push, shift: shift, label: label, deg: deg, solidNormal: n, line: [x1, y1, x2, y2] }
}
// true when the box crosses the line segment / hatch parallelogram band, or leaves the field
// (TASK-263: or touches a fixed label: the start marker's 'start' or a portal label)
function calloutBoxBlocked(b, band, fixed = fixedLabelBoxes())
{
    if (b.x < 0 || b.y < 0 || b.x + b.w > GAME_W || b.y + b.h > GAME_H)
        return true
    const B = [b.x, b.y, b.x + b.w, b.y + b.h]
    return convexOverlap(boxPoly(B), band) || fixed.some(f => boxesTouch(B, f))
}
function boxPoly(b)
{
    return [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]
}
function boxesTouch(a, b, pad = 2)
{
    return a[0] < b[2] + pad && b[0] < a[2] + pad && a[1] < b[3] + pad && b[1] < a[3] + pad
}
// TASK-263: [x0, y0, x1, y1] of the labels with a fixed place on the current level, which the angle callout and the
// target leader keep clear of: 'start' (startLabelPos, drawn before the run) and the portal labels (portalLabelPos)
function fixedLabelBoxes()
{
    const L = curLevel(), out = [startLabelPos(L.ballX, L.ballY).box]
    const P = currentPortals()
    if (P)
        P.forEach((p, i) =>
        {
            const label = PORTAL_STYLE[i % 2].label, lp = portalLabelPos(p, label)
            ctx.save(); ctx.font = PORTAL_LABEL_FONT + 'px ' + THEME.fontStack
            const w = ctx.measureText(label).width
            ctx.restore()
            out.push([lp.x - w / 2, lp.y - PORTAL_LABEL_FONT, lp.x + w / 2, lp.y + 6])
        })
    return out
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
            const g = drawPlayerAngle(lines[i])
            if (g) labels.push(g)
        }
    lastAnnotationLabels = labels
}
function annotationLabels()
{
    return lastAnnotationLabels.slice()
}
window.annotationLabels = annotationLabels
