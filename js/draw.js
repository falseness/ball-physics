// Cached page background for the "61 Noir" style: navy gradient, soft exposure
// blotches, engineering grid, vignette and static film grain. Built once into an
// offscreen canvas by buildBackground() (and again only on window resize), then
// blitted every frame by draw(). Purely visual: no gameplay values.
let bgCanvas = null
window.bgBuildCount = 0
function bgRng(seed)
{
    return function() { return (seed = (seed * 16807) % 2147483647) / 2147483647 }
}
function buildBackground()
{
    let W = canvas.width, H = canvas.height
    if (!bgCanvas)
        bgCanvas = document.createElement('canvas')
    bgCanvas.width = W
    bgCanvas.height = H
    let g = bgCanvas.getContext('2d')
    let R = bgRng(6161)

    // diagonal navy gradient + ~40 soft radial exposure blotches (seeded)
    let grad = g.createLinearGradient(0, 0, W, H)
    grad.addColorStop(0, THEME.bg[0])
    grad.addColorStop(0.5, THEME.bg[1])
    grad.addColorStop(1, THEME.bg[2])
    g.fillStyle = grad
    g.fillRect(0, 0, W, H)
    for (let i = 0; i < 40; i++)
    {
        let x = R() * W, y = R() * H, r = 80 + R() * 300
        let rg = g.createRadialGradient(x, y, 0, x, y, r)
        rg.addColorStop(0, R() < 0.6 ? THEME.blot[0] : THEME.blot[1])
        rg.addColorStop(1, 'rgba(0,0,0,0)')
        g.fillStyle = rg
        g.fillRect(x - r, y - r, 2 * r, 2 * r)
    }

    // engineering grid: 16px minor / 80px major, x 40..W-30, y 30..H-30 (no header)
    g.lineWidth = 1
    let grids = [[16, THEME.grid.minor], [80, THEME.grid.major]]
    for (let k = 0; k < grids.length; k++)
    {
        let step = grids[k][0]
        g.strokeStyle = grids[k][1]
        g.beginPath()
        for (let x = 40.5; x <= W - 30; x += step)
        {
            g.moveTo(x, 30)
            g.lineTo(x, H - 30)
        }
        for (let y = 30.5; y <= H - 30; y += step)
        {
            g.moveTo(40, y)
            g.lineTo(W - 30, y)
        }
        g.stroke()
    }

    // vignette
    let vg = g.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35, W / 2, H / 2, Math.hypot(W, H) / 2)
    vg.addColorStop(0, 'rgba(0,4,12,0)')
    vg.addColorStop(1, 'rgba(0,4,12,0.6)')
    g.fillStyle = vg
    g.fillRect(0, 0, W, H)

    // static film grain: seeded 256px noise tile, overlay-blended once
    let tile = document.createElement('canvas')
    tile.width = tile.height = 256
    let tg = tile.getContext('2d'), img = tg.createImageData(256, 256), TR = bgRng(61)
    for (let i = 0; i < img.data.length; i += 4)
    {
        let v = TR() * 255
        img.data[i] = img.data[i + 1] = img.data[i + 2] = v
        img.data[i + 3] = 255
    }
    tg.putImageData(img, 0, 0)
    g.save()
    g.globalAlpha = 0.07
    g.globalCompositeOperation = 'overlay'
    g.fillStyle = g.createPattern(tile, 'repeat')
    g.fillRect(0, 0, W, H)
    g.restore()

    window.bgBuildCount++
}
window.addEventListener('resize', function() { if (bgCanvas) buildBackground() })

function drawIcons()
{
    drawStartIcon()
    drawLinesK()
    menuIcon()
}
function draw()
{
    if (!bgCanvas)
        buildBackground()
    ctx.drawImage(bgCanvas, 0, 0)
    
    guide()
    drawIcons()


    drawFlag(levels[thisLevel].flagX, levels[thisLevel].flagY, '#ff0000', '#ff0000')
    drawLines()
    
    bounce.draw()
    
    ball.draw()
    drawNewLine()
    levelCompleted()
}