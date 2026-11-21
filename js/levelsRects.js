let rectMarginTop = 525
let rectSize = 40
let rectCols = 8
let rectGap = 6
// rows of 8 squares (40 px, 46 px pitch), centred in the panel: grid +525..+749 for 5 rows
// (40 levels), below the 'Levels' heading and the win window's 'restart' button (+455..+505)
function levelRectXY(i)
{
    const left = (menuSize[0] - rectCols * rectSize - (rectCols - 1) * rectGap) / 2
    return [menuCoords[0] + left + (rectSize + rectGap) * (i % rectCols),
            menuCoords[1] + rectMarginTop + Math.floor(i / rectCols) * (rectSize + rectGap)]
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
    ctx.font = "bold 24px " + THEME.fontStack
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