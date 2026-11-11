function mouseCoords(event)
{
    let rect = canvas.getBoundingClientRect()
    return [event.clientX - rect.left, event.clientY - rect.top]
}

function collisionTwoCircles(x1, y1, r1, x2, y2, r2)
{
    let d = Math.sqrt(Math.pow(x1 - x2, 2) + Math.pow(y1 - y2, 2))
    if (d < r1 + r2)
        return true
    return false
}
function dotСorrection(x, y, r)
{
    for (let i = 0; i < lines.length; ++i)
    {
        if (collisionTwoCircles(x, y, r, lines[i].posX, lines[i].posY, lines[i].radius))
            return [lines[i].posX, lines[i].posY]
        if (collisionTwoCircles(x, y, r, lines[i].posX2, lines[i].posY2, lines[i].radius))
            return [lines[i].posX2, lines[i].posY2]
    }
    return [x, y]
}

document.addEventListener('mousemove', function(event)
{
    if (line)
    {
        let coords = mouseCoords(event)
        line.posX2 = coords[0]
        line.posY2 = coords[1]
    }
})
// Line being drawn: faint construction line running 60px past both ends,
// a firmer 1.6px segment between the actual endpoints and a handwritten (x, y) readout of the cursor end
function drawNewLine()
{
    if (!line)
        return
    const x1 = line.posX, y1 = line.posY, x2 = line.posX2, y2 = line.posY2
    const len = Math.hypot(x2 - x1, y2 - y1)
    const a = len > 0 ? Math.atan2(y2 - y1, x2 - x1) : 0, ext = 60
    ctx.save()
    if (len > 0)
    {
        ctx.strokeStyle = THEME.soft; ctx.globalAlpha = .45; ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(x1 - Math.cos(a) * ext, y1 - Math.sin(a) * ext)
        ctx.lineTo(x2 + Math.cos(a) * ext, y2 + Math.sin(a) * ext)
        ctx.stroke()
        ctx.globalAlpha = 1
        handLine(ctx, sketchRng(sketchSeed([x1, y1, x2, y2])), x1, y1, x2, y2, THEME.ink, 1.6, 1, 0.5, 0)
    }
    ctx.fillStyle = THEME.ink
    ctx.beginPath(); ctx.arc(x1, y1, 2.5, 0, Math.PI * 2); ctx.fill()
    ctx.fillStyle = THEME.soft
    ctx.font = '20px ' + THEME.fontStack; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'
    ctx.fillText('(' + Math.round(x2) + ', ' + Math.round(y2) + ')', x2 + 14, y2 + 34)
    ctx.restore()
}