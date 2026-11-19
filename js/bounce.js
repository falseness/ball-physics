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
// The finished job.count positions (TASK-118: pointsCount, portalPointsCount on portal levels) equal calcSync() (the old synchronous algorithm, kept for tests).
// Idle mode (TASK-111): before the first click (no line being drawn, run not started, no menu/editor)
// update() shows the trail of the level as it is: an idle job simulates `lines` unchanged (no new
// line), from the ball start with speed 0, in the same slices/budget; it restarts only when the
// state signature (ball start, lines, level) changes. Once a run starts or the editor is open the
// trail is hidden (positions = [], no job).
// TASK-112: the idle trail also runs while an end of a player line is dragged (live, from the
// moved end); while the dragged segment is too close to the ball the last valid trail is kept.
// gamePhysics() steps per update() slice (the per-frame floor); positions match any chunk size
const STEP_CHUNK = 50
class Bounce
{
    constructor()
    {
        this.drawEnable = true
        this.positions = []

        this.pointsCount = 100          // points of a preview on a portal-free level
        this.portalPointsCount = 300    // TASK-118: 3x longer on levels with a portal pair

        this.color = THEME.cyan
        this.dotRadius = 4
        this.spacing = 6

        this.target = null      // latest requested end point (logical coords), null = nothing new
        this.job = null         // {idle, x2, y2, ballX, ballY, speedX, speedY, portal, step, positions, teleports}
        this.idleSig = null     // signature of the state the current/finished idle job was started for
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
    // TASK-118: preview length for a level object (portal pair -> portalPointsCount)
    countForLevel(lv)
    {
        return lv && lv.portals && lv.portals.length ? this.portalPointsCount : this.pointsCount
    }
    // Preview length for the level being played (decided when a job starts, stored as job.count)
    curCount()
    {
        return this.countForLevel(curLevel())
    }
    get busy()
    {
        return this.job !== null
    }
    // Game loop, once per frame: (re)start for a new target, then compute for up to budgetMs
    update(budgetMs = 6)
    {
        if (!this.drawEnable)
        {
            this.cancel()
            this.idleSig = null
            return
        }
        const start = performance.now()
        if (!line)
        {
            this.target = null
            if (!this.idleWanted())
            {
                // run started / menu / editor: no trail
                this.job = null
                this.idleSig = null
                this.positions = []
                return
            }
            if (this.dragRefused())
                return  // dragged end in the refused zone: keep the last valid trail, no job
            const sig = this.idleSignature()
            if (sig !== this.idleSig)
            {
                this.idleSig = sig
                this.startIdleJob()
            }
        }
        else
        {
            this.idleSig = null
            if (this.job && this.job.idle)
                this.job = null     // drawing: the idle job no longer applies
        }
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
        while (job.positions.length < job.count && performance.now() - start < budgetMs)
        if (job.positions.length >= job.count)
        {
            this.lastTeleports = job.teleports  // diagnostics: teleports in the finished preview
            this.job = null
        }
    }
    // Idle trail wanted: nothing being drawn, run not started, no menu / editor / level-completed window
    idleWanted()
    {
        return !line && this.drawEnable && !levelStarted && !physics && !editorMode && !drawMenu && !levelCompletedWindow
    }
    // TASK-112: an end of a player line is being dragged (js/select.js) and the dragged segment
    // passes within ball.radius of the ball centre (the drop would be refused)
    dragRefused()
    {
        if (typeof endDrag == 'undefined' || !endDrag || !lines[endDrag.li])
            return false
        const l = lines[endDrag.li]
        return pointSegDist(ball.posX, ball.posY, l.posX, l.posY, l.posX2, l.posY2) <= ball.radius
    }
    // Cheap state signature for the idle trail: level, ball start, every line's ends
    idleSignature()
    {
        let s = (playtestLevel ? 'p' : 'l' + thisLevel) + ':' + ball.posX + ',' + ball.posY + ':' + lines.length
        for (let i = 0; i < lines.length; ++i)
        {
            const l = lines[i]
            s += ';' + l.posX + ',' + l.posY + ',' + l.posX2 + ',' + l.posY2
        }
        // a play-test level object is compared by identity
        if (playtestLevel !== this.idleLevel)
        {
            this.idleLevel = playtestLevel
            this.idleLevelGen = (this.idleLevelGen || 0) + 1
        }
        return s + ':' + (this.idleLevelGen || 0)
    }
    startIdleJob()
    {
        this.job = {
            idle: true,
            count: this.curCount(),
            ballX: ball.getX(), ballY: ball.getY(), speedX: 0, speedY: 0,
            portal: portalCopy(portalState),
            step: 0,
            positions: [],
            teleports: 0
        }
        this.positions = this.job.positions
        this.positionsCount = this.job.count
    }
    startJob(coords)
    {
        if (!addNewLine(coords))    // refused: keep the previous job/positions
            return
        unfastenLastLine()
        this.job = {
            x2: line.posX2, y2: line.posY2,
            count: this.curCount(),
            ballX: ball.getX(), ballY: ball.getY(), speedX: ball.speedX, speedY: ball.speedY,
            portal: portalCopy(portalState),
            step: 0,            // steps done in the current point (0..cyclesPerTact-1)
            positions: [],
            teleports: 0
        }
        this.positions = this.job.positions
        this.positionsCount = this.job.count
        this.drawed = true
    }
    // Up to maxSteps steps of the job's current point, on the job's own state; pushes the point's
    // position when its cyclesPerTact steps are complete
    runSlice(job, maxSteps)
    {
        const idle = job.idle   // idle: simulate `lines` as they are (no line pushed)
        const lx2 = idle ? 0 : line.posX2, ly2 = idle ? 0 : line.posY2
        const bx = ball.posX, by = ball.posY, vx = ball.speedX, vy = ball.speedY
        const realPortal = portalState
        if (!idle)
        {
            line.posX2 = job.x2
            line.posY2 = job.y2
            lines.push(line)
        }
        ball.posX = job.ballX; ball.posY = job.ballY
        ball.speedX = job.speedX; ball.speedY = job.speedY
        portalState = job.portal
        const n = Math.min(maxSteps, cyclesPerTact - job.step)
        const frozen = portalFreeze(true)    // TASK-123: lines / portals are fixed inside a slice
        try
        {
            for (let j = 0; j < n; ++j)
                gamePhysics()
        }
        finally
        {
            portalFreeze(frozen)
        }
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
        if (!idle)
        {
            unfastenLastLine()
            line.posX2 = lx2
            line.posY2 = ly2
        }
    }
    // Test-only: the idle trail computed synchronously (lines as they are, ball start, speed 0);
    // returns the curCount() positions and restores ball / portal state
    calcSyncIdle()
    {
        const bx = ball.posX, by = ball.posY, vx = ball.speedX, vy = ball.speedY
        const portalSaved = portalSave()
        ball.speedX = 0
        ball.speedY = 0
        const out = []
        const count = this.curCount()
        const frozen = portalFreeze(true)
        try
        {
            for (let i = 0; i < count; ++i)
            {
                for (let j = 0; j < cyclesPerTact; ++j)
                    gamePhysics()
                out.push({x: ball.getX(), y: ball.getY()})
            }
        }
        finally
        {
            portalFreeze(frozen)
        }
        ball.posX = bx; ball.posY = by
        ball.speedX = vx; ball.speedY = vy
        portalRestore(portalSaved)
        return out
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

            const count = this.curCount()
            this.positionsCount = count
            const frozen = portalFreeze(true)
            try
            {
                for (let i = 0; i < count; ++i)
                {
                    for (let j = 0; j < cyclesPerTact; ++j)
                    {
                        gamePhysics()
                    }
                    this.positions.push({x: ball.getX(), y: ball.getY()})
                }
            }
            finally
            {
                portalFreeze(frozen)
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
        const N = Math.max(n, this.positionsCount || this.pointsCount)  // fade over the job's count
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
