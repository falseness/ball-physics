// Level editor (opened from the pause menu's 'editor' button).
//
// editorMode = true: the game's clicks, the play-mode path preview and physics are off (the editor
// draws its own live path preview of the working copy, editorPreviewUpdate); draw() shows the
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
               portalPending: null, selected: null, error: null, snap: false, barDrag: null, barDropAt: null }
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
const EDITOR_ERROR_MS = 2000             // how long the handwritten error text stays
const EDITOR_ERROR_POS = { x: 30, y: 100, size: 28 } // left / alphabetic baseline of the error text (follows the toolbar, editorBarMoveTo)

// Toolbar: glass panel at the top-left, clear of the top-right HUD.
// kind 'tool' = selectable tool (editor.tool), 'action' = one-shot action (editor.lastAction),
// 'toggle' = on/off switch (editor[id], e.g. editor.snap), 'value' = lineK display (no hit area).
const EDITOR_BAR = { x: 30, y: 22, h: 38, gap: 6, pad: 8 }
const EDITOR_BUTTONS = (function()
{
    const spec = [
        ['select', 'tool', 'select', 70], ['line', 'tool', 'line', 56], ['snap', 'toggle', 'snap', 56], ['portal', 'tool', 'portal', 70],
        ['delete', 'tool', 'delete', 70], ['flagCCW', 'action', 'flag', 70], ['flagCW', 'action', 'flag', 70],
        ['portalSmaller', 'action', 'size −', 62], ['portalBigger', 'action', 'size +', 62],
        ['linesDec', 'action', 'lines −', 66], ['lineK', 'value', '', 36], ['linesInc', 'action', 'lines +', 66],
        ['play', 'action', 'play', 56], ['export', 'action', 'export', 70], ['import', 'action', 'import', 70],
        ['new', 'action', 'new', 50], ['exit', 'action', 'exit', 50]
    ]
    let x = EDITOR_BAR.x
    return spec.map(function(s)
    {
        const b = { id: s[0], kind: s[1], label: s[2], x: x, y: EDITOR_BAR.y, w: s[3], h: EDITOR_BAR.h, ox: x - EDITOR_BAR.x }
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

// The toolbar can be dragged by its background (TASK-117); the position is saved through
// PLATFORM.storage (TASK-184; read at boot by index.html)
const EDITOR_BAR_DEFAULT = [EDITOR_BAR.x - EDITOR_BAR.pad, EDITOR_BAR.y - EDITOR_BAR.pad] // panel top-left
const EDITOR_BAR_EDGE = 14       // snapped panel distance from the top / bottom field edge
const EDITOR_BAR_SNAP = 24       // snap when the panel's top / bottom is this close to its snapped place
const EDITOR_BAR_STORE = 'bp.editorBar.v1'
// Move the panel so its rect's top-left is (x, y): kept fully inside the field, snapped to the top /
// bottom edge when close. Buttons are updated in place (same EDITOR_BUTTONS objects).
function editorBarMoveTo(x, y)
{
    const R = editorBarRect(), w = R[2], h = R[3]
    x = Math.min(Math.max(x, 0), GAME_W - w)
    y = Math.min(Math.max(y, 0), GAME_H - h)
    if (Math.abs(y - EDITOR_BAR_EDGE) <= EDITOR_BAR_SNAP)
        y = EDITOR_BAR_EDGE
    else if (Math.abs(y + h - (GAME_H - EDITOR_BAR_EDGE)) <= EDITOR_BAR_SNAP)
        y = GAME_H - EDITOR_BAR_EDGE - h
    EDITOR_BAR.x = x + EDITOR_BAR.pad
    EDITOR_BAR.y = y + EDITOR_BAR.pad
    for (const b of EDITOR_BUTTONS)
    {
        b.x = EDITOR_BAR.x + b.ox
        b.y = EDITOR_BAR.y
    }
    // error text: 32 px below the panel in the top half, 14 px above it in the bottom half
    EDITOR_ERROR_POS.x = x + EDITOR_BAR.pad
    EDITOR_ERROR_POS.y = y + h / 2 < GAME_H / 2 ? y + h + 32 : y - 14
}
// Last saved / loaded position (JSON string or null): entering the editor re-applies it without a
// storage read (reads are asynchronous through the facade)
let editorBarSaved = null
function editorBarSave()
{
    const R = editorBarRect()
    editorBarSaved = JSON.stringify({ x: R[0], y: R[1] })
    return PLATFORM.storage.setMany({ [EDITOR_BAR_STORE]: editorBarSaved })
}
// Apply editorBarSaved (missing / unparsable / non-finite -> default)
function editorBarApply()
{
    let pos = EDITOR_BAR_DEFAULT
    try
    {
        const v = JSON.parse(editorBarSaved)
        if (v && Number.isFinite(v.x) && Number.isFinite(v.y))
            pos = [v.x, v.y]
    }
    catch (e) {}
    editorBarMoveTo(pos[0], pos[1])
}
// values: the PLATFORM.storage.getMany result ({key: string | null}), read at boot (index.html)
function editorBarLoad(values)
{
    const v = values && values[EDITOR_BAR_STORE]
    editorBarSaved = typeof v === 'string' ? v : null
    editorBarApply()
}
editorBarLoad(null) // default position until boot applies the saved one

// 'editor' button shared by the pause menu and the level-completed window (same rect in both):
// top-right corner inside the logo frame (frame x +30..+370, y +70..+285), under the 'Ball physics'
// title (bottom ~+64) and above the logo drawing (line/ball start at y +120/+150). The old spot at
// the right end of the pause menu's 'Levels' row overlapped the win window's 'restart' button
// (+455..+505). Independent of levels.length (levels are picked on the route map since TASK-181) and fits the 34 px 'editor' label (~65 px).
const EDITOR_BUTTON_W = 120, EDITOR_BUTTON_H = 40
function editorButtonRect()
{
    const right = menuSize[0] - 30 - 10, top = 80
    return [menuCoords[0] + right - EDITOR_BUTTON_W, menuCoords[1] + top, EDITOR_BUTTON_W, EDITOR_BUTTON_H]
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
    editor.snap = false
    editor.lastAction = null
    editor.pending = null
    editor.drag = null
    editor.portalPending = null
    editor.selected = null
    editor.error = null
    editor.flagPoly = editorFlagPolygon(editor.level.flagRotate)
    editor.barDrag = null
    editor.barDropAt = null
    editorBarApply()
    editorPreviewClear()
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
    editorPreviewClear()
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
    const drop = editor.barDropAt
    editor.barDropAt = null
    if (drop && drop[0] == coords[0] && drop[1] == coords[1])
        return // the click that ends a toolbar drag (the drop may be outside the clamped panel)
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
    if (b.kind == 'toggle')
    {
        editor[b.id] = !editor[b.id] // 'snap': kept across tool changes and play-tests until the editor reopens
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
    editorPreviewClear()
}

// 'play': load a clone of the working copy as playtestLevel and switch to normal play.
// editor.level itself is kept as is for the way back.
function editorStartPlaytest()
{
    editor.pending = null
    editor.drag = null
    editor.portalPending = null
    editor.error = null
    editorPreviewClear()
    playtestLevel = editorCloneLevel(editor.level)
    editorMode = false
    drawMenu = false
    drawMenuIcon = true
    levelCompletedWindow = false
    line = false
    levelChoosed(thisLevel)
}

// HUD 'edit' box (play-test only): left of the restart box (x - 146), same size and style;
// always at x - 292 so it does not jump when the restart and speed boxes appear (TASK-187: speed took x - 219)
function editIconRect()
{
    return [menuIconRect[0][0] - 292, menuIconRect[0][1], menuIconRect[1][0], menuIconRect[1][1]]
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
    editor.barDrag = null
    editor.barDropAt = null
    if (editorInBar(coords) && !editorButtonAt(coords))
    {
        // panel background (any tool): drag the toolbar, keeping the grab offset
        const R = editorBarRect()
        editor.barDrag = { dx: R[0] - coords[0], dy: R[1] - coords[1], x0: R[0], y0: R[1] }
        return
    }
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
// Endpoint drag: only end d.end follows the mouse (grab offset kept), clamped to the field. In 'snap'
// mode the moving end is editorSnapEnd(fixed end, cursor, the other lines) on every move and the drop.
function editorDragLineEnd(d, coords)
{
    const l = editor.level.lines[d.i]
    if (!l)
        return
    let [x, y] = editorClampToField(coords[0] + d.dx, coords[1] + d.dy)
    if (editor.snap)
    {
        const fx = d.end == 0 ? l.posX2 : l.posX, fy = d.end == 0 ? l.posY2 : l.posY
        ;[x, y] = editorSnapEnd(fx, fy, x, y, editor.level.lines.filter((o, j) => j != d.i))
    }
    if (d.end == 0) { l.posX = x; l.posY = y }
    else { l.posX2 = x; l.posY2 = y }
}
// Endpoint drop: snap to another line's endpoint (dotСorrection, the line itself excluded; in 'snap'
// mode editorDragLineEnd already did it, so the 15° angle is kept); refused (true) when the line gets
// shorter than 1 px
function editorDropLineEnd(d)
{
    const W = editor.level, l = W.lines[d.i]
    if (!l)
        return false
    if (editor.snap)
        return Math.hypot(l.posX2 - l.posX, l.posY2 - l.posY) < 1
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
    const bd = editor.barDrag
    if (bd)
    {
        editor.barDrag = null
        editorBarMoveTo(coords[0] + bd.dx, coords[1] + bd.dy)
        const R = editorBarRect()
        if (R[0] != bd.x0 || R[1] != bd.y0)
            editor.barDropAt = [coords[0], coords[1]] // swallow the click that follows this mouseup
        editorBarSave()
        return
    }
    if (!editor.drag)
        return
    const d = editor.drag
    editorDragTo(coords)
    editor.drag = null
    if (d.kind == 'portal')
    {
        const P = editor.level.portals[d.i]
        // other lines may cross the opening (TASK-106); only the pair overlapping is refused
        const err = P && editorPortalsOverlap(editor.level.portals) ? 'portals overlap' : null
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
// the line gets shorter than an opening needs (2*h + 2*ball.radius) or the carried pair overlaps on
// the line. Lines may cross portal openings (TASK-106: the line stays solid). null = the edit is allowed.
function editorLineEditError(i)
{
    const W = editor.level, l = W.lines[i]
    if (!l)
        return null
    const hosted = W.portals.filter(P => editorIsWallPortal(P) && P.line === i)
    const len = Math.hypot(l.posX2 - l.posX, l.posY2 - l.posY)
    if (hosted.some(P => len < 2 * P.h + 2 * ball.radius))
        return 'line too short for its portal'
    if (hosted.length && editorPortalsOverlap(W.portals))
        return 'portals overlap'
    return null
}

// touchcancel (OS gesture, palm rejection...): no drop happened, so the dragged object goes back
// to where it was picked up (never left where the drop check would refuse it) and the drag ends
function editorCancelDrag()
{
    if (editor.barDrag)
    {
        editor.barDrag = null // lost mouseup: the panel stays where it was last moved
        editorBarSave()
    }
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
// from every line, B overlapping A on the same line. Other lines may cross an opening (TASK-106).
function editorPortalClick(coords)
{
    const P = editorNewPortal(coords, editor.portalPending ? 'B' : 'A')
    const err = !P ? 'portals go on lines' :
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
// a legacy free-standing one rotates by ∓PI/12 (lines may cross its opening, TASK-106)
function editorRotatePortal(P, da)
{
    if (editorIsWallPortal(P))
    {
        P.side = P.side < 0 ? 1 : -1
        return
    }
    P.angle += da
}

// 'size −' / 'size +' with a selected portal: h of BOTH portals of the pair (one shared size) changes
// by dh, limited to EDITOR_PORTAL_H_MIN..EDITOR_PORTAL_H_MAX (at a limit nothing changes, no error).
// A wall portal's u is re-clamped to the new h first; the change is refused (h and u of both kept,
// 'portal does not fit') when an opening plus ball.radius no longer fits on its host line or the pair
// overlaps; another line crossing or touching an opening is allowed (TASK-106). No portal selected: no-op.
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
    if (fits && editorPortalsOverlap(W.portals))
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

// 'snap' mode: end point of a segment from (fx, fy) towards (x, y). An existing endpoint within
// dotRadius (the same circle test and order as dotСorrection) wins and is returned unchanged, also when
// (x, y) lies exactly on it; otherwise the direction is rounded to a multiple of 15° at the same length,
// and a point that would leave EDITOR_FIELD is pulled back along that same ray to the field edge (the
// angle stays exact).
const EDITOR_SNAP_STEP = Math.PI / 12
function editorSnapEnd(fx, fy, x, y, list)
{
    for (const l of list)
    {
        if (collisionTwoCircles(x, y, dotRadius, l.posX, l.posY, l.radius))
            return [l.posX, l.posY]
        if (collisionTwoCircles(x, y, dotRadius, l.posX2, l.posY2, l.radius))
            return [l.posX2, l.posY2]
    }
    let r = Math.hypot(x - fx, y - fy)
    if (r < 1)
        return [x, y]
    const a = Math.round(Math.atan2(y - fy, x - fx) / EDITOR_SNAP_STEP) * EDITOR_SNAP_STEP
    const ca = Math.cos(a), sa = Math.sin(a), F = EDITOR_FIELD
    if (ca > 0) r = Math.min(r, (F.w - fx) / ca)
    if (ca < 0) r = Math.min(r, -fx / ca)
    if (sa > 0) r = Math.min(r, (F.h - fy) / sa)
    if (sa < 0) r = Math.min(r, -fy / sa)
    r = Math.max(r, 0)
    return editorClampToField(fx + r * ca, fy + r * sa) // only rounding noise is clamped here
}
window.editorSnapEnd = editorSnapEnd

// Line end shown by the live preview: the cursor, or editorSnapEnd(pending, cursor) in 'snap' mode
function editorPreviewEnd()
{
    if (!editor.snap)
        return editor.mouse
    const k = editorClampToField(editor.mouse[0], editor.mouse[1])
    return editorSnapEnd(editor.pending[0], editor.pending[1], k[0], k[1], editor.level.lines)
}

// Line tool: first click = start, second click = end (both snapped to an existing endpoint of the
// working copy with dotСorrection; in 'snap' mode the end goes through editorSnapEnd); appends a level line. Zero-length lines are ignored;
// a line may cross a portal opening (TASK-106: it stays solid in play).
function editorLineClick(coords)
{
    const W = editor.level
    const k = editorClampToField(coords[0], coords[1])
    const c = editor.snap && editor.pending ? editorSnapEnd(editor.pending[0], editor.pending[1], k[0], k[1], W.lines)
                                            : dotСorrection(k[0], k[1], dotRadius, W.lines)
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
    if (editor.barDrag)
        editorBarMoveTo(coords[0] + editor.barDrag.dx, coords[1] + editor.barDrag.dy)
    else if (editor.drag)
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
    drawLines(W.lines, W.lines, portals, [W.ballX, W.ballY])
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
    editorPreviewDraw() // live predicted ball path of the working copy (TASK-094)
    editorDrawSelection()
    drawStartMarker(W.ballX, W.ballY)
    Ball.prototype.draw.call({ posX: W.ballX, posY: W.ballY, radius: ball.radius })
    if (editor.pending && editor.mouse)
    {
        const e = editorPreviewEnd()
        editor.previewEnd = e
        drawNewLine({ posX: editor.pending[0], posY: editor.pending[1], posX2: e[0], posY2: e[1] })
    }
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
        const active = (b.kind == 'tool' && editor.tool == b.id) || (b.kind == 'toggle' && editor[b.id])
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
    // the editor's own portal rules: h within EDITOR_PORTAL_H_MIN..MAX and shared by the pair,
    // the host line long enough for the opening plus ball.radius at both ends, u already clamped
    for (const P of d.portals)
    {
        const l = d.lines[P.line], len = Math.hypot(l[2] - l[0], l[3] - l[1])
        if (P.h < EDITOR_PORTAL_H_MIN || P.h > EDITOR_PORTAL_H_MAX || P.h !== d.portals[0].h ||
            len < 2 * (P.h + ball.radius) || Math.abs(P.u - portalClampU(P.u, len, P.h)) > 1e-9)
            return null
    }
    const portals = d.portals.map((P, i) => ({ line: P.line, u: P.u, side: P.side, h: P.h,
                                              name: typeof P.name == 'string' && P.name ? P.name : (i ? 'B' : 'A') }))
    if (editorPortalsOverlap(portals, lines))
        return null // other lines may cross an opening (TASK-106)
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
    editorPreviewClear()
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

// ---- Editor path preview (TASK-094) ----
// While the editor is open (editorMode, no play-test) the predicted ball path of the working copy is
// drawn live. editorPreviewUpdate() runs once per frame from gameLoop: it builds a key from the
// working copy (ball start, every line, every portal) plus the line tool's pending segment and, when
// the key changed, starts a new job on a snapshot (editorCloneLevel + the pending segment as a
// 'player' line). The job is advanced like Bounce.update (TASK-085/086): resumable, slices of
// STEP_CHUNK gamePhysics() steps for up to budgetMs per frame (at least one slice), a point pushed
// after every cyclesPerTact steps, job.count points in total (TASK-118: 300 with a portal pair, else 100). Each slice installs the snapshot as
// playtestLevel / lines, the job's ball state, portalState and portal cache, and restores the real
// ones afterwards, so editor.level, the real ball, lines, portalState and playtestLevel never change.
let editorPrev = null   // {key, snap, ballX, ballY, speedX, speedY, portal, cache, step, points, slices, done}

// End point of the line tool's pending segment as the second click would place it, or null
function editorPendingEnd()
{
    if (editor.tool != 'line' || !editor.pending || !editor.mouse || !editor.level)
        return null
    const k = editorClampToField(editor.mouse[0], editor.mouse[1])
    const c = dotСorrection(k[0], k[1], dotRadius, editor.level.lines)
    if (c[0] == editor.pending[0] && c[1] == editor.pending[1])
        return null // zero length: the click would only cancel the start point
    return c
}

function editorPreviewKey(W, pend)
{
    let key = W.ballX + ',' + W.ballY + '|'
    for (const l of W.lines)
        key += l.posX + ',' + l.posY + ',' + l.posX2 + ',' + l.posY2 + ',' + l.radius + ';'
    key += '|'
    for (const P of W.portals || [])
        key += typeof P.line == 'number' ? P.line + ',' + P.u + ',' + P.side + ',' + P.h + ';'
                                         : P.x + ',' + P.y + ',' + P.angle + ',' + P.h + ';'
    if (pend)
        key += '|' + editor.pending[0] + ',' + editor.pending[1] + ',' + pend[0] + ',' + pend[1]
    return key
}

function editorPreviewClear()
{
    editorPrev = null
}

function editorPreviewStart(key, pend)
{
    const snap = editorCloneLevel(editor.level)
    if (pend)
        snap.lines.push(new Line(editor.pending[0], editor.pending[1], pend[0], pend[1], dotRadius, '#0000ff', 'player'))
    editorPrev = {
        key: key, snap: snap,
        ballX: snap.ballX, ballY: snap.ballY, speedX: 0, speedY: 0,
        portal: { prevD: [], teleports: [], rimHits: 0, rims: [], steps: 0, hostHits: 0, hostHit: null, blockedExits: 0, blocked: [], grace: null }, // = portalReset()
        cache: { level: null, src: null, vals: [], list: null, hosts: null },
        step: 0, points: [], slices: 0, done: false,
        count: editorPortals().length ? bounce.portalPointsCount : bounce.pointsCount  // TASK-118: 300 with portals, else 100
    }
}

// Up to maxSteps steps of the job's current point on the job's own state
function editorPreviewSlice(job, maxSteps)
{
    const savedPlay = playtestLevel, savedLines = lines, savedPortal = portalState, savedCache = portalCache
    const bx = ball.posX, by = ball.posY, vx = ball.speedX, vy = ball.speedY
    playtestLevel = job.snap
    lines = job.snap.lines
    portalState = job.portal
    portalCache = job.cache
    ball.posX = job.ballX; ball.posY = job.ballY
    ball.speedX = job.speedX; ball.speedY = job.speedY
    try
    {
        const n = Math.min(maxSteps, cyclesPerTact - job.step)
        const frozen = portalFreeze(true)    // TASK-123: validates the job's own cache (job.snap), then frozen
        try
        {
            for (let j = 0; j < n; ++j)
                gamePhysics()
        }
        finally
        {
            portalFreeze(frozen)
        }
        job.step += n
        if (job.step >= cyclesPerTact)
        {
            job.step = 0
            job.points.push({x: ball.getX(), y: ball.getY()})
        }
        job.ballX = ball.posX; job.ballY = ball.posY
        job.speedX = ball.speedX; job.speedY = ball.speedY
        job.portal = portalState
        job.cache = portalCache
        job.slices++
    }
    finally
    {
        ball.posX = bx; ball.posY = by
        ball.speedX = vx; ball.speedY = vy
        portalCache = savedCache
        portalState = savedPortal
        lines = savedLines
        playtestLevel = savedPlay
    }
}

// Game loop, once per frame
function editorPreviewUpdate(budgetMs = 6)
{
    if (!editorMode || playtestLevel || !editor.level)
    {
        editorPrev = null
        return
    }
    const start = performance.now()
    const pend = editorPendingEnd()
    const key = editorPreviewKey(editor.level, pend)
    if (!editorPrev || editorPrev.key !== key)
        editorPreviewStart(key, pend)
    const job = editorPrev
    if (job.done)
        return
    do
        editorPreviewSlice(job, STEP_CHUNK)
    while (job.points.length < job.count && performance.now() - start < budgetMs)
    job.done = job.points.length >= job.count
}

// Same look as Bounce.draw (cyan hollow circles, fading, spacing rule); partial paths too
function editorPreviewDraw()
{
    if (!editorPrev || !editorPrev.points.length)
        return
    Bounce.prototype.draw.call({ drawEnable: true, positions: editorPrev.points, pointsCount: editorPrev.count,
        color: bounce.color, dotRadius: bounce.dotRadius, spacing: bounce.spacing })
}

// Test hook
window.editorPreview = function()
{
    if (!editorPrev)
        return { key: null, done: false, points: [], slices: 0, teleports: 0 }
    return { key: editorPrev.key, done: editorPrev.done, points: editorPrev.points.map(p => [p.x, p.y]), slices: editorPrev.slices,
             teleports: editorPrev.portal.teleports.length }
}
