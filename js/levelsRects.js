let rectMarginTop = 525
let rectMarginLeft = 25
let rectSize = 50 
// Level grid: locked = dim navy outline, unlocked = cyan outline, completed = coral fill.
// Square positions are the same expressions levelsRectCollision() uses.
function drawLevels()
{
    // indexed by levels[i].unlock: 0 locked, 1 unlocked, 2 completed
    const fill = ['rgba(10,30,55,0.6)', 'rgba(130,210,255,0.08)', 'rgba(255,106,85,0.85)']
    const stroke = ['rgba(92,200,255,0.22)', THEME.cyan, THEME.coral]
    const text = ['rgba(159,198,230,0.4)', THEME.ink, '#071a30']

    ctx.save()
    ctx.font = "bold 36px " + THEME.fontStack
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    for (let i = 0; i < levels.length; ++i)
    {
        const u = levels[i].unlock
        const x = menuCoords[0] + rectMarginLeft + (rectMarginLeft + rectSize) * (i - 5 * (i > 4))
        const y = menuCoords[1] + rectMarginTop + (i > 4) * 60
        ctx.fillStyle = fill[u]
        ctx.fillRect(x, y, rectSize, rectSize)
        ctx.strokeStyle = stroke[u]; ctx.lineWidth = 1.5
        ctx.shadowColor = u ? stroke[u] : 'transparent'; ctx.shadowBlur = u ? 6 : 0
        ctx.strokeRect(x, y, rectSize, rectSize)
        ctx.shadowBlur = 0
        ctx.fillStyle = text[u]
        ctx.fillText(i + 1, x + rectSize / 2, y + rectSize / 2 + 2)
    }
    ctx.restore()
}
function levelsRectCollision(x, y)
{
    for (let i = 0; i < levels.length; ++i)
    {
        if (levels[i].unlock && collisionWithRect(x, y, menuCoords[0] + rectMarginLeft + (rectMarginLeft + rectSize) * (i - 5 * (i > 4)),
                          menuCoords[1] + rectMarginTop + (i > 4) * 60, 
                          menuCoords[0] + rectMarginLeft + (rectMarginLeft + rectSize) * (i - 5 * (i > 4)) + rectSize,
                          menuCoords[1] + rectMarginTop + rectSize + (i > 4) * 60))
        {
            thisLevel = i
            levelChoosed(thisLevel)
            drawMenu = false
            levelCompletedWindow = false
            drawMenuIcon = true 
            return true
        }
    }
    return false
}