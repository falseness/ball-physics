function collisionCircleWithLine(x1, y1, x2, y2, x0, y0, r)
{
    let k = (y1 - y2) / (x1 - x2)
    let b = y1 - k * x1
    /*
    ax^2 + bx + c = 0
    */
    let a = k * k + 1
    let c = x0 * x0 + b * b - 2 * y0 * b + y0 * y0 - r * r
    b = 2 * k * b - 2 * x0 - 2 * y0 * k
    let D = b * b - 4 * a * c
    if (D >= 0)
    {
        D = Math.sqrt(D)
        let root1 = (-b - D) / (2 * a)
        let root2 = (-b + D) / (2 * a)
        // x2 > x1
        if (root1 < x2 && x1 < root1 || 
            root2 < x2 && x1 < root2 ||
            root1 < x1 && x2 < root1 ||
            root2 < x1 && x2 < root2)
            return true
    }
    return false
}

class Ball extends Sprite
{
    constructor(radius, posX, posY, speedX, speedY, color, type)
    {
        super(posX, posY, speedX, speedY, color, type)
        this.radius = radius
        this.angle = 1
    }
    // Compass-drawn circle in ice ink: hatch shading on the lower-right half, small centre cross, soft glow.
    // rng is seeded from the radius only, so the stroke is identical every frame and just travels with the ball.
    draw()
    {
        const x = this.posX, y = this.posY, r = this.radius, R = sketchRng(sketchSeed([r, 61]))
        hatch(ctx, () => { ctx.beginPath(); ctx.arc(x, y, r, -Math.PI / 4, Math.PI * 3 / 4); ctx.closePath() },
            x - r, y - r, r * 2, r * 2, -Math.PI / 4, 3.2, THEME.ink, 1, .8)
        ctx.save()
        ctx.shadowColor = 'rgba(190,230,255,0.55)'; ctx.shadowBlur = 8
        handCircle(ctx, R, x, y, r, THEME.ink, 2, 1.05)
        ctx.strokeStyle = THEME.ink; ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(x - 4, y); ctx.lineTo(x + 4, y)
        ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4)
        ctx.stroke()
        ctx.restore()
    }
    // collisionWithDot's test alone (no side effects)
    dotHit(x, y)
    {
        return Math.pow(this.posX - x, 2) + Math.pow(this.posY - y, 2) < Math.pow(this.radius, 2) - 1
    }
    collisionWithDot(x, y)
    {
        if (this.dotHit(x, y))
        {//-1 - костыль, который чинит физику при колизии при скатывании
            this.speedX *= -1
            this.speedY *= -1
            return true
        }
        return false
    }
    // Collision with the segment (x1, y1)-(x2, y2) (the original per-line code); true = it reflected
    collisionWithSegment(x1, y1, x2, y2)
    {
        let x0 = this.posX
        let y0 = this.posY
        let r = this.radius
        
        if (x1 == x2)
        {
            let root1 = y0 + Math.sqrt(Math.pow(r, 2) - Math.pow(x1 - x0, 2))
            let root2 = y0 - Math.sqrt(Math.pow(r, 2) - Math.pow(x1 - x0, 2))
            //if (Math.pow(y1 - y0, 2) + Math.pow(x1 - x0, 2) <= Math.pow(this.radius, 2) && this.speedY > 0 ||
             //  Math.pow(y2 - y0, 2) + Math.pow(x2 - x0, 2) <= Math.pow(this.radius, 2) && this.speedY < 0)
             //   this.speedY *= -1
            if (root1 < y1 && y2 < root1 ||
                    root1 < y2 && y1 < root1 ||
                    root2 < y1 && y2 < root2 ||
                    root2 < y2 && y1 < root2)
            {
                this.speedX *= -1
                return true
            }
        }
        else if (collisionCircleWithLine(x1, y1, x2, y2, x0, y0, r))
        {
            let lineAngle = Math.atan((y1 - y2) / (x1 - x2))

            let xn = -this.speedX
            let yn = -this.speedY

            let x = xn * Math.cos(lineAngle) + yn * Math.sin(lineAngle)
            let y = yn * Math.cos(lineAngle) - xn * Math.sin(lineAngle)

            x = -x

            xn = x * Math.cos(lineAngle) - y * Math.sin(lineAngle)
            yn = y * Math.cos(lineAngle) + x * Math.sin(lineAngle)

            this.speedX = xn
            this.speedY = yn
            this.speedX += gravitationalAcceleration * Math.cos(lineAngle) * Math.sin(lineAngle)
            this.speedY -= gravitationalAcceleration * Math.pow(Math.cos(lineAngle), 2)
            return true
        }
        return false
    }
    collision()
    {
        //Добавь обработку коллизий с краями прямых
        // wall-portal host lines (null when the level has none): line object -> its resolved portals
        const hosts = portalHosts()
        for (let i = 0; i < lines.length; ++i)
        {
            const host = hosts && hosts.get(lines[i])
            // a ball being captured by a portal on this line ignores a line end next to the opening (TASK-074)
            // (dotHit first: when it is false collisionWithDot would do nothing, so the capture zone is not needed)
            if (host ? (this.dotHit(lines[i].posX, lines[i].posY) && !portalCaptureZone(this, host, lines[i].posX, lines[i].posY) && this.collisionWithDot(lines[i].posX, lines[i].posY)) ||
                       (this.dotHit(lines[i].posX2, lines[i].posY2) && !portalCaptureZone(this, host, lines[i].posX2, lines[i].posY2) && this.collisionWithDot(lines[i].posX2, lines[i].posY2))
                     : this.collisionWithDot(lines[i].posX, lines[i].posY) || this.collisionWithDot(lines[i].posX2, lines[i].posY2))
                break
            /*
            y1 = kx1 + b
            y2 = kx2 + b
            */
            if (host)
                portalHostCollision(this, lines[i], host)
            else
                this.collisionWithSegment(lines[i].posX, lines[i].posY, lines[i].posX2, lines[i].posY2)
        }
    }
    gravity()
    {
        this.speedY += gravitationalAcceleration
    }
    physics()
    {
        this.collision()
        this.gravity()
    }
    onMap()
    {
        return !(this.posX > GAME_W || this.posX < 0 || this.posY > GAME_H || this.posY < 0)
    }
}