let lineColor = '#0000ff'
let levelLineColor = '#3e1170'
let lines = []

let line = false
let dotRadius = 5
const LINE_HATCH_DEPTH = 14
const LINE_GLOW_INK = 'rgba(190,230,255,0.55)'
const LINE_GLOW_CORAL = 'rgba(255,106,85,0.6)'
class Line extends Sprite
{
    constructor(posX, posY, posX2, posY2, radius, color, type)
    {
        super(posX, posY, 0, 0, color, type)
        this.posX2 = posX2
        this.posY2 = posY2
        this.radius = radius
    }
    // Stable per-line rng: seeded from the line's own coordinates, so every frame draws the same stroke
    sketchR()
    {
        return sketchRng(sketchSeed([this.posX, this.posY, this.posX2, this.posY2]))
    }
    // Level line: ice ink, hand-drawn, soft glow, solid end dots, hatching on the underside if slope < 60 deg
    drawLevel()
    {
        const R = this.sketchR(), x1 = this.posX, y1 = this.posY, x2 = this.posX2, y2 = this.posY2
        const slope = Math.abs(Math.atan2(y2 - y1, x2 - x1)) * 180 / Math.PI
        if (Math.min(slope, 180 - slope) < 60 && Math.hypot(x2 - x1, y2 - y1) > 1)
        {
            const d = LINE_HATCH_DEPTH
            let a = Math.atan2(y2 - y1, x2 - x1)          // hatch at 45 deg to the line itself
            if (a > Math.PI / 2) a -= Math.PI
            if (a <= -Math.PI / 2) a += Math.PI
            hatch(ctx, () => { ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.lineTo(x2, y2 + d); ctx.lineTo(x1, y1 + d); ctx.closePath() },
                Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1) + d, a + Math.PI * .75, 7, THEME.ink, 1.1, .6)
        }
        ctx.save()
        ctx.shadowColor = LINE_GLOW_INK; ctx.shadowBlur = 10
        handLine(ctx, R, x1, y1, x2, y2, THEME.ink, 2.6, 2, 0.6, 4)
        ctx.fillStyle = THEME.ink
        ctx.beginPath(); ctx.arc(x1, y1, 3.5, 0, Math.PI * 2); ctx.arc(x2, y2, 3.5, 0, Math.PI * 2); ctx.fill()
        ctx.restore()
    }
    // Player line: coral, hand-drawn, same glow, hollow ring ends
    drawPlayer()
    {
        const R = this.sketchR(), x1 = this.posX, y1 = this.posY, x2 = this.posX2, y2 = this.posY2
        ctx.save()
        ctx.shadowColor = LINE_GLOW_CORAL; ctx.shadowBlur = 10
        handLine(ctx, R, x1, y1, x2, y2, THEME.coral, 2.8, 1, 0.5, 2)
        handCircle(ctx, R, x1, y1, 6, THEME.coral, 1.8)
        handCircle(ctx, R, x2, y2, 6, THEME.coral, 1.8)
        ctx.restore()
    }
    draw()
    {
        if (this.type == 'player')
            this.drawPlayer()
        else
            this.drawLevel()
    }
}

function drawLines()
{
    for (let i = 0; i < lines.length; ++i)
        lines[i].draw()
}