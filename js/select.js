'use strict'
// Player-line selection and the 'delete' bin (look: artifacts/concepts/80-delete-bin.png).
// Editable state = no run in progress and no line being drawn (before the first run and after
// an off-map failure, which keeps the player's lines). A click within SEL_HIT px of a player
// line selects it (playerSel = index into lines); a click in the bin removes that line.
const SEL_HIT = 8          // click distance to a player line (logical px)
const BIN_R = 26           // bin button radius
const BIN_OFF = 62         // bin centre distance from the line midpoint (above, else below)
let playerSel = null

function selectionEditable()
{
    return !levelStarted && !line && !drawMenu && !levelCompletedWindow && !editorMode
}
// index into lines of the nearest player line within SEL_HIT of (x, y), or null
function playerLineAt(x, y)
{
    let best = null, bestD = SEL_HIT
    for (let i = 0; i < lines.length; ++i)
    {
        const l = lines[i]
        if (l.type != 'player')
            continue
        const d = pointSegDist(x, y, l.posX, l.posY, l.posX2, l.posY2)
        if (d <= bestD)
        {
            best = i
            bestD = d
        }
    }
    return best
}
function selectionClear()
{
    playerSel = null
}
// HUD rectangles [x1, y1, x2, y2] the bin must not overlap: menu box, play box, edit box
// (play-test only), restart box (while visible) and the lines counter
function hudRects()
{
    const x = menuIconRect[0][0], y = menuIconRect[0][1], w = menuIconRect[1][0], h = menuIconRect[1][1]
    const r = [[x, y, x + w, y + h], [x - 73, y, x - 73 + w, y + h]]
    if (typeof playtestLevel != 'undefined' && playtestLevel)
        r.push([x - 219, y, x - 219 + w, y + h])
    if (typeof restartIconVisible == 'function' && restartIconVisible())
        r.push([x - 146, y, x - 146 + w, y + h])
    const n = curLevel().lineK
    r.push([GAME_W - 120 - 4, 63 + 20 + 30 - 9, GAME_W - 120 + (n - 1) * 36 + 26 + 4, 63 + 20 + 30 + 9])
    return r
}
// bounding box of the bin (circle + glow) and its 'delete' label for a centre (cx, cy)
function binBox(cx, cy)
{
    return [cx - 32, cy - 36 - 14, cx + 32, cy + BIN_R + 4]
}
// bin centre for player line l: BIN_OFF above the midpoint, or below if that leaves the
// canvas or overlaps the HUD
function binCenter(l)
{
    const mx = (l.posX + l.posX2) / 2, my = (l.posY + l.posY2) / 2
    const b = binBox(mx, my - BIN_OFF)
    let ok = b[0] >= 0 && b[1] >= 0 && b[2] <= GAME_W && b[3] <= GAME_H
    const hud = hudRects()
    for (let i = 0; ok && i < hud.length; ++i)
        if (b[0] < hud[i][2] && b[2] > hud[i][0] && b[1] < hud[i][3] && b[3] > hud[i][1])
            ok = false
    return ok ? [mx, my - BIN_OFF] : [mx, my + BIN_OFF]
}
function inBin(coords)
{
    if (endDrag || playerSel === null || !lines[playerSel])
        return false
    const c = binCenter(lines[playerSel])
    return Math.hypot(coords[0] - c[0], coords[1] - c[1]) <= BIN_R
}
// remove the selected player line; the player may draw a line again
function deleteSelectedLine()
{
    lines.splice(playerSel, 1)
    linesK -= 1
    playerSel = null
    bounce.cancel()
    bounce.positions = []
}
// Click while a line is selected (editable state): bin -> delete; another player line ->
// select it; anything else -> deselect. Never starts a line.
function selectionClick(coords)
{
    if (inBin(coords))
        return deleteSelectedLine()
    playerSel = playerLineAt(coords[0], coords[1])
}
function drawSelection()
{
    if (playerSel === null || !lines[playerSel] || !selectionEditable())
        return
    const l = lines[playerSel]
    ctx.save()
    // dashed capsule 14 px around the segment
    const a = Math.atan2(l.posY2 - l.posY, l.posX2 - l.posX), nx = -Math.sin(a) * 14, ny = Math.cos(a) * 14
    ctx.strokeStyle = THEME.cyan; ctx.lineWidth = 1.2; ctx.globalAlpha = .8
    ctx.setLineDash([5, 6]); ctx.lineCap = 'round'
    ctx.beginPath()
    ctx.moveTo(l.posX + nx, l.posY + ny)
    ctx.lineTo(l.posX2 + nx, l.posY2 + ny)
    ctx.arc(l.posX2, l.posY2, 14, a + Math.PI / 2, a - Math.PI / 2, true)
    ctx.lineTo(l.posX - nx, l.posY - ny)
    ctx.arc(l.posX, l.posY, 14, a - Math.PI / 2, a + Math.PI / 2, true)
    ctx.closePath()
    ctx.stroke()
    ctx.setLineDash([]); ctx.globalAlpha = 1
    // coral handles at both ends
    ctx.lineWidth = 2; ctx.strokeStyle = THEME.coral; ctx.fillStyle = 'rgba(255,106,85,.25)'
    ctx.shadowColor = 'rgba(255,106,85,.8)'; ctx.shadowBlur = 10
    const ends = [[l.posX, l.posY], [l.posX2, l.posY2]]
    for (let i = 0; i < 2; ++i)
    {
        ctx.beginPath(); ctx.arc(ends[i][0], ends[i][1], 10, 0, Math.PI * 2)
        ctx.fill(); ctx.stroke()
    }
    ctx.restore()

    if (endDrag)
        return // the bin is hidden while an end is dragged
    // bin button
    const c = binCenter(l), cx = c[0], cy = c[1]
    ctx.save()
    ctx.beginPath(); ctx.arc(cx, cy, BIN_R, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(7,26,48,.9)'; ctx.fill()
    ctx.strokeStyle = THEME.coral; ctx.lineWidth = 2
    ctx.shadowColor = 'rgba(255,106,85,.85)'; ctx.shadowBlur = 12
    ctx.stroke()
    ctx.restore()
    const R = sketchRng(sketchSeed([l.posX, l.posY, l.posX2, l.posY2, 80]))
    const ink = THEME.ink
    handLine(ctx, R, cx - 11, cy - 9, cx + 11, cy - 9, ink, 1.6, 2, 0.8, 0)
    handLine(ctx, R, cx - 4, cy - 13, cx + 4, cy - 13, ink, 1.6, 2, 0.8, 0)
    handLine(ctx, R, cx - 9, cy - 6, cx - 7, cy + 13, ink, 1.6, 2, 0.8, 0)
    handLine(ctx, R, cx + 9, cy - 6, cx + 7, cy + 13, ink, 1.6, 2, 0.8, 0)
    handLine(ctx, R, cx - 7, cy + 13, cx + 7, cy + 13, ink, 1.6, 2, 0.8, 0)
    handLine(ctx, R, cx - 3, cy - 3, cx - 3, cy + 9, THEME.soft, 1.2, 2, 0.6, 0)
    handLine(ctx, R, cx + 3, cy - 3, cx + 3, cy + 9, THEME.soft, 1.2, 2, 0.6, 0)
    ctx.save()
    ctx.fillStyle = THEME.coral
    ctx.font = '22px ' + THEME.fontStack; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText('delete', cx, cy - 36)
    ctx.restore()
}

// ---- Dragging an end of a player line (editable state only) ----
// mousedown / touchstart within END_HIT px of an end picks it up and selects its line; the end
// follows the pointer (clamped to the field); the drop is validated like addNewLine (snap to
// line ends, not through the ball, not shorter than 1 px; crossing a portal is allowed). A rejected drop
// puts the end back where it was picked up and shows a short handwritten hint near it.
const END_HIT = 12           // pick-up distance to a player line end (logical px)
const DRAG_SLOP = 3          // movement beyond this makes a press a drag (a click otherwise)
const DRAG_HINT_MS = 1500    // how long the rejection hint stays
let endDrag = null           // {li, end: 0|1, orig: [x, y], start: [x, y], prevSel, moved}
let dragHint = null          // {text, x, y, until}
let suppressClick = false    // the click that follows a mouse drag is ignored

// [line index, end 0|1] of the nearest player line end within END_HIT of (x, y), or null
function playerEndAt(x, y)
{
    let best = null, bestD = END_HIT
    for (let i = 0; i < lines.length; ++i)
    {
        const l = lines[i]
        if (l.type != 'player')
            continue
        const d1 = Math.hypot(x - l.posX, y - l.posY), d2 = Math.hypot(x - l.posX2, y - l.posY2)
        if (d1 <= bestD) { best = [i, 0]; bestD = d1 }
        if (d2 <= bestD) { best = [i, 1]; bestD = d2 }
    }
    return best
}
function endSet(l, end, x, y)
{
    if (end == 0) { l.posX = x; l.posY = y }
    else { l.posX2 = x; l.posY2 = y }
}
// press at coords: start a drag if it is on a player line end in the editable state
function dragStart(coords)
{
    if (!selectionEditable() || inBin(coords) || inMenuIcon(coords) || inPlayIcon(coords))
        return false
    const hit = playerEndAt(coords[0], coords[1])
    if (!hit)
        return false
    const l = lines[hit[0]]
    endDrag = {li: hit[0], end: hit[1], orig: hit[1] == 0 ? [l.posX, l.posY] : [l.posX2, l.posY2],
               start: coords.slice(), prevSel: playerSel, moved: false}
    playerSel = hit[0]
    dragHint = null
    return true
}
function dragMove(coords)
{
    if (!endDrag)
        return
    const d = endDrag
    if (Math.hypot(coords[0] - d.start[0], coords[1] - d.start[1]) > DRAG_SLOP)
        d.moved = true
    if (!d.moved)
        return
    const x = Math.max(0, Math.min(GAME_W, d.orig[0] + coords[0] - d.start[0]))
    const y = Math.max(0, Math.min(GAME_H, d.orig[1] + coords[1] - d.start[1]))
    endSet(lines[d.li], d.end, x, y)
}
// put the end back; a press that never moved (or asTap: a touch tap) restores the selection it
// found, so the click / tap that follows behaves as without the drag
function dragCancel(asTap = false)
{
    if (!endDrag)
        return
    const d = endDrag
    endDrag = null
    endSet(lines[d.li], d.end, d.orig[0], d.orig[1])
    if (!d.moved || asTap)
        playerSel = d.prevSel
}
// release at coords; returns true if the press was a drag (the follow-up click must be ignored)
function dragDrop(coords)
{
    if (!endDrag)
        return false
    dragMove(coords)
    const d = endDrag
    if (!d.moved)
    {
        dragCancel()
        return false
    }
    endDrag = null
    const l = lines[d.li]
    const p = d.end == 0 ? [l.posX, l.posY] : [l.posX2, l.posY2]
    const others = lines.filter(function(o, i) { return i != d.li })
    const c = dotСorrection(p[0], p[1], dotRadius, others)
    const q = d.end == 0 ? [l.posX2, l.posY2] : [l.posX, l.posY] // the fixed end
    let err = null
    if (Math.hypot(c[0] - q[0], c[1] - q[1]) < 1)
        err = 'too short'
    else if (pointSegDist(ball.posX, ball.posY, q[0], q[1], c[0], c[1]) <= ball.radius)
        err = 'too close to the ball'
    if (err)
    {
        endSet(l, d.end, d.orig[0], d.orig[1])
        dragHint = {text: err, x: d.orig[0], y: d.orig[1], until: performance.now() + DRAG_HINT_MS}
    }
    else
        endSet(l, d.end, c[0], c[1])
    // the idle trail (js/bounce.js) is recomputed from the final lines (state signature changes)
    playerSel = d.li
    return true
}
function drawDragHint()
{
    if (!dragHint)
        return
    if (performance.now() > dragHint.until || !selectionEditable())
    {
        dragHint = null
        return
    }
    const h = dragHint
    ctx.save()
    ctx.font = '700 26px ' + THEME.fontStack
    ctx.textBaseline = 'alphabetic'
    const w = ctx.measureText(h.text).width
    // right of the end, flipped left / below to stay on the canvas
    let x = h.x + 18, y = h.y - 18
    if (x + w > GAME_W - 8) x = h.x - 18 - w
    if (y - 26 < 8) y = h.y + 40
    ctx.textAlign = 'left'
    ctx.fillStyle = THEME.coral; ctx.shadowColor = 'rgba(255,106,85,.9)'; ctx.shadowBlur = 10
    ctx.fillText(h.text, x, y)
    ctx.restore()
}

// ---- Locked after a run ----
// Once a run was started (levelStarted, physics running or paused with the play icon) the
// player's lines can't be edited; an attempt (click/tap within SEL_HIT of a player line, or a
// press within END_HIT of a player line end) shows a plain handwritten hint at the pointer that
// fades out linearly over LOCK_HINT_MS. Nothing is selected, moved or deleted.
const LOCK_HINT_MS = 1500
const LOCK_HINT_TEXT = 'locked after run · menu → restart to edit'
let lockHint = null          // {x, y, t0}

function lockedState()
{
    return levelStarted && !line && !drawMenu && !levelCompletedWindow && !editorMode
}
// click / tap at coords: show the hint if it is an edit attempt on a locked player line
function lockClick(coords)
{
    if (!lockedState() || inMenuIcon(coords) || inPlayIcon(coords) || (restartIconVisible() && inRestartIcon(coords)))
        return false
    if (playerLineAt(coords[0], coords[1]) === null && playerEndAt(coords[0], coords[1]) === null)
        return false
    lockHint = {x: coords[0], y: coords[1], t0: performance.now()}
    return true
}
// press (mousedown / touchstart) at coords: only a press on a player line end counts
function lockPress(coords)
{
    if (!lockedState() || inMenuIcon(coords) || inPlayIcon(coords) || (restartIconVisible() && inRestartIcon(coords)))
        return false
    if (playerEndAt(coords[0], coords[1]) === null)
        return false
    lockHint = {x: coords[0], y: coords[1], t0: performance.now()}
    return true
}
function lockHintAlpha()
{
    if (!lockHint)
        return 0
    const a = 1 - (performance.now() - lockHint.t0) / LOCK_HINT_MS
    if (a <= 0)
    {
        lockHint = null
        return 0
    }
    return a
}
function drawLockHint()
{
    const a = lockHintAlpha()
    if (a <= 0)
        return
    ctx.save()
    ctx.font = '20px ' + THEME.fontStack
    ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left'
    const w = ctx.measureText(LOCK_HINT_TEXT).width
    // right of / above the pointer, flipped to stay on the canvas
    let x = lockHint.x + 16, y = lockHint.y - 16
    if (x + w > GAME_W - 8) x = lockHint.x - 16 - w
    if (x < 8) x = 8
    if (y - 20 < 8) y = lockHint.y + 34
    ctx.globalAlpha = a
    ctx.fillStyle = THEME.soft
    ctx.fillText(LOCK_HINT_TEXT, x, y)
    ctx.restore()
}
