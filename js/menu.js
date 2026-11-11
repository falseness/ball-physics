let menuTextRect = [250, 50]
let menuCoords = [canvas.width / 2, 50]
let menuSize = [400, 650]
let menuButtons = ['resume', 'restart', 'Levels']

function eclipse()
{
    ctx.beginPath()
    ctx.fillStyle = menuBackgroundColor
    ctx.rect(0, 0, canvas.width, canvas.height)
    ctx.fill()
    
    ctx.font = "30px Arial"
    ctx.textAlign = "center"
    ctx.closePath()
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
        ctx.beginPath()
        ctx.fillStyle = '#ffffff'
        ctx.strokeStyle = '#000000'
        ctx.rect(menuCoords[0], menuCoords[1], menuSize[0], menuSize[1])
        ctx.fill()
        ctx.fillStyle = menuColor
        
        for (let i = 0; i < menuButtons.length; ++i)
        {
            ctx.fillText(menuButtons[i], menuCoords[0] + menuSize[0] / 2, menuCoords[1] + 335 + 85 * i)
            if (i == 2)
                continue
            ctx.rect(menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2, menuCoords[1] + 300 + i * 85, menuTextRect[0], menuTextRect[1])
        }
        ctx.stroke()
        ctx.closePath()
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
    const n = levels[thisLevel].lineK, x0 = canvas.width - 120, cy = 63 + 20 + 30
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
function drawLogo()
{
    ctx.beginPath()
    ctx.fillStyle = menuColor
    ctx.textAling = 'center'
    ctx.fillText('Ball physics', menuCoords[0] + menuSize[0] / 2, menuCoords[1] + 50)
    ctx.rect(menuCoords[0] + 30, menuCoords[1] + 70, menuSize[0] - 30 * 2, 215)
    ctx.strokeStyle = '#000000'
    ctx.stroke()
    ctx.closePath()
    
    ctx.beginPath()
    ctx.fillStyle = menuColor
    ctx.arc(menuCoords[0] + 220, menuCoords[1] + 180, 30, 0, Math.PI * 2, false)
    ctx.fill()
    ctx.closePath()
    
    ctx.beginPath()
    let x1 = menuCoords[0] + 50
    let y1 = menuCoords[1] + 120
    let x2 = menuCoords[0] + 320
    let y2 = menuCoords[1] + 270
        
    ctx.strokeStyle = lineColor
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke() 
    ctx.closePath()
    
    ctx.beginPath()
    ctx.fillStyle = lineColor
    ctx.arc(x1, y1, dotRadius, 0, Math.PI * 2, false)
    ctx.arc(x2, y2, dotRadius, 0, Math.PI * 2, false)
    ctx.fill()
    ctx.closePath()
}
function guide()
{
    if (thisLevel == 0)
    {
        ctx.textAlign = 'center'
        ctx.font = "20px Arial"
        ctx.beginPath()
        ctx.fillStyle = menuColor
        ctx.fillText('Click here', 800, 160)
        ctx.fillText('and here', 260, 480)
        ctx.fillText('to draw line', 260, 500)
        ctx.closePath()
    }
}