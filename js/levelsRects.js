let rectMarginTop = 525
let rectMarginLeft = 25
let rectSize = 50 
// rows of 5 squares, 60 px apart (levels 1-5, 6-10, 11-15, 16-20; the panel fits 4 rows)
function levelRectXY(i)
{
    return [menuCoords[0] + rectMarginLeft + (rectMarginLeft + rectSize) * (i % 5),
            menuCoords[1] + rectMarginTop + Math.floor(i / 5) * 60]
}
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
        const [x, y] = levelRectXY(i)
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
        const r = levelRectXY(i)
        if (levels[i].unlock && collisionWithRect(x, y, r[0], r[1], r[0] + rectSize, r[1] + rectSize))
        {
            thisLevel = i
            playtestLevel = null // picking a real level ends a play-test
            levelChoosed(thisLevel)
            drawMenu = false
            levelCompletedWindow = false
            drawMenuIcon = true 
            return true
        }
    }
    return false
}