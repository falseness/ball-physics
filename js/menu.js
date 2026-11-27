// TASK-255: one centred layout for the pause menu and the level-complete window. menuLayout(kind) is the only
// source of the panel and button rects: menu() / levelCompleted() draw from it and handleClick (index.html)
// hit-tests the same rects. Panel: logo area (js/logo.js, box +10..+390 x +5..+285), then for 'win' the
// 'Level completed!' row, then the buttons (MENU_BTN_W x MENU_BTN_H, MENU_BTN_STEP apart) and a bottom margin;
// the panel is centred on the logical field (GAME_W / 2, GAME_H / 2).
const MENU_W = 400, MENU_BTN_W = 250, MENU_BTN_H = 50, MENU_BTN_STEP = 85, MENU_LOGO_H = 285, MENU_PAD = 20
// kind 'pause': resume / restart / skip level / Levels / editor (TASK-260; 'skip level' only when a next level
// exists in play order and not in a play-test, otherwise the row is dropped and the panel shrinks).
// kind 'win': next level (not on the last level, not in a play-test) / restart / editor / Levels, under the
// 'Level completed!' row; on the last level a 'Thanks for playing!' row takes the 'next level' slot.
// In a play-test 'editor' is the way back to the editor (editorEndPlaytest).
// Returns {panel: [x, y, w, h], logo: [x, y, w, h], buttons: [{id, rect}], labels: [{text, x, y, size, color}]}.
function menuLayout(kind)
{
    const ids = kind == 'win' ? ['restart', 'editor', 'Levels']
        : menuSkipVisible() ? ['resume', 'restart', 'skip level', 'Levels', 'editor'] : ['resume', 'restart', 'Levels', 'editor']
    const rows = []  // [type, value] top to bottom below the logo
    if (kind == 'win')
    {
        rows.push(['label', 'Level completed!', 38, THEME.coral])
        if (playtestLevel)
            ;
        else if (thisLevel + 1 < levels.length)
            rows.push(['button', 'next level'])
        else
            rows.push(['label', 'Thanks for playing!', 34, THEME.soft])
    }
    for (const id of ids)
        rows.push(['button', id])
    const h = MENU_LOGO_H + MENU_PAD / 2 + rows.length * MENU_BTN_STEP - (MENU_BTN_STEP - MENU_BTN_H) + MENU_PAD
    const x = Math.round((GAME_W - MENU_W) / 2), y = Math.round((GAME_H - h) / 2)
    const bx = x + (MENU_W - MENU_BTN_W) / 2
    const out = {panel: [x, y, MENU_W, h], logo: [x + 10, y + 5, MENU_W - 20, MENU_LOGO_H - 5], buttons: [], labels: []}
    rows.forEach((r, i) =>
    {
        const ry = y + MENU_LOGO_H + MENU_PAD / 2 + i * MENU_BTN_STEP
        if (r[0] == 'button')
            out.buttons.push({id: r[1], rect: [bx, ry, MENU_BTN_W, MENU_BTN_H]})
        else
            out.labels.push({text: r[1], x: x + MENU_W / 2, y: ry + MENU_BTN_H / 2, size: r[2], color: r[3]})
    })
    return out
}
// TASK-260: the pause menu's 'skip level' row: a next level in play order, not in a play-test
function menuSkipVisible()
{
    return !playtestLevel && thisLevel + 1 < levels.length
}
// id of the menuLayout(kind) button under the logical point, or null
function menuButtonAt(kind, coords)
{
    for (const b of menuLayout(kind).buttons)
    {
        const r = b.rect
        if (collisionWithRect(coords[0], coords[1], r[0], r[1], r[0] + r[2], r[1] + r[3]))
            return b.id
    }
    return null
}
// Panel, logo, labels and buttons of menuLayout(kind) (the navy overlay is drawn by the caller)
function drawMenuLayout(kind)
{
    const L = menuLayout(kind)
    glassPanel(...L.panel)
    drawLogo(...L.logo)
    for (const t of L.labels)
        menuLabel(t.text, t.x, t.y, t.size, t.color)
    for (const b of L.buttons)
        menuButton(...b.rect, b.id)
}

// Translucent navy overlay behind the pause menu / level-complete window.
// Leaves a centred THEME-font text state behind (levelCompleted() relies on it).
function eclipse()
{
    ctx.fillStyle = 'rgba(4,15,30,0.62)'
    ctx.fillRect(0, 0, GAME_W, GAME_H)
    ctx.font = "30px " + THEME.fontStack
    ctx.textAlign = "center"
    ctx.textBaseline = "alphabetic"
}
// Dark glass panel with a 1.5px cyan border and a soft glow
function glassPanel(x, y, w, h)
{
    ctx.save()
    ctx.fillStyle = 'rgba(7,26,48,0.85)'
    ctx.fillRect(x, y, w, h)
    ctx.strokeStyle = THEME.cyan; ctx.lineWidth = 1.5
    ctx.shadowColor = THEME.cyan; ctx.shadowBlur = 10
    ctx.strokeRect(x, y, w, h)
    ctx.restore()
}
// Cyan outlined button rect (same rect the click handler tests) with a handwritten label centred in it
function menuButton(x, y, w, h, label)
{
    ctx.save()
    ctx.fillStyle = 'rgba(130,210,255,0.06)'
    ctx.fillRect(x, y, w, h)
    ctx.strokeStyle = THEME.cyan; ctx.lineWidth = 1.5
    ctx.shadowColor = THEME.cyan; ctx.shadowBlur = 6
    ctx.strokeRect(x, y, w, h)
    ctx.shadowBlur = 0
    menuLabel(label, x + w / 2, y + h / 2)
    ctx.restore()
}
function menuLabel(text, x, y, size = 34, color = THEME.ink)
{
    ctx.save()
    ctx.font = size + "px " + THEME.fontStack
    ctx.textAlign = "center"; ctx.textBaseline = "middle"
    ctx.fillStyle = color
    ctx.shadowColor = 'rgba(190,230,255,0.45)'; ctx.shadowBlur = 6
    ctx.fillText(text, x, y)
    ctx.restore()
}
function collisionWithRect(x, y, x1, y1, x2, y2)
{
    return (x1 < x && x < x2 &&
       y1 < y && y < y2)
}

function menu()
{
    if (drawMenu)
    {
        applyViewTransform()
        eclipse()
        drawMenuLayout('pause')
    }
}
function menuIcon()
{
    if (drawMenuIcon)
    {
        const x = menuIconRect[0][0], y = menuIconRect[0][1]
        ctx.save()
        hudBox(x, y)
        ctx.fillStyle = THEME.ink
        ctx.shadowColor = 'rgba(130,210,255,0.6)'; ctx.shadowBlur = 6
        for (let i = 0; i < menuIconLine.length; i += 2)
            ctx.fillRect(x + menuIconLine[i][0], y + menuIconLine[i][1], 53, 8)
        ctx.restore()
    }
}
// 1.5px cyan outlined HUD box with a soft glow (hit areas are computed elsewhere from menuIconRect)
function hudBox(x, y)
{
    ctx.save()
    ctx.strokeStyle = THEME.cyan; ctx.lineWidth = 1.5
    ctx.shadowColor = THEME.cyan; ctx.shadowBlur = 8
    ctx.fillStyle = 'rgba(7,26,48,0.55)'
    ctx.fillRect(x, y, menuIconRect[1][0], menuIconRect[1][1])
    ctx.strokeRect(x, y, menuIconRect[1][0], menuIconRect[1][1])
    ctx.restore()
}
function drawStartIcon()
{
    ctx.save()
    hudBox(menuIconRect[0][0] - 73, menuIconRect[0][1])
    const c = physics ? THEME.physicsOn : THEME.coral
    ctx.fillStyle = c
    ctx.shadowColor = c; ctx.shadowBlur = 8
    ctx.beginPath()
    ctx.moveTo(startIconTriangle[startIconTriangle.length - 1][0], startIconTriangle[startIconTriangle.length - 1][1])
    for (let i = 0; i < startIconTriangle.length; ++i)
        ctx.lineTo(startIconTriangle[i][0], startIconTriangle[i][1])
    ctx.closePath()
    ctx.fill()
    ctx.restore()
}
// 'restart' box: white circular arrow (concept 82 'loop'), drawn only when restartIconVisible()
function drawRestartIcon()
{
    const r = restartIconRect(), cx = r[0] + r[2] / 2, cy = r[1] + r[3] / 2, R = 17
    const a0 = -0.35 * Math.PI, a1 = 1.35 * Math.PI
    ctx.save()
    hudBox(r[0], r[1])
    ctx.strokeStyle = ctx.fillStyle = ctx.shadowColor = THEME.ink
    ctx.shadowBlur = 8
    ctx.lineWidth = 4; ctx.lineCap = 'round'
    ctx.beginPath()
    ctx.arc(cx, cy, R, a0, a1)
    ctx.stroke()
    // filled arrowhead at the arc start, pointing against the arc direction (counter-clockwise)
    const px = cx + R * Math.cos(a0), py = cy + R * Math.sin(a0)
    const tx = Math.sin(a0), ty = -Math.cos(a0)       // tangent pointing backwards along the arc
    const nx = Math.cos(a0), ny = Math.sin(a0)        // radial
    ctx.beginPath()
    ctx.moveTo(px + tx * 9, py + ty * 9)
    ctx.lineTo(px - tx * 3 + nx * 7, py - ty * 3 + ny * 7)
    ctx.lineTo(px - tx * 3 - nx * 7, py - ty * 3 - ny * 7)
    ctx.closePath()
    ctx.fill()
    ctx.restore()
}
// '3x speed' box (concept 14): a double play arrow centred on the box on both axes and a THEME-font '3x' label
// (23 px, centre at x+48, y+49). Off: ink on the cyan hudBox; on (speedMul 3): green on a coral box.
function drawSpeedIcon()
{
    const r = speedIconRect(), x = r[0], y = r[1], cx = x + r[2] / 2, cy = y + r[3] / 2
    const on = speedMul == 3, c = on ? THEME.physicsOn : THEME.ink
    const w = 17, h = 24, step = 14, ax = cx - (step + w) / 2
    ctx.save()
    if (on)
    {
        ctx.fillStyle = 'rgba(255,106,85,0.14)'
        ctx.fillRect(x, y, r[2], r[3])
        ctx.strokeStyle = THEME.coral; ctx.lineWidth = 1.5
        ctx.shadowColor = THEME.coral; ctx.shadowBlur = 14
        ctx.strokeRect(x, y, r[2], r[3])
    }
    else
        hudBox(x, y)
    ctx.restore()
    for (const tx of [ax, ax + step])
    {
        ctx.save()
        ctx.fillStyle = ctx.shadowColor = c; ctx.shadowBlur = 6
        ctx.beginPath()
        ctx.moveTo(tx, cy - h / 2); ctx.lineTo(tx + w, cy); ctx.lineTo(tx, cy + h / 2)
        ctx.closePath()
        ctx.fill()
        ctx.restore()
    }
    ctx.save()
    ctx.font = '23px ' + THEME.fontStack; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillStyle = c; ctx.shadowColor = 'rgba(190,230,255,0.45)'; ctx.shadowBlur = 6
    ctx.fillText('3x', x + 48, y + 49)
    ctx.restore()
}
// Line counter option A: one mini line glyph per allowed line; used = coral, free = dashed cyan
function drawLinesK()
{
    const n = curLevel().lineK, x0 = GAME_W - 120, cy = 63 + 20 + 30
    const w = 26, h = 10, step = 36, r = 3
    ctx.save()
    ctx.lineCap = 'round'
    for (let i = 0; i < n; ++i)
    {
        const used = i < linesK, c = used ? THEME.coral : THEME.cyan
        const x1 = x0 + i * step, y1 = cy + h / 2, x2 = x1 + w, y2 = cy - h / 2
        const a = Math.atan2(y2 - y1, x2 - x1), dx = Math.cos(a) * r, dy = Math.sin(a) * r
        ctx.strokeStyle = c; ctx.lineWidth = used ? 1.8 : 1.4
        ctx.shadowColor = c; ctx.shadowBlur = 6
        ctx.setLineDash(used ? [] : [3, 3])
        ctx.beginPath(); ctx.moveTo(x1 + dx, y1 + dy); ctx.lineTo(x2 - dx, y2 - dy); ctx.stroke()
        ctx.setLineDash([]); ctx.lineWidth = 1.4
        ctx.beginPath(); ctx.arc(x1, y1, r, 0, Math.PI * 2); ctx.stroke()
        ctx.beginPath(); ctx.arc(x2, y2, r, 0, Math.PI * 2); ctx.stroke()
    }
    ctx.restore()
}
// drawLogo(x, y, w, h): js/logo.js (TASK-265, concept 129)
function guide()
{
    // Level-1 tutorial hints: bright coral handwritten text with a glow pass, hand-drawn
    // arrows and target rings at the points to click. Seeded rng -> identical every frame.
    if (thisLevel == 0 && !playtestLevel)
    {
        const R = sketchRng(1161), col = THEME.coral
        ctx.save()
        ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'
        ctx.fillStyle = col; ctx.shadowColor = 'rgba(255,106,85,0.9)'
        for (const blur of [16, 0])
        {
            ctx.shadowBlur = blur
            ctx.font = '34px ' + THEME.fontStack
            ctx.fillText('Click here', 800, 156)
            ctx.fillText('and here', 262, 482)
            ctx.font = '30px ' + THEME.fontStack
            ctx.fillText('to draw a line', 262, 514)
        }
        guideArrow(R, 808, 168, 794, 192, col, 2.6, 10)
        guideArrow(R, 340, 478, 316, 462, col, 2.6, 10)
        guideRing(790, 206, col)
        guideRing(300, 450, col)
        ctx.restore()
    }
}
function guideArrow(R, x1, y1, x2, y2, color, width, head)
{
    ctx.save(); ctx.shadowColor = color; ctx.shadowBlur = 10
    handLine(ctx, R, x1, y1, x2, y2, color, width, 2, 1.2, 0)
    arrowHead(ctx, x2, y2, Math.atan2(y2 - y1, x2 - x1), head, color)
    ctx.restore()
}
function guideRing(x, y, color)
{
    ctx.save(); ctx.strokeStyle = color; ctx.shadowColor = color
    ctx.lineWidth = 2.2; ctx.shadowBlur = 14
    ctx.beginPath(); ctx.arc(x, y, 9, 0, 2 * Math.PI); ctx.stroke()
    ctx.globalAlpha = .45; ctx.lineWidth = 1.4
    ctx.beginPath(); ctx.arc(x, y, 18, 0, 2 * Math.PI); ctx.stroke()
    ctx.restore()
}
