class Bounce
{
    constructor()
    {
        this.drawEnable = true
        this.positions = []
        
        this.pointsCount = 100
        
        this.color = THEME.cyan
        this.dotRadius = 4
        this.spacing = 6
    }
    calc(coords)
    {
        if (line)   
        {
            if (!addNewLine(coords))
                return 

            const cycles = 1000
            this.positions = []

            let ballStartX = ball.getX()
            let ballStartY = ball.getY()

            for (let i = 0; i < this.pointsCount; ++i)
            {
                for (let j = 0; j < cyclesPerTact; ++j)
                {
                    gamePhysics()
                }
                this.positions.push({x: ball.getX(), y: ball.getY()})
            }
            this.drawed = true

            ball.setX(ballStartX)
            ball.setY(ballStartY)

            ball.setSpeedX(0)
            ball.setSpeedY(0)

            unfastenLastLine()
        }
    }
    setDrawEnable(input)
    {
        this.drawEnable = input
        if (!this.drawEnable)
            this.positions = []
    }
    // Predicted path: small hollow cyan circles, fading along the path
    draw()
    {
        if (!this.drawEnable || this.positions.length == 0)
            return
        ctx.save()
        ctx.strokeStyle = this.color
        ctx.lineWidth = 1.2
        const n = this.positions.length
        let lx = -1e9, ly = -1e9
        for (let i = 0; i < n; ++i)
        {
            const p = this.positions[i]
            if (Math.hypot(p.x - lx, p.y - ly) < this.spacing)     // skip circles that would overlap the previous one
                continue
            lx = p.x; ly = p.y
            ctx.globalAlpha = 0.9 * (n - i) / n
            ctx.beginPath(); ctx.arc(p.x, p.y, this.dotRadius, 0, Math.PI * 2); ctx.stroke()
        }
        ctx.restore()
    }
}
let bounce = new Bounce()