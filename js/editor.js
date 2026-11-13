// Level editor (opened from the pause menu's 'editor' button).
//
// editorMode = true: the game's clicks, the path preview and physics are off; draw() shows the
// working copy of levels[thisLevel] (lines, flag, ball start, portals) and the toolbar.
// Working copy shape: {ballX, ballY, flagX, flagY, flagRotate, lineK, lines: [Line], portals: [] | [A, B]}.
// 'exit' writes the copy back to levels[thisLevel] (this session only) and reloads the level.
let editorMode = false
let editor = { tool: 'select', level: null, lastAction: null, actions: 0, mouse: null }

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
        return // play-field tools: later tickets
    if (b.kind == 'tool')
    {
        editor.tool = b.id
        return
    }
    editor.lastAction = b.id
    editor.actions++
    if (b.id == 'exit')
        editorExit()
}

function editorMouseMove(coords)
{
    editor.mouse = coords
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
    flag = editorFlagPolygon(W.flagRotate)
    drawFlag(W.flagX, W.flagY, THEME.ink, THEME.coral)
    flag = saved
    drawPortals(W.portals)
    drawStartMarker(W.ballX, W.ballY)
    Ball.prototype.draw.call({ posX: W.ballX, posY: W.ballY, radius: ball.radius })
    editorDrawToolbar()
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
