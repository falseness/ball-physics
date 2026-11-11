let flagCoords = 
[
    [-9, 0],
    [-9, -99],
    [0, -99], 
    [50, -75],
    [0, -50]
], flag = []

// Ice pole + coral-hatched pennant, built from the rotated `flag` polygon (see levelChoosed),
// so levels with flagRotate render the pennant attached to its pole.
// flag[0..2] + origin = pole rectangle, flag[2..4] = pennant triangle (flag[2] and flag[4] lie on the pole).
function drawFlag(x, y, poleColor, pennantColor)
{
    if (flag.length < 5)
        return
    const P = flag.map(p => [x + p[0], y + p[1]])
    const R = sketchRng(sketchSeed([x, y, P[3][0], P[3][1]]))
    const tri = [P[2], P[3], P[4]]
    const xs = tri.map(p => p[0]), ys = tri.map(p => p[1])
    const bx = Math.min(...xs), by = Math.min(...ys)
    hatch(ctx, () => { ctx.beginPath(); ctx.moveTo(...tri[0]); ctx.lineTo(...tri[1]); ctx.lineTo(...tri[2]); ctx.closePath() },
        bx, by, Math.max(...xs) - bx, Math.max(...ys) - by, Math.PI / 4, 4, pennantColor, 1.4, .9)
    ctx.save()
    ctx.shadowColor = 'rgba(255,106,85,0.6)'; ctx.shadowBlur = 8
    handLine(ctx, R, P[2][0], P[2][1], P[3][0], P[3][1], pennantColor, 1.6, 2, 0.8, 1)
    handLine(ctx, R, P[3][0], P[3][1], P[4][0], P[4][1], pennantColor, 1.6, 2, 0.8, 1)
    ctx.shadowColor = 'rgba(190,230,255,0.55)'
    // pole along the edge the pennant hangs from: origin -> flag[2]
    handLine(ctx, R, x, y, P[2][0], P[2][1], poleColor, 2.6, 2, 0.6, 1)
    ctx.fillStyle = poleColor
    ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill()
    ctx.restore()
}
function flagLineCollision(x1, y1, x2, y2, x0, y0, r)
{
    if (x1 == x2)
    {
        let root1 = y0 + Math.sqrt(Math.pow(r, 2) - Math.pow(x1 - x0, 2))
        let root2 = y0 - Math.sqrt(Math.pow(r, 2) - Math.pow(x1 - x0, 2))
        if (root1 < y1 && y2 < root1 ||
                root1 < y2 && y1 < root1 ||
                root2 < y1 && y2 < root2 ||
                root2 < y2 && y1 < root2)
            return true
    }
    else if (collisionCircleWithLine(x1, y1, x2, y2, x0, y0, r))
        return true
    return false
}
function flagCollision(x, y)
{
    for (let i = 1; i < flag.length; ++i)
    {
        if (flagLineCollision(flag[i][0] + x, flag[i][1] + y, flag[i - 1][0] + x, flag[i - 1][1] + y, ball.posX, ball.posY, ball.radius))
                return true
    }
    return false
}
function pointRotation(x, y, angle)
{
    return [x * Math.cos(angle) + y * Math.sin(angle), y * Math.cos(angle) - x * Math.sin(angle)]
}
