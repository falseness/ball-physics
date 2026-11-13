let menuTextRect = [250, 50]
let menuCoords = [GAME_W / 2, 50]
let menuSize = [400, 650]
let menuButtons = ['resume', 'restart', 'Levels']

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
        eclipse()
        glassPanel(menuCoords[0], menuCoords[1], menuSize[0], menuSize[1])
        for (let i = 0; i < menuButtons.length; ++i)
        {
            if (i == 2)
            {
                // 'Levels' heading above the level grid (no button rect, as before)
                menuLabel(menuButtons[i], menuCoords[0] + menuSize[0] / 2, menuCoords[1] + 335 + 85 * i - 10, 34, THEME.soft)
                continue
            }
            menuButton(menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2, menuCoords[1] + 300 + i * 85, menuTextRect[0], menuTextRect[1], menuButtons[i])
        }
        drawLevels()
        drawLogo()
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
// Line counter option A: one mini line glyph per allowed line; used = coral, free = dashed cyan
function drawLinesK()
{
    const n = levels[thisLevel].lineK, x0 = GAME_W - 120, cy = 63 + 20 + 30
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
// Logo: handwritten title over a small framed sketch (ice ball resting on a coral line)
function drawLogo()
{
    const x0 = menuCoords[0], y0 = menuCoords[1]
    menuLabel('Ball physics', x0 + menuSize[0] / 2, y0 + 38, 52)
    ctx.save()
    ctx.strokeStyle = 'rgba(130,210,255,0.45)'; ctx.lineWidth = 1
    ctx.strokeRect(x0 + 30.5, y0 + 70.5, menuSize[0] - 30 * 2, 215)
    // faint grid inside the frame
    ctx.strokeStyle = THEME.grid.minor
    ctx.beginPath()
    for (let gx = x0 + 30.5 + 20; gx < x0 + menuSize[0] - 30; gx += 20) { ctx.moveTo(gx, y0 + 71); ctx.lineTo(gx, y0 + 285) }
    for (let gy = y0 + 70.5 + 20; gy < y0 + 285; gy += 20) { ctx.moveTo(x0 + 31, gy); ctx.lineTo(x0 + menuSize[0] - 30, gy) }
    ctx.stroke()
    ctx.restore()

    const x1 = x0 + 50, y1 = y0 + 120, x2 = x0 + 320, y2 = y0 + 270
    const bx = x0 + 220, by = y0 + 180, r = 30
    const R = sketchRng(sketchSeed([x1, y1, x2, y2, 9]))
    ctx.save()
    ctx.shadowColor = THEME.coral; ctx.shadowBlur = 8
    handLine(ctx, R, x1, y1, x2, y2, THEME.coral, 2.4, 2, 1.2, 0)
    handCircle(ctx, R, x1, y1, 5, THEME.coral, 1.6)
    handCircle(ctx, R, x2, y2, 5, THEME.coral, 1.6)
    ctx.restore()
    hatch(ctx, () => { ctx.beginPath(); ctx.arc(bx, by, r, -Math.PI / 4, Math.PI * 3 / 4); ctx.closePath() },
        bx - r, by - r, r * 2, r * 2, -Math.PI / 4, 3.6, THEME.ink, 1, .8)
    ctx.save()
    ctx.shadowColor = 'rgba(190,230,255,0.55)'; ctx.shadowBlur = 8
    handCircle(ctx, R, bx, by, r, THEME.ink, 2, 1.05)
    ctx.strokeStyle = THEME.ink; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(bx - 5, by); ctx.lineTo(bx + 5, by); ctx.moveTo(bx, by - 5); ctx.lineTo(bx, by + 5); ctx.stroke()
    ctx.restore()
}
function guide()
{
    // Level-1 tutorial hints: bright coral handwritten text with a glow pass, hand-drawn
    // arrows and target rings at the points to click. Seeded rng -> identical every frame.
    if (thisLevel == 0)
    {
        const R = sketchRng(1161), col = THEME.coral
        ctx.save()
        ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'
        ctx.fillStyle = col; ctx.shadowColor = 'rgba(255,106,85,0.9)'
        for (const blur of [16, 0])
        {
            ctx.shadowBlur = blur
            ctx.font = '700 34px ' + THEME.fontStack
            ctx.fillText('Click here', 800, 156)
            ctx.fillText('and here', 262, 482)
            ctx.font = '700 30px ' + THEME.fontStack
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
