// Level editor (opened from the pause menu's 'editor' button).
//
// editorMode = true: the game's clicks, the path preview and physics are off; draw() shows the
// working copy of levels[thisLevel] (lines, flag, ball start, portals) and the toolbar.
// Working copy shape: {ballX, ballY, flagX, flagY, flagRotate, lineK, lines: [Line], portals: [] | [A, B]}.
// 'exit' writes the copy back to levels[thisLevel] (this session only) and reloads the level.
let editorMode = false
let editor = { tool: 'select', level: null, lastAction: null, actions: 0, mouse: null, pending: null, drag: null, flagPoly: null,
               portalPending: null, selected: null, error: null }
const EDITOR_DELETE_LINE_DIST = 8     // delete tool: max distance to a line segment
const EDITOR_DELETE_PORTAL_DIST = 12  // delete tool: max distance to a portal opening (c ± h·t)
const EDITOR_PICK_DIST = 20           // select tool: max distance to flag anchor / ball start / portal centre
const EDITOR_FLAG_STEP = Math.PI / 12 // 'flag ⟲' / 'flag ⟳' rotation step
const EDITOR_MAX_LINEK = 5
const EDITOR_PORTAL_ANGLE = -Math.PI / 2 // default angle of a placed portal (opening horizontal, front up)
const EDITOR_PORTAL_H = 45
const EDITOR_PORTAL_CLEAR = 2            // level lines must stay > ball.radius + 2 px from an opening
const EDITOR_ERROR_MS = 2000             // how long the handwritten error text stays
const EDITOR_ERROR_POS = { x: 30, y: 100, size: 28 } // left / alphabetic baseline of the error text

// Toolbar: glass panel at the top-left, clear of the top-right HUD.
// kind 'tool' = selectable tool (editor.tool), 'action' = one-shot action (editor.lastAction),
// 'value' = lineK display (no hit area).
const EDITOR_BAR = { x: 30, y: 22, h: 38, gap: 6, pad: 8 }
const EDITOR_BUTTONS = (function()
{
    const spec = [
        ['select', 'tool', 'select', 70], ['line', 'tool', 'line', 56], ['portal', 'tool', 'portal', 70],
        ['delete', 'tool', 'delete', 70], ['flagCCW', 'action', 'flag', 70], ['flagCW', 'action', 'flag', 70],
        ['linesDec', 'action', 'lines −', 66], ['lineK', 'value', '', 36], ['linesInc', 'action', 'lines +', 66],
        ['play', 'action', 'play', 56], ['export', 'action', 'export', 70], ['import', 'action', 'import', 70],
        ['new', 'action', 'new', 50], ['exit', 'action', 'exit', 50]
    ]
    let x = EDITOR_BAR.x
    return spec.map(function(s)
    {
        const b = { id: s[0], kind: s[1], label: s[2], x: x, y: EDITOR_BAR.y, w: s[3], h: EDITOR_BAR.h }
        x += s[3] + EDITOR_BAR.gap
        return b
    })
})()
// [x, y, w, h] of the toolbar panel
function editorBarRect()
{
    const last = EDITOR_BUTTONS[EDITOR_BUTTONS.length - 1], p = EDITOR_BAR.pad
    return [EDITOR_BAR.x - p, EDITOR_BAR.y - p, last.x + last.w - EDITOR_BAR.x + 2 * p, EDITOR_BAR.h + 2 * p]
}

// Pause-menu 'editor' button: right part of the third level-grid row (squares 12-15 are unused;
// levelRectXY(10) is the only square in that row), clear of resume/restart, the grid and the logo.
function editorButtonRect()
{
    const w = menuTextRect[0], h = menuTextRect[1]
    return [menuCoords[0] + menuSize[0] - rectMarginLeft - w, menuCoords[1] + rectMarginTop + 2 * 60, w, h]
}
function inEditorButton(coords)
{
    const r = editorButtonRect()
    return collisionWithRect(coords[0], coords[1], r[0], r[1], r[0] + r[2], r[1] + r[3])
}

function editorCloneLevel(L)
{
    return {
        ballX: L.ballX, ballY: L.ballY, flagX: L.flagX, flagY: L.flagY,
        flagRotate: L.flagRotate, lineK: L.lineK,
        lines: L.lines.map(l => new Line(l.posX, l.posY, l.posX2, l.posY2, l.radius, l.color, l.type)),
        portals: (L.portals || []).map(p => Object.assign({}, p))
    }
}

function editorOpen()
{
    drawMenu = false
    drawMenuIcon = true
    physics = false
    line = false
    editor.level = editorCloneLevel(levels[thisLevel])
    editor.tool = 'select'
    editor.lastAction = null
    editor.pending = null
    editor.drag = null
    editor.portalPending = null
    editor.selected = null
    editor.error = null
    editor.flagPoly = editorFlagPolygon(editor.level.flagRotate)
    editorMode = true
}

// Write the working copy back to levels[thisLevel] (session only) and reload the level
function editorExit()
{
    const L = levels[thisLevel], W = editorCloneLevel(editor.level)
    L.ballX = W.ballX; L.ballY = W.ballY
    L.flagX = W.flagX; L.flagY = W.flagY; L.flagRotate = W.flagRotate
    L.lineK = W.lineK
    L.lines = W.lines
    if (W.portals.length)
        L.portals = W.portals
    else
        delete L.portals
    editorMode = false
    editor.level = null
    editor.pending = null
    editor.drag = null
    editor.portalPending = null
    editor.selected = null
    editor.error = null
    editor.flagPoly = null
    levelChoosed(thisLevel)
}

function editorButtonAt(coords)
{
    for (const b of EDITOR_BUTTONS)
        if (b.kind != 'value' && collisionWithRect(coords[0], coords[1], b.x, b.y, b.x + b.w, b.y + b.h))
            return b
    return null
}

// All clicks while editorMode is on end up here (handleClick returns right after)
function editorClick(coords)
{
    const b = editorButtonAt(coords)
    if (!b)
    {
        const R = editorBarRect()
        if (collisionWithRect(coords[0], coords[1], R[0], R[1], R[0] + R[2], R[1] + R[3]))
            return // toolbar panel background
        if (editor.tool == 'line')
            editorLineClick(coords)
        else if (editor.tool == 'portal')
            editorPortalClick(coords)
        else if (editor.tool == 'delete')
            editorDeleteAt(coords)
        return
    }
    if (b.kind == 'tool')
    {
        editor.tool = b.id
        editor.pending = null
        editor.portalPending = null
        if (b.id != 'select')
            editor.selected = null
        return
    }
    editor.lastAction = b.id
    editor.actions++
    const W = editor.level
    if ((b.id == 'flagCCW' || b.id == 'flagCW') && editorSelectedPortal())
        editorRotatePortal(editorSelectedPortal(), b.id == 'flagCW' ? EDITOR_FLAG_STEP : -EDITOR_FLAG_STEP)
    else if (b.id == 'flagCCW' || b.id == 'flagCW')
    {
        W.flagRotate += b.id == 'flagCW' ? EDITOR_FLAG_STEP : -EDITOR_FLAG_STEP
        editor.flagPoly = editorFlagPolygon(W.flagRotate)
    }
    else if (b.id == 'linesDec' || b.id == 'linesInc')
        W.lineK = Math.max(0, Math.min(EDITOR_MAX_LINEK, W.lineK + (b.id == 'linesInc' ? 1 : -1)))
    else if (b.id == 'exit')
        editorExit()
}

function editorInBar(coords)
{
    const R = editorBarRect()
    return collisionWithRect(coords[0], coords[1], R[0], R[1], R[0] + R[2], R[1] + R[3])
}

// Select tool: the nearest of flag anchor, ball start and portal centres within EDITOR_PICK_DIST
function editorPickAt(coords)
{
    const W = editor.level, x = coords[0], y = coords[1]
    const cand = [['flag', 0, W.flagX, W.flagY], ['ball', 0, W.ballX, W.ballY]]
    W.portals.forEach((P, i) => cand.push(['portal', i, P.x, P.y]))
    let best = null, bestD = Infinity
    for (const c of cand)
    {
        const d = Math.hypot(x - c[2], y - c[3])
        if (d <= EDITOR_PICK_DIST && d < bestD) { best = c; bestD = d }
    }
    return best
}

// mousedown / touchstart in editor mode: start dragging the picked object (select tool only).
// The grab offset is kept, so the object moves by exactly the mouse delta.
function editorMouseDown(coords)
{
    editor.drag = null
    if (editor.tool != 'select' || editorInBar(coords))
        return
    const c = editorPickAt(coords)
    // selection: a portal picked with the select tool (⟲ / ⟳ then rotate it); anything else clears it
    editor.selected = c && c[0] == 'portal' ? { kind: 'portal', i: c[1] } : null
    if (c)
        editor.drag = { kind: c[0], i: c[1], dx: c[2] - coords[0], dy: c[3] - coords[1], x0: c[2], y0: c[3] }
}

function editorDragTo(coords)
{
    const d = editor.drag, W = editor.level
    const x = coords[0] + d.dx, y = coords[1] + d.dy
    if (d.kind == 'flag') { W.flagX = x; W.flagY = y }
    else if (d.kind == 'ball') { W.ballX = x; W.ballY = y }
    else { W.portals[d.i].x = x; W.portals[d.i].y = y }
}

// mouseup / touchend: drop the dragged object at the release point
function editorMouseUp(coords)
{
    if (!editor.drag)
        return
    const d = editor.drag
    editorDragTo(coords)
    editor.drag = null
    if (d.kind == 'portal')
    {
        const P = editor.level.portals[d.i]
        if (editorPortalBlocked(P))
        {
            P.x = d.x0; P.y = d.y0 // refused drop: back to where it was picked up
            editorShowError('portal too close to a line')
        }
    }
}

function editorSelectedPortal()
{
    const s = editor.selected
    return s && s.kind == 'portal' ? editor.level.portals[s.i] || null : null
}

// Distance rule (same as TASK-027's design check): every level line must stay farther than
// ball.radius + EDITOR_PORTAL_CLEAR from the portal opening c ± h·t (rims included)
function editorPortalLineDist(P)
{
    const r = portalRims(P)
    let m = Infinity
    for (const l of editor.level.lines)
        m = Math.min(m, segSegDist(l.posX, l.posY, l.posX2, l.posY2, r[0][0], r[0][1], r[1][0], r[1][1]))
    return m
}
function editorPortalBlocked(P)
{
    return editorPortalLineDist(P) <= ball.radius + EDITOR_PORTAL_CLEAR
}

function editorNewPortal(coords, name)
{
    return { x: coords[0], y: coords[1], angle: EDITOR_PORTAL_ANGLE, h: EDITOR_PORTAL_H, name: name }
}

// Portal tool: 1st click places A (pending), 2nd places B; the pair then replaces the existing pair
// (at most one pair per level). A placement too close to a level line is refused (state kept).
function editorPortalClick(coords)
{
    const P = editorNewPortal(coords, editor.portalPending ? 'B' : 'A')
    if (editorPortalBlocked(P))
    {
        editorShowError('portal too close to a line')
        return false
    }
    if (!editor.portalPending)
    {
        editor.portalPending = P
        return true
    }
    editor.level.portals = [editor.portalPending, P]
    editor.portalPending = null
    editor.selected = null
    return true
}

// ⟲ / ⟳ with a selected portal: rotate it by ∓PI/12; refused (angle kept) when it would hit a line
function editorRotatePortal(P, da)
{
    const a = P.angle
    P.angle += da
    if (editorPortalBlocked(P))
    {
        P.angle = a
        editorShowError('portal too close to a line')
    }
}

function editorShowError(text)
{
    editor.error = { text: text, until: performance.now() + EDITOR_ERROR_MS }
}

// [x, y, w, h] box that holds the error text (for tests; the text is left-aligned at EDITOR_ERROR_POS)
function editorErrorRect()
{
    const e = EDITOR_ERROR_POS
    return [e.x, e.y - e.size, 360, e.size + 10]
}

function editorDrawError()
{
    const e = editor.error
    if (!e)
        return
    if (performance.now() > e.until)
    {
        editor.error = null
        return
    }
    const p = EDITOR_ERROR_POS
    ctx.save()
    ctx.font = '700 ' + p.size + 'px ' + THEME.fontStack
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'
    ctx.fillStyle = THEME.coral; ctx.shadowColor = 'rgba(255,106,85,.9)'; ctx.shadowBlur = 10
    ctx.fillText(e.text, p.x, p.y)
    ctx.restore()
}

// Dashed ring around the selected portal (select tool)
function editorDrawSelection()
{
    const P = editorSelectedPortal()
    if (!P || editor.tool != 'select')
        return
    ctx.save()
    ctx.strokeStyle = THEME.cyan; ctx.lineWidth = 1.4; ctx.setLineDash([5, 5])
    ctx.shadowColor = THEME.cyan; ctx.shadowBlur = 6
    ctx.beginPath(); ctx.arc(P.x, P.y, P.h + 18, 0, Math.PI * 2); ctx.stroke()
    ctx.restore()
}

// Line tool: first click = start, second click = end (both snapped to an existing endpoint of the
// working copy with dotСorrection); appends a level line. Zero-length lines are ignored.
function editorLineClick(coords)
{
    const W = editor.level
    const c = dotСorrection(coords[0], coords[1], dotRadius, W.lines)
    if (!editor.pending)
    {
        editor.pending = [c[0], c[1]]
        return
    }
    const p = editor.pending
    editor.pending = null
    if (p[0] == c[0] && p[1] == c[1])
        return
    W.lines.push(new Line(p[0], p[1], c[0], c[1], dotRadius, levelLineColor, 'line'))
}

// Delete tool: removes the single nearest line within 8 px, or the portal pair when a portal
// opening is within 12 px; the nearest candidate wins. Elsewhere nothing is removed.
function editorDeleteAt(coords)
{
    const W = editor.level, x = coords[0], y = coords[1]
    let best = null, bestD = Infinity
    W.lines.forEach(function(l, i)
    {
        const d = pointSegDist(x, y, l.posX, l.posY, l.posX2, l.posY2)
        if (d <= EDITOR_DELETE_LINE_DIST && d < bestD) { best = ['line', i]; bestD = d }
    })
    for (const P of W.portals)
    {
        const r = portalRims(P)
        const d = pointSegDist(x, y, r[0][0], r[0][1], r[1][0], r[1][1])
        if (d <= EDITOR_DELETE_PORTAL_DIST && d < bestD) { best = ['portal']; bestD = d }
    }
    if (!best)
        return false
    if (best[0] == 'line')
        W.lines.splice(best[1], 1)
    else
    {
        W.portals = []
        editor.selected = null
    }
    return true
}

function editorMouseMove(coords)
{
    editor.mouse = coords
    if (editor.drag)
        editorDragTo(coords)
}

// Flag polygon of the working copy (same pointRotation path as levelChoosed)
function editorFlagPolygon(rot)
{
    return flagCoords.map(c => pointRotation(c[0], c[1], rot))
}

function editorDraw()
{
    const W = editor.level
    for (const l of W.lines)
        l.draw()
    const saved = flag
    flag = editor.flagPoly
    drawFlag(W.flagX, W.flagY, THEME.ink, THEME.coral)
    flag = saved
    drawPortals(W.portals)
    if (editor.portalPending)
    {
        // placed A waiting for its partner (the existing pair stays until B is placed)
        drawPortal(editor.portalPending, PORTAL_STYLE[0])
    }
    editorDrawSelection()
    drawStartMarker(W.ballX, W.ballY)
    Ball.prototype.draw.call({ posX: W.ballX, posY: W.ballY, radius: ball.radius })
    if (editor.pending && editor.mouse)
        drawNewLine({ posX: editor.pending[0], posY: editor.pending[1], posX2: editor.mouse[0], posY2: editor.mouse[1] })
    editorDrawToolbar()
    editorDrawError()
}

// Small hand-drawn rotation arrow (dir -1 counter-clockwise, +1 clockwise)
function editorRotIcon(cx, cy, dir, color)
{
    const r = 7, a0 = -Math.PI * 0.9, a1 = Math.PI * 0.4
    ctx.save()
    ctx.strokeStyle = color; ctx.lineWidth = 1.6; ctx.lineCap = 'round'
    ctx.beginPath()
    if (dir > 0)
        ctx.arc(cx, cy, r, a0, a1)
    else
        ctx.arc(cx, cy, r, Math.PI - a0, Math.PI - a1, true)
    ctx.stroke()
    const end = dir > 0 ? a1 : Math.PI - a1
    const ex = cx + r * Math.cos(end), ey = cy + r * Math.sin(end)
    arrowHead(ctx, ex, ey, end + dir * Math.PI / 2, 5, color)
    ctx.restore()
}

function editorDrawToolbar()
{
    const R = editorBarRect()
    glassPanel(R[0], R[1], R[2], R[3])
    for (const b of EDITOR_BUTTONS)
    {
        const cx = b.x + b.w / 2, cy = b.y + b.h / 2
        if (b.kind == 'value')
        {
            menuLabel(String(editor.level.lineK), cx, cy, 26, THEME.coral)
            continue
        }
        const active = b.kind == 'tool' && editor.tool == b.id
        ctx.save()
        ctx.fillStyle = active ? 'rgba(255,106,85,0.22)' : 'rgba(130,210,255,0.06)'
        ctx.fillRect(b.x, b.y, b.w, b.h)
        ctx.strokeStyle = active ? THEME.coral : THEME.cyan
        ctx.lineWidth = active ? 2 : 1.2
        ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = active ? 10 : 4
        ctx.strokeRect(b.x, b.y, b.w, b.h)
        ctx.restore()
        const col = active ? THEME.coral : THEME.ink
        if (b.id == 'flagCCW' || b.id == 'flagCW')
        {
            menuLabel(b.label, cx - 9, cy, 24, col)
            editorRotIcon(cx + 21, cy, b.id == 'flagCW' ? 1 : -1, col)
        }
        else
            menuLabel(b.label, cx, cy, 24, col)
    }
}
