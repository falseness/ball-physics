// Path preview (the dotted line while a player line is being drawn).
//
// Progressive (TASK-085): input handlers only call request(coords); the game loop calls
// update(budgetMs) once per frame before draw(). update() validates the newest target with
// addNewLine() (refused -> the previous job and positions stay, as before) and then runs the current
// job in slices of up to STEP_CHUNK gamePhysics() steps for up to budgetMs (at least one slice per
// frame; TASK-086: a whole point is cyclesPerTact = 500 steps, 70-120 ms under 6x CPU throttling, too
// coarse a floor). A point's position is pushed once its cyclesPerTact steps are done. A job owns its
// ball position/speed and its own portalState copy, so each slice starts where the previous one
// stopped and leaves the real ball, portalState and lines untouched.
// The finished pointsCount positions equal calcSync() (the old synchronous algorithm, kept for tests).
// gamePhysics() steps per update() slice (the per-frame floor); positions match any chunk size
const STEP_CHUNK = 50
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

        this.target = null      // latest requested end point (logical coords), null = nothing new
        this.job = null         // {x2, y2, ballX, ballY, speedX, speedY, portal, step, positions, teleports}
    }
    // Input handlers: remember the newest end point only (no physics here)
    request(coords)
    {
        this.target = [coords[0], coords[1]]
    }
    // Drop the running job (line placed, level (re)started, physics started)
    cancel()
    {
        this.target = null
        this.job = null
    }
    get busy()
    {
        return this.job !== null
    }
    // Game loop, once per frame: (re)start for a new target, then compute for up to budgetMs
    update(budgetMs = 6)
    {
        if (!line || !this.drawEnable)
        {
            this.cancel()
            return
        }
        const start = performance.now()
        if (this.target)
        {
            const t = this.target
            this.target = null
            this.startJob(t)
        }
        const job = this.job
        if (!job)
            return
        do
            this.runSlice(job, STEP_CHUNK)
        while (job.positions.length < this.pointsCount && performance.now() - start < budgetMs)
        if (job.positions.length >= this.pointsCount)
        {
            this.lastTeleports = job.teleports  // diagnostics: teleports in the finished preview
            this.job = null
        }
    }
    startJob(coords)
    {
        if (!addNewLine(coords))    // refused: keep the previous job/positions
            return
        unfastenLastLine()
        this.job = {
            x2: line.posX2, y2: line.posY2,
            ballX: ball.getX(), ballY: ball.getY(), speedX: ball.speedX, speedY: ball.speedY,
            portal: portalCopy(portalState),
            step: 0,            // steps done in the current point (0..cyclesPerTact-1)
            positions: [],
            teleports: 0
        }
        this.positions = this.job.positions
        this.drawed = true
    }
    // Up to maxSteps steps of the job's current point, on the job's own state; pushes the point's
    // position when its cyclesPerTact steps are complete
    runSlice(job, maxSteps)
    {
        const lx2 = line.posX2, ly2 = line.posY2
        const bx = ball.posX, by = ball.posY, vx = ball.speedX, vy = ball.speedY
        const realPortal = portalState
        line.posX2 = job.x2
        line.posY2 = job.y2
        lines.push(line)
        ball.posX = job.ballX; ball.posY = job.ballY
        ball.speedX = job.speedX; ball.speedY = job.speedY
        portalState = job.portal
        const n = Math.min(maxSteps, cyclesPerTact - job.step)
        for (let j = 0; j < n; ++j)
            gamePhysics()
        job.step += n
        if (job.step >= cyclesPerTact)
        {
            job.step = 0
            job.positions.push({x: ball.getX(), y: ball.getY()})
        }
        job.ballX = ball.posX; job.ballY = ball.posY
        job.speedX = ball.speedX; job.speedY = ball.speedY
        job.portal = portalState
        job.teleports = portalState.teleports.length
        portalState = realPortal
        ball.posX = bx; ball.posY = by
        ball.speedX = vx; ball.speedY = vy
        unfastenLastLine()
        line.posX2 = lx2
        line.posY2 = ly2
    }
    // Test-only: the pre-TASK-085 synchronous preview (100 x cyclesPerTact steps at once)
    calcSync(coords)
    {
        if (line)
        {
            if (!addNewLine(coords))
                return

            this.job = null
            this.target = null
            this.positions = []

            let ballStartX = ball.getX()
            let ballStartY = ball.getY()

            const portalSaved = portalSave()

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
            portalRestore(portalSaved)
        }
    }
    setDrawEnable(input)
    {
        this.drawEnable = input
        this.cancel()
        if (!this.drawEnable)
            this.positions = []
    }
    // Predicted path: small hollow cyan circles, fading along the path (a partial path fades
    // exactly like the same points of the finished one)
    draw()
    {
        if (!this.drawEnable || this.positions.length == 0)
            return
        ctx.save()
        ctx.strokeStyle = this.color
        ctx.lineWidth = 1.2
        const n = this.positions.length
        const N = Math.max(n, this.pointsCount)
        let lx = -1e9, ly = -1e9
        for (let i = 0; i < n; ++i)
        {
            const p = this.positions[i]
            if (Math.hypot(p.x - lx, p.y - ly) < this.spacing)     // skip circles that would overlap the previous one
                continue
            lx = p.x; ly = p.y
            ctx.globalAlpha = 0.9 * (N - i) / N
            ctx.beginPath(); ctx.arc(p.x, p.y, this.dotRadius, 0, Math.PI * 2); ctx.stroke()
        }
        ctx.restore()
    }
}
let bounce = new Bounce()
