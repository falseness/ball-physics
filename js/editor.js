// Level editor (opened from the pause menu's 'editor' button).
//
// editorMode = true: the game's clicks, the path preview and physics are off; draw() shows the
// working copy of levels[thisLevel] (lines, flag, ball start, portals) and the toolbar.
// Working copy shape: {ballX, ballY, flagX, flagY, flagRotate, lineK, lines: [Line], portals: [] | [A, B]}.
// 'exit' writes the copy back to levels[thisLevel] (this session only) and reloads the level.
// 'play' play-tests a clone of the copy as `playtestLevel` (levels[] untouched); the HUD 'edit'
// box or the completion window's 'editor' button return to the editor with the copy unchanged.
let editorMode = false
let playtestLevel = null // level object being play-tested (null = normal play)
// The level the game is playing: the play-test level or levels[thisLevel]
function curLevel()
{
    return playtestLevel || levels[thisLevel]
}
let editor = { tool: 'select', level: null, lastAction: null, actions: 0, mouse: null, pending: null, drag: null, flagPoly: null,
               portalPending: null, selected: null, error: null }
const EDITOR_DELETE_LINE_DIST = 8     // delete tool: max distance to a line segment
const EDITOR_DELETE_PORTAL_DIST = 12  // delete tool: max distance to a portal opening (c ± h·t)
const EDITOR_PICK_DIST = 20           // select tool: max distance to flag anchor / ball start / portal centre
const EDITOR_PICK_LINE_DIST = 8       // select tool: max distance to a line segment (no point object in reach)
const EDITOR_PICK_END_DIST = 12       // select tool: max distance to a line endpoint (drags that end only)
const EDITOR_LINE_SEL_PAD = 10        // select tool: dashed capsule distance around a selected line
const EDITOR_FLAG_STEP = Math.PI / 12 // 'flag ⟲' / 'flag ⟳' rotation step
const EDITOR_MAX_LINEK = 5
const EDITOR_PORTAL_LINE_DIST = 20       // portal tool: max distance from the click to a level line
const EDITOR_PORTAL_H = PORTAL_DEFAULT_H   // h of a newly placed portal; 'size −' / 'size +' change it afterwards
const EDITOR_PORTAL_H_STEP = 15           // 'size −' / 'size +' step of h (both portals of the pair)
const EDITOR_PORTAL_H_MIN = 30
const EDITOR_PORTAL_H_MAX = 135
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
        ['portalSmaller', 'action', 'size −', 62], ['portalBigger', 'action', 'size +', 62],
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

// Pause-menu 'editor' button: right end of the 'Levels' heading row, between the restart button
// (bottom at +435) and the level grid (top at +rectMarginTop). Independent of levels.length, so it
// never collides with a level square (the grid's 3 rows hold up to 15 levels) and fits the
// 34 px 'editor' label (~65 px) with padding.
const EDITOR_BUTTON_W = 120, EDITOR_BUTTON_H = 40
function editorButtonRect()
{
    const right = menuSize[0] - rectMarginLeft, cy = 495  // heading centre: 335 + 85 * 2 - 10
    return [menuCoords[0] + right - EDITOR_BUTTON_W, menuCoords[1] + cy - EDITOR_BUTTON_H / 2, EDITOR_BUTTON_W, EDITOR_BUTTON_H]
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
    else if ((b.id == 'flagCCW' || b.id == 'flagCW') && editorSelectedLine())
        editorRotateLine(editorSelectedLine(), b.id == 'flagCW' ? EDITOR_FLAG_STEP : -EDITOR_FLAG_STEP)
    else if (b.id == 'flagCCW' || b.id == 'flagCW')
    {
        W.flagRotate += b.id == 'flagCW' ? EDITOR_FLAG_STEP : -EDITOR_FLAG_STEP
        editor.flagPoly = editorFlagPolygon(W.flagRotate)
    }
    else if (b.id == 'portalSmaller' || b.id == 'portalBigger')
        editorResizePortals(b.id == 'portalBigger' ? EDITOR_PORTAL_H_STEP : -EDITOR_PORTAL_H_STEP)
    else if (b.id == 'linesDec' || b.id == 'linesInc')
        W.lineK = Math.max(0, Math.min(EDITOR_MAX_LINEK, W.lineK + (b.id == 'linesInc' ? 1 : -1)))
    else if (b.id == 'new')
        editorNewLevel()
    else if (b.id == 'play')
        editorStartPlaytest()
    else if (b.id == 'export')
        editorExport()
    else if (b.id == 'import')
        editorImportOpen()
    else if (b.id == 'exit')
        editorExit()
}

// 'new': an empty working copy (ball start top-left, flag bottom-right, lineK 1, no lines/portals)
const EDITOR_NEW_LEVEL = { ballX: 200, ballY: 200, flagX: 1000, flagY: 600, flagRotate: 0, lineK: 1 }
function editorNewLevel()
{
    editor.level = Object.assign({}, EDITOR_NEW_LEVEL, { lines: [], portals: [] })
    editor.pending = null
    editor.drag = null
    editor.portalPending = null
    editor.selected = null
    editor.flagPoly = editorFlagPolygon(editor.level.flagRotate)
}

// 'play': load a clone of the working copy as playtestLevel and switch to normal play.
// editor.level itself is kept as is for the way back.
function editorStartPlaytest()
{
    editor.pending = null
    editor.drag = null
    editor.portalPending = null
    editor.error = null
    playtestLevel = editorCloneLevel(editor.level)
    editorMode = false
    drawMenu = false
    drawMenuIcon = true
    levelCompletedWindow = false
    line = false
    levelChoosed(thisLevel)
}

// HUD 'edit' box (play-test only): left of the play box, same size and style
function editIconRect()
{
    return [menuIconRect[0][0] - 146, menuIconRect[0][1], menuIconRect[1][0], menuIconRect[1][1]]
}
function inEditIcon(coords)
{
    const r = editIconRect()
    return collisionWithRect(coords[0], coords[1], r[0], r[1], r[0] + r[2], r[1] + r[3])
}
function drawEditIcon()
{
    if (!playtestLevel)
        return
    const r = editIconRect()
    ctx.save()
    hudBox(r[0], r[1])
    menuLabel('edit', r[0] + r[2] / 2, r[1] + r[3] / 2, 30)
    ctx.restore()
}

// Leave the play-test and go back to the editor; the working copy was never touched
function editorEndPlaytest()
{
    playtestLevel = null
    levelCompletedWindow = false
    drawMenu = false
    drawMenuIcon = true
    line = false
    levelChoosed(thisLevel)
    editorMode = true
}

function editorInBar(coords)
{
    const R = editorBarRect()
    return collisionWithRect(coords[0], coords[1], R[0], R[1], R[0] + R[2], R[1] + R[3])
}

// Select tool: the nearest of flag anchor, ball start and portal centres within EDITOR_PICK_DIST;
// with none in reach, the nearest line endpoint within EDITOR_PICK_END_DIST (['lineEnd', i, x, y, end]),
// else the nearest level line within EDITOR_PICK_LINE_DIST of its segment
// (['line', i, x, y] with the pointer as the grab point)
function editorPickAt(coords)
{
    const W = editor.level, x = coords[0], y = coords[1]
    const cand = [['flag', 0, W.flagX, W.flagY], ['ball', 0, W.ballX, W.ballY]]
    editorPortals().forEach((P, i) => cand.push(['portal', i, P.x, P.y]))
    let best = null, bestD = Infinity
    for (const c of cand)
    {
        const d = Math.hypot(x - c[2], y - c[3])
        if (d <= EDITOR_PICK_DIST && d < bestD) { best = c; bestD = d }
    }
    if (best)
        return best
    W.lines.forEach(function(l, i)
    {
        [[l.posX, l.posY], [l.posX2, l.posY2]].forEach(function(e, end)
        {
            const d = Math.hypot(x - e[0], y - e[1])
            if (d <= EDITOR_PICK_END_DIST && d < bestD) { best = ['lineEnd', i, e[0], e[1], end]; bestD = d }
        })
    })
    if (best)
        return best
    W.lines.forEach(function(l, i)
    {
        const d = pointSegDist(x, y, l.posX, l.posY, l.posX2, l.posY2)
        if (d <= EDITOR_PICK_LINE_DIST && d < bestD) { best = ['line', i, x, y]; bestD = d }
    })
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
    // selection: a portal (⟲ / ⟳ then rotate it) or a line picked with the select tool; anything else clears it
    editor.selected = c && (c[0] == 'portal' || c[0] == 'line' || c[0] == 'lineEnd') ?
        { kind: c[0] == 'lineEnd' ? 'line' : c[0], i: c[1] } : null
    if (c && c[0] == 'lineEnd')
    {
        const l = editor.level.lines[c[1]]
        editor.drag = { kind: 'lineEnd', i: c[1], end: c[4], dx: c[2] - coords[0], dy: c[3] - coords[1],
                        ends: [l.posX, l.posY, l.posX2, l.posY2] }
    }
    else if (c && c[0] == 'line')
    {
        const l = editor.level.lines[c[1]]
        editor.drag = { kind: 'line', i: c[1], mx: coords[0], my: coords[1], ends: [l.posX, l.posY, l.posX2, l.posY2] }
    }
    else if (c)
    {
        const P = c[0] == 'portal' ? editor.level.portals[c[1]] : null
        editor.drag = { kind: c[0], i: c[1], dx: c[2] - coords[0], dy: c[3] - coords[1], x0: c[2], y0: c[3],
                        u0: P ? P.u : undefined }
    }
}

// Pointer input in the letterbox bars maps to logical coords outside the field; every point the
// editor stores from the pointer is clamped to 0..EDITOR_FIELD.w x 0..EDITOR_FIELD.h, so its own
// export always passes editorLevelFromData
function editorClampToField(x, y)
{
    return [Math.min(Math.max(x, 0), EDITOR_FIELD.w), Math.min(Math.max(y, 0), EDITOR_FIELD.h)]
}

// Line drag: both endpoints move by the mouse delta, clamped so both stay inside the field
function editorDragLine(d, coords)
{
    const l = editor.level.lines[d.i], e = d.ends
    if (!l)
        return
    const F = EDITOR_FIELD
    const dx = Math.min(Math.max(coords[0] - d.mx, -Math.min(e[0], e[2])), F.w - Math.max(e[0], e[2]))
    const dy = Math.min(Math.max(coords[1] - d.my, -Math.min(e[1], e[3])), F.h - Math.max(e[1], e[3]))
    l.posX = e[0] + dx; l.posY = e[1] + dy; l.posX2 = e[2] + dx; l.posY2 = e[3] + dy
}
// Endpoint drag: only end d.end follows the mouse (grab offset kept), clamped to the field
function editorDragLineEnd(d, coords)
{
    const l = editor.level.lines[d.i]
    if (!l)
        return
    const [x, y] = editorClampToField(coords[0] + d.dx, coords[1] + d.dy)
    if (d.end == 0) { l.posX = x; l.posY = y }
    else { l.posX2 = x; l.posY2 = y }
}
// Endpoint drop: snap to another line's endpoint (dotСorrection, the line itself excluded); refused
// (true) when the line gets shorter than 1 px
function editorDropLineEnd(d)
{
    const W = editor.level, l = W.lines[d.i]
    if (!l)
        return false
    const others = W.lines.filter((o, j) => j != d.i)
    const x = d.end == 0 ? l.posX : l.posX2, y = d.end == 0 ? l.posY : l.posY2
    const c = dotСorrection(x, y, dotRadius, others)
    if (d.end == 0) { l.posX = c[0]; l.posY = c[1] }
    else { l.posX2 = c[0]; l.posY2 = c[1] }
    return Math.hypot(l.posX2 - l.posX, l.posY2 - l.posY) < 1
}
function editorLineRevert(d)
{
    const l = editor.level.lines[d.i]
    if (l)
        [l.posX, l.posY, l.posX2, l.posY2] = d.ends
}

function editorDragTo(coords)
{
    const d = editor.drag, W = editor.level
    if (d.kind == 'line')
        return editorDragLine(d, coords)
    if (d.kind == 'lineEnd')
        return editorDragLineEnd(d, coords)
    const [x, y] = editorClampToField(coords[0] + d.dx, coords[1] + d.dy)
    if (d.kind == 'flag') { W.flagX = x; W.flagY = y }
    else if (d.kind == 'ball') { W.ballX = x; W.ballY = y }
    else if (editorIsWallPortal(W.portals[d.i])) editorSlidePortal(W.portals[d.i], coords[0] + d.dx, coords[1] + d.dy)
    else { W.portals[d.i].x = x; W.portals[d.i].y = y }
}

// Wall-portal drag: u follows the projection of (x, y) onto the host line, clamped like portalResolve
function editorSlidePortal(P, x, y)
{
    const l = editor.level.lines[P.line]
    if (!l)
        return
    P.u = editorProjectU(l, x, y, P.h)
}

// Clamped line parameter u of the projection of (x, y) onto line l (portalClampU for an opening of half-width h)
function editorProjectU(l, x, y, h)
{
    const dx = l.posX2 - l.posX, dy = l.posY2 - l.posY, L2 = dx * dx + dy * dy
    const u = L2 > 0 ? ((x - l.posX) * dx + (y - l.posY) * dy) / L2 : 0.5
    return portalClampU(Math.min(Math.max(u, 0), 1), Math.sqrt(L2), h)
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
        const err = !P ? null : editorPortalBlocked(P) ? 'portal too close to a line' :
                    editorPortalsOverlap(editor.level.portals) ? 'portals overlap' : null
        if (err)
        {
            // refused drop: back to where it was picked up
            if (editorIsWallPortal(P)) P.u = d.u0
            else { P.x = d.x0; P.y = d.y0 }
            editorShowError(err)
        }
    }
    else if (d.kind == 'lineEnd' || d.kind == 'line')
    {
        if (d.kind == 'lineEnd' && editorDropLineEnd(d))
        {
            editorLineRevert(d) // degenerate (< 1 px) line: back to where it was picked up
            return
        }
        const err = editorLineEditError(d.i)
        if (err)
        {
            editorLineRevert(d) // refused drop: back to where it was picked up
            editorShowError(err)
        }
    }
}

// Check after line i was moved / rotated / had an endpoint dragged (the edit already applied).
// Wall portals hosted on line i follow it (they store {line, u, side}), so the edit is refused when
// the line gets shorter than an opening needs (2*h + 2*ball.radius), the line comes within the
// clearance of another portal's opening, a carried opening comes within the clearance of another
// line, or the carried pair overlaps on the line. null = the edit is allowed.
function editorLineEditError(i)
{
    const W = editor.level, l = W.lines[i]
    if (!l)
        return null
    const hosted = W.portals.filter(P => editorIsWallPortal(P) && P.line === i)
    const len = Math.hypot(l.posX2 - l.posX, l.posY2 - l.posY)
    if (hosted.some(P => len < 2 * P.h + 2 * ball.radius))
        return 'line too short for its portal'
    if (editorSegNearPortal(l.posX, l.posY, l.posX2, l.posY2, W.portals, i))
        return 'line too close to a portal'
    if (hosted.some(editorPortalBlocked))
        return 'portal too close to a line'
    if (hosted.length && editorPortalsOverlap(W.portals))
        return 'portals overlap'
    return null
}

// touchcancel (OS gesture, palm rejection...): no drop happened, so the dragged object goes back
// to where it was picked up (never left where the drop check would refuse it) and the drag ends
function editorCancelDrag()
{
    const d = editor.drag
    if (!d)
        return
    editor.drag = null
    const W = editor.level
    if (d.kind == 'flag') { W.flagX = d.x0; W.flagY = d.y0 }
    else if (d.kind == 'ball') { W.ballX = d.x0; W.ballY = d.y0 }
    else if (d.kind == 'line' || d.kind == 'lineEnd') editorLineRevert(d)
    else if (editorIsWallPortal(W.portals[d.i])) W.portals[d.i].u = d.u0
    else if (W.portals[d.i]) { W.portals[d.i].x = d.x0; W.portals[d.i].y = d.y0 }
}

function editorSelectedPortal()
{
    const s = editor.selected
    return s && s.kind == 'portal' ? editor.level.portals[s.i] || null : null
}

// Wall portal ({line, u, side}) vs a legacy free-standing one ({x, y, angle})
function editorIsWallPortal(P)
{
    return !!P && typeof P.line == 'number'
}
// The working copy's portals resolved against its own lines ({x, y, angle, h, ...})
function editorPortals()
{
    return portalResolveAll(editor.level.portals, editor.level.lines)
}

// Distance rule (same as TASK-027's design check): every level line must stay farther than
// ball.radius + EDITOR_PORTAL_CLEAR from the portal opening c ± h·t (rims included).
// A wall portal's own host line is skipped (the opening is cut into it).
function editorPortalLineDist(P)
{
    const R = portalResolve(P, editor.level.lines), r = portalRims(R)
    let m = Infinity
    editor.level.lines.forEach(function(l, i)
    {
        if (i !== R.line)
            m = Math.min(m, segSegDist(l.posX, l.posY, l.posX2, l.posY2, r[0][0], r[0][1], r[1][0], r[1][1]))
    })
    return m
}
function editorPortalBlocked(P)
{
    return editorPortalLineDist(P) <= ball.radius + EDITOR_PORTAL_CLEAR
}
// Same rule seen from the line side: segment (x1,y1)-(x2,y2) is within ball.radius +
// EDITOR_PORTAL_CLEAR of any portal opening in the list (line tool and import).
// lineIndex: the segment's index in `lines` (-1 = a new line); portals hosted on that line are skipped.
function editorSegNearPortal(x1, y1, x2, y2, portals, lineIndex = -1, lines = editor.level ? editor.level.lines : [])
{
    for (const P0 of portals)
    {
        if (editorIsWallPortal(P0) && P0.line === lineIndex)
            continue
        const P = portalResolve(P0, lines), r = portalRims(P)
        if (segSegDist(x1, y1, x2, y2, r[0][0], r[0][1], r[1][0], r[1][1]) <= ball.radius + EDITOR_PORTAL_CLEAR)
            return true
    }
    return false
}

// Portal tool: a wall portal {line, u, side, h, name} on the level line nearest to the click
// (within EDITOR_PORTAL_LINE_DIST): u = the clamped projection of the click, side = the side of
// the line the click is on (the front normal points towards the click). null = no line in reach.
function editorNewPortal(coords, name)
{
    const W = editor.level, x = coords[0], y = coords[1]
    let best = -1, bestD = Infinity
    W.lines.forEach(function(l, i)
    {
        const d = pointSegDist(x, y, l.posX, l.posY, l.posX2, l.posY2)
        if (d <= EDITOR_PORTAL_LINE_DIST && d < bestD) { best = i; bestD = d }
    })
    if (best < 0)
        return null
    const l = W.lines[best], dx = l.posX2 - l.posX, dy = l.posY2 - l.posY
    // n(side = +1) = (-ty, tx); the click's offset along it picks the side (0 = on the line: +1)
    const side = (x - l.posX) * -dy + (y - l.posY) * dx < 0 ? -1 : 1
    return { line: best, u: editorProjectU(l, x, y, EDITOR_PORTAL_H), side: side, h: EDITOR_PORTAL_H, name: name }
}

// Two wall portals on the same line whose openings u ± h/len overlap (touching counts)
function editorPortalsOverlap(list, lines = editor.level.lines)
{
    if (!list || list.length != 2 || !editorIsWallPortal(list[0]) || list[0].line !== list[1].line)
        return false
    const R = portalResolveAll(list, lines), l = lines[list[0].line]
    const len = Math.hypot(l.posX2 - l.posX, l.posY2 - l.posY)
    return Math.abs(R[0].u - R[1].u) * len <= R[0].h + R[1].h
}

// Portal tool: 1st click places A (pending), 2nd places B; the pair then replaces the existing pair
// (at most one pair per level). Refused (state kept): a click farther than EDITOR_PORTAL_LINE_DIST
// from every line, an opening too close to another level line, B overlapping A on the same line.
function editorPortalClick(coords)
{
    const P = editorNewPortal(coords, editor.portalPending ? 'B' : 'A')
    const err = !P ? 'portals go on lines' : editorPortalBlocked(P) ? 'portal too close to a line' :
                editor.portalPending && editorPortalsOverlap([editor.portalPending, P]) ? 'portals overlap' : null
    if (err)
    {
        editorShowError(err)
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

// ⟲ / ⟳ with a selected portal: a wall portal flips its side (front normal reversed, opening kept);
// a legacy free-standing one rotates by ∓PI/12, refused (angle kept) when it would hit a line
function editorRotatePortal(P, da)
{
    if (editorIsWallPortal(P))
    {
        P.side = P.side < 0 ? 1 : -1
        return
    }
    const a = P.angle
    P.angle += da
    if (editorPortalBlocked(P))
    {
        P.angle = a
        editorShowError('portal too close to a line')
    }
}

// 'size −' / 'size +' with a selected portal: h of BOTH portals of the pair (one shared size) changes
// by dh, limited to EDITOR_PORTAL_H_MIN..EDITOR_PORTAL_H_MAX (at a limit nothing changes, no error).
// A wall portal's u is re-clamped to the new h first; the change is refused (h and u of both kept,
// 'portal does not fit') when an opening plus ball.radius no longer fits on its host line, an opening
// comes within the clearance of another line, or the pair overlaps. No portal selected: no-op.
function editorResizePortals(dh)
{
    const W = editor.level, S = editorSelectedPortal()
    if (!S)
        return false
    const h = Math.min(EDITOR_PORTAL_H_MAX, Math.max(EDITOR_PORTAL_H_MIN, S.h + dh))
    if (W.portals.every(P => P.h === h))
        return false
    const old = W.portals.map(P => ({ h: P.h, u: P.u }))
    let fits = true
    for (const P of W.portals)
    {
        P.h = h
        if (!editorIsWallPortal(P))
            continue
        const l = W.lines[P.line], len = Math.hypot(l.posX2 - l.posX, l.posY2 - l.posY)
        if (len < 2 * (h + ball.radius))
            fits = false
        else
            P.u = portalClampU(P.u, len, h)
    }
    if (fits && (W.portals.some(editorPortalBlocked) || editorPortalsOverlap(W.portals)))
        fits = false
    if (!fits)
    {
        W.portals.forEach((P, i) => { P.h = old[i].h; P.u = old[i].u })
        editorShowError('portal does not fit')
        return false
    }
    return true
}

// ⟲ / ⟳ with a selected line: rotate it by ∓PI/12 around its midpoint (length kept, its wall portals
// turn with it); refused (line unchanged) when it leaves EDITOR_FIELD or editorLineEditError objects
function editorRotateLine(l, da)
{
    const mx = (l.posX + l.posX2) / 2, my = (l.posY + l.posY2) / 2
    const hx = (l.posX2 - l.posX) / 2, hy = (l.posY2 - l.posY) / 2
    const c = Math.cos(da), s = Math.sin(da)
    const rx = hx * c - hy * s, ry = hx * s + hy * c
    const x1 = mx - rx, y1 = my - ry, x2 = mx + rx, y2 = my + ry
    const F = EDITOR_FIELD
    const inField = (x, y) => x >= 0 && x <= F.w && y >= 0 && y <= F.h
    if (!inField(x1, y1) || !inField(x2, y2))
    {
        editorShowError('line would leave the field')
        return false
    }
    const old = [l.posX, l.posY, l.posX2, l.posY2]
    l.posX = x1; l.posY = y1; l.posX2 = x2; l.posY2 = y2
    const err = editorLineEditError(editor.level.lines.indexOf(l))
    if (err)
    {
        [l.posX, l.posY, l.posX2, l.posY2] = old
        editorShowError(err)
        return false
    }
    return true
}

// Delete / Backspace in the editor (no play-test) removes the selected line; other selections ignore the key
function editorKeyDown(event)
{
    if (!editorMode || playtestLevel || !editor.level || (event.key != 'Delete' && event.key != 'Backspace'))
        return
    const s = editor.selected
    if (!s || s.kind != 'line' || !editor.level.lines[s.i])
        return
    event.preventDefault()
    if (editor.drag)
        editorCancelDrag()
    editorRemoveLine(s.i)
    editor.selected = null
}
document.addEventListener('keydown', editorKeyDown)

function editorShowError(text, ms = EDITOR_ERROR_MS)
{
    editor.error = { text: text, until: performance.now() + ms }
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

function editorSelectedLine()
{
    const s = editor.selected
    return s && s.kind == 'line' ? editor.level.lines[s.i] || null : null
}

// Removes working-copy line i. Wall portals keep their host: a pair hosted (partly) on line i is
// removed with it, the remaining portals' line indices are shifted down past i.
function editorRemoveLine(i)
{
    const W = editor.level
    W.lines.splice(i, 1)
    if (W.portals.some(P => editorIsWallPortal(P) && P.line === i))
    {
        W.portals = []
        if (editor.selected && editor.selected.kind == 'portal')
            editor.selected = null
    }
    else
        for (const P of W.portals)
            if (editorIsWallPortal(P) && P.line > i)
                P.line--
}

// Dashed ring around the selected portal, dashed capsule around the selected line (select tool)
function editorDrawSelection()
{
    const s = editor.selected
    const P = s && s.kind == 'portal' && editor.level.portals[s.i] ? editorPortals()[s.i] : null
    const l = editorSelectedLine()
    if ((!P && !l) || editor.tool != 'select')
        return
    ctx.save()
    ctx.strokeStyle = THEME.cyan; ctx.lineWidth = 1.4; ctx.setLineDash([5, 5])
    ctx.shadowColor = THEME.cyan; ctx.shadowBlur = 6
    ctx.beginPath()
    if (P)
        ctx.arc(P.x, P.y, P.h + 18, 0, Math.PI * 2)
    else
    {
        const r = EDITOR_LINE_SEL_PAD, a = Math.atan2(l.posY2 - l.posY, l.posX2 - l.posX)
        ctx.arc(l.posX2, l.posY2, r, a - Math.PI / 2, a + Math.PI / 2)
        ctx.arc(l.posX, l.posY, r, a + Math.PI / 2, a + Math.PI * 1.5)
        ctx.closePath()
    }
    ctx.stroke()
    ctx.restore()
    if (P)
        editorDrawPortalSize(P)
}

// 'h = NN' next to the selected portal: in front of it (along its normal), just outside the dashed ring
function editorDrawPortalSize(P)
{
    const d = P.h + 18 + 22, F = EDITOR_FIELD
    const x = Math.min(Math.max(P.x + Math.cos(P.angle) * d, 50), F.w - 50)
    const y = Math.min(Math.max(P.y + Math.sin(P.angle) * d, 90), F.h - 20)
    menuLabel('h = ' + Math.round(P.h), x, y, 24, THEME.cyan)
}

// Line tool: first click = start, second click = end (both snapped to an existing endpoint of the
// working copy with dotСorrection); appends a level line. Zero-length lines are ignored; a line
// within ball.radius + EDITOR_PORTAL_CLEAR of a portal opening is refused (start point kept).
function editorLineClick(coords)
{
    const W = editor.level
    const k = editorClampToField(coords[0], coords[1])
    const c = dotСorrection(k[0], k[1], dotRadius, W.lines)
    if (!editor.pending)
    {
        editor.pending = [c[0], c[1]]
        return
    }
    const p = editor.pending
    if (p[0] == c[0] && p[1] == c[1])
    {
        editor.pending = null
        return
    }
    const portals = editor.portalPending ? W.portals.concat([editor.portalPending]) : W.portals
    if (editorSegNearPortal(p[0], p[1], c[0], c[1], portals))
    {
        editorShowError('line too close to a portal') // refused: keep the start point for another end
        return
    }
    editor.pending = null
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
    for (const P of editorPortals())
    {
        const r = portalRims(P)
        const d = pointSegDist(x, y, r[0][0], r[0][1], r[1][0], r[1][1])
        if (d <= EDITOR_DELETE_PORTAL_DIST && d < bestD) { best = ['portal']; bestD = d }
    }
    if (!best)
        return false
    if (best[0] == 'line')
        editorRemoveLine(best[1])
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
    const portals = editorPortals()
    drawLines(W.lines, W.lines, portals)
    const saved = flag
    flag = editor.flagPoly
    drawFlag(W.flagX, W.flagY, THEME.ink, THEME.coral)
    flag = saved
    drawPortals(portals)
    if (editor.portalPending)
    {
        // placed A waiting for its partner (the existing pair stays until B is placed)
        drawPortal(portalResolve(editor.portalPending, W.lines), PORTAL_STYLE[0])
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

// ---- Export / import (level.json) ----
// File format (stable key order, numbers as-is):
// {version: 2, ballX, ballY, flagX, flagY, flagRotate, lineK, lines: [[x1,y1,x2,y2], ...],
//  portals: [{line, u, side, h, name}, ...]}   (wall portals, `line` indexes `lines`)
// Import also accepts a version 1 file ({..., portals: [{x, y, angle, h}]}) when it has no portals;
// a version 1 file with portals is refused with 'old portal format'.
const EDITOR_FILE_VERSION = 2
const EDITOR_FIELD = { w: 1280, h: 800 }   // every point must lie inside 0..w x 0..h
const EDITOR_IMPORT_ERROR_MS = 3000

function editorLevelToJSON(W)
{
    return JSON.stringify({
        version: EDITOR_FILE_VERSION,
        ballX: W.ballX, ballY: W.ballY, flagX: W.flagX, flagY: W.flagY,
        flagRotate: W.flagRotate, lineK: W.lineK,
        lines: W.lines.map(l => [l.posX, l.posY, l.posX2, l.posY2]),
        portals: W.portals.map(P => ({ line: P.line, u: P.u, side: P.side, h: P.h, name: P.name }))
    })
}

// 'export': download the working copy as level.json (Blob + temporary <a download>)
function editorExport()
{
    const blob = new Blob([editorLevelToJSON(editor.level)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'level.json'
    a.style.display = 'none'
    // the synthetic click must not bubble to the game's document click handler (editorClick at (0,0))
    a.addEventListener('click', e => e.stopPropagation())
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// Parsed file -> working-copy level, or null when the file is not a valid level
// (version 2, or version 1 without portals)
function editorLevelFromData(d)
{
    const num = v => typeof v == 'number' && Number.isFinite(v)
    const inField = (x, y) => num(x) && num(y) && x >= 0 && x <= EDITOR_FIELD.w && y >= 0 && y <= EDITOR_FIELD.h
    if (!d || typeof d != 'object' || Array.isArray(d) || (d.version !== 1 && d.version !== EDITOR_FILE_VERSION))
        return null
    if (!inField(d.ballX, d.ballY) || !inField(d.flagX, d.flagY) || !num(d.flagRotate))
        return null
    if (!Number.isInteger(d.lineK) || d.lineK < 0 || d.lineK > EDITOR_MAX_LINEK)
        return null
    if (!Array.isArray(d.lines) || !Array.isArray(d.portals) || (d.portals.length != 0 && d.portals.length != 2))
        return null
    if (d.version === 1 && d.portals.length)
        return null // old free-standing portal format (editorImportText reports it)
    for (const l of d.lines)
        if (!Array.isArray(l) || l.length != 4 || !inField(l[0], l[1]) || !inField(l[2], l[3]))
            return null
    const lines = d.lines.map(l => new Line(l[0], l[1], l[2], l[3], dotRadius, levelLineColor, 'line'))
    for (const P of d.portals)
        if (!P || typeof P != 'object' || !Number.isInteger(P.line) || P.line < 0 || P.line >= lines.length ||
            !num(P.u) || P.u < 0 || P.u > 1 || (P.side !== 1 && P.side !== -1) || !num(P.h) || P.h <= 0)
            return null
    const portals = d.portals.map((P, i) => ({ line: P.line, u: P.u, side: P.side, h: P.h,
                                              name: typeof P.name == 'string' && P.name ? P.name : (i ? 'B' : 'A') }))
    if (editorPortalsOverlap(portals, lines))
        return null
    for (let i = 0; i < lines.length; i++)
        if (editorSegNearPortal(lines[i].posX, lines[i].posY, lines[i].posX2, lines[i].posY2, portals, i, lines))
            return null
    return {
        ballX: d.ballX, ballY: d.ballY, flagX: d.flagX, flagY: d.flagY,
        flagRotate: d.flagRotate, lineK: d.lineK, lines: lines, portals: portals
    }
}

// File text -> replaces the working copy (true), or leaves it unchanged and shows an error (false):
// 'old portal format' for a version 1 file with portals, 'invalid level file' otherwise. Never throws.
function editorImportText(text)
{
    let L = null, err = 'invalid level file'
    try
    {
        const d = JSON.parse(text)
        L = editorLevelFromData(d)
        if (!L && d && d.version === 1 && Array.isArray(d.portals) && d.portals.length)
            err = 'old portal format'
    }
    catch (e)
    {
        L = null
    }
    if (!L || !editorMode || !editor.level)
    {
        editorShowError(err, EDITOR_IMPORT_ERROR_MS)
        return false
    }
    editor.level = L
    editor.pending = null
    editor.drag = null
    editor.portalPending = null
    editor.selected = null
    editor.error = null
    editor.flagPoly = editorFlagPolygon(L.flagRotate)
    return true
}

// Hidden <input type=file accept='.json'> (created once, id editorImportFile)
function editorImportInput()
{
    let input = document.getElementById('editorImportFile')
    if (input)
        return input
    input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.id = 'editorImportFile'
    input.style.display = 'none'
    // input.click() from editorImportOpen must not bubble to the document click handler (editorClick at (0,0))
    input.addEventListener('click', e => e.stopPropagation())
    input.addEventListener('change', function()
    {
        const f = input.files && input.files[0]
        input.value = '' // the same file can be picked again
        if (!f)
            return
        f.text().then(editorImportText, () => editorShowError('invalid level file', EDITOR_IMPORT_ERROR_MS))
    })
    document.body.appendChild(input)
    return input
}

// 'import': open the file picker
function editorImportOpen()
{
    editorImportInput().click()
}
