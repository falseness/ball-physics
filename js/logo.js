'use strict'
// TASK-265: the menu / win-window logo (concept 129, artifacts/logo/src/129-font-finger-paint.html).
// A tilted lockup: the title 'Ball physics' (THEME.fontStack) sits on a coral player line; the purple portal B at
// the high-left end and the orange portal A at the low-right end are drawn as tunnel holes; a comet trail leaves B
// with the game ball at its head and faint dots run on into A.
// Drawn in the concept's 400 x 290 logo space (panel-local coords of the concept sheet), scaled to fit the
// menuLayout() logo box (plus LOGO_PAD each side) and centred in it. Rendered once to an offscreen canvas and blitted every frame; rebuilt only
// when the box size, the backing-store scale or the font readiness changes (logoCache.builds counts the builds).
const LOGO_W = 400, LOGO_H = 290, LOGO_PAD = 12   // logo space; side margin for the portal glow (not clipped by the box)
// geometry of concept 49/108 (style.js G49): tilt, frame centre, title baseline, coral line, portals, arc height
const LOGO_G = {ang: .16, cx: 200, cy: 152, ty: 22, ly: 42, lx: 150, px: 168, py: 6, rx: 12, ry: 34, arcH: 92}
const LOGO_TITLE = 'Ball physics', LOGO_TITLE_W = 262, LOGO_HEAD = 52   // fitted title width; trail index of the ball
const logoCache = {canvas: null, key: '', builds: 0, x: 0, y: 0, w: 0, h: 0, scale: 1}

// (x, y, w, h) = the menuLayout() logo box in logical coords
function drawLogo(x, y, w, h)
{
    const s = Math.min(w / (LOGO_W + 2 * LOGO_PAD), h / LOGO_H), k = canvas.width / GAME_W
    const fontOk = !document.fonts || document.fonts.check('60px ' + THEME.fontStack)
    const key = [w, h, k, fontOk].join('|')
    logoCache.x = x; logoCache.y = y
    if (logoCache.key != key)
        logoBuild(w, h, s, k, key)
    ctx.drawImage(logoCache.canvas, x, y, w, h)
}
function logoBuild(w, h, s, k, key)
{
    const c = logoCache.canvas || document.createElement('canvas')
    c.width = Math.max(1, Math.round(w * k)); c.height = Math.max(1, Math.round(h * k))
    const g = c.getContext('2d')
    g.setTransform(1, 0, 0, 1, 0, 0)
    g.clearRect(0, 0, c.width, c.height)
    // box px -> logo space: scale s, centred
    g.setTransform(k * s, 0, 0, k * s, k * (w - LOGO_W * s) / 2, k * (h - LOGO_H * s) / 2)
    logoScene(g)
    Object.assign(logoCache, {canvas: c, key, w, h, scale: s, builds: logoCache.builds + 1})
}
function logoScene(g)
{
    const L = LOGO_G, A = logoArc(), B = PORTAL_STYLE[1], P = PORTAL_STYLE[0]
    g.save()
    g.translate(L.cx, L.cy); g.rotate(L.ang)
    logoTitle(g, L.ty)
    logoCoralBar(g, -L.lx, L.ly, L.lx, L.ly, 3)
    logoComet(g, A.slice(0, LOGO_HEAD + 1))
    logoDots(g, A.slice(LOGO_HEAD + 5), THEME.ink, 9, 1.6, .55)
    logoHole(g, -L.px, L.py, L.rx, L.ry, B, 1)
    logoHole(g, L.px, L.py, L.rx, L.ry, P, -1)
    logoBall(g, A[LOGO_HEAD][0], A[LOGO_HEAD][1], 14, 18)
    g.restore()
}
// the ball's arc, local frame: out of B's mouth, over the title, down into A's mouth (a projectile hop)
function logoArc()
{
    const L = LOGO_G, p0 = [-L.px + 16, L.py - 12], p1 = [L.px - 14, L.py - 4], out = []
    for (let i = 0; i <= 80; i++)
    {
        const u = i / 80
        out.push([p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u - 4 * L.arcH * u * (1 - u)])
    }
    return out
}
// title fitted to LOGO_TITLE_W, centred at x 0 on baseline y, soft ice glow
function logoTitle(g, y)
{
    g.save()
    g.font = '60px ' + THEME.fontStack
    const tw = g.measureText(LOGO_TITLE).width, f = LOGO_TITLE_W / tw
    g.translate(0, y); g.scale(f, f)
    g.textBaseline = 'alphabetic'; g.textAlign = 'left'
    g.fillStyle = THEME.ink
    g.shadowColor = 'rgba(160,215,255,.7)'; g.shadowBlur = 14 / f
    g.fillText(LOGO_TITLE, -tw / 2, 0)
    g.restore()
}
// crisp coral player line with hollow end dots
function logoCoralBar(g, x1, y1, x2, y2, w)
{
    g.save()
    g.strokeStyle = THEME.coral; g.lineWidth = w; g.lineCap = 'round'
    g.shadowColor = THEME.coral; g.shadowBlur = 12
    g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke()
    g.lineWidth = 2; g.shadowBlur = 6; g.fillStyle = '#0b2140'
    for (const [x, y] of [[x1, y1], [x2, y2]]) { g.beginPath(); g.arc(x, y, 5, 0, 2 * Math.PI); g.fill(); g.stroke() }
    g.restore()
}
// tapered glowing stroke: thin and faint at the tail, wide and bright at the head
function logoComet(g, pts)
{
    g.save(); g.lineCap = 'round'
    g.strokeStyle = g.shadowColor = 'rgb(223,243,255)'
    for (let i = 1; i < pts.length; i++)
    {
        const t = i / (pts.length - 1), e = Math.pow(t, 1.4)
        g.shadowBlur = 4 + 12 * t; g.globalAlpha = e; g.lineWidth = .4 + 5.6 * e
        g.beginPath(); g.moveTo(pts[i - 1][0], pts[i - 1][1]); g.lineTo(pts[i][0], pts[i][1]); g.stroke()
    }
    g.restore()
}
// evenly spaced dots along a path (arc length)
function logoDots(g, pts, color, every, r, alpha)
{
    g.save(); g.fillStyle = color; g.globalAlpha = alpha
    let d = 0, next = 0
    for (let i = 1; i < pts.length; i++)
    {
        const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], L = Math.hypot(x1 - x0, y1 - y0)
        while (next <= d + L)
        {
            const u = (next - d) / L
            g.beginPath(); g.arc(x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, r, 0, 2 * Math.PI); g.fill()
            next += every
        }
        d += L
    }
    g.restore()
}
// portal as a tunnel hole (local frame): light spill out of the mouth, dark interior lit at the edge, three inner
// rings receding into the wall, glowing rim with a hot core. facing +1 opens right, -1 opens left.
function logoHole(g, x, y, rx, ry, st, facing)
{
    const glow = a => st.glow.replace(/[\d.]+\)$/, a + ')')
    g.save()
    const sp = g.createRadialGradient(x + facing * 6, y, 2, x + facing * 10, y, ry * 1.5)
    sp.addColorStop(0, glow(.35)); sp.addColorStop(1, 'rgba(0,0,0,0)')
    g.fillStyle = sp; g.beginPath(); g.ellipse(x + facing * 14, y, ry * .9, ry * 1.3, 0, 0, 2 * Math.PI); g.fill()
    g.save(); g.translate(x, y); g.scale(rx / ry, 1)
    const inner = g.createRadialGradient(-facing * ry * .25, 0, 1, 0, 0, ry)
    inner.addColorStop(0, '#010409'); inner.addColorStop(.62, '#04101f'); inner.addColorStop(.86, glow(.35)); inner.addColorStop(1, st.color)
    g.fillStyle = inner; g.beginPath(); g.arc(0, 0, ry, 0, 2 * Math.PI); g.fill()
    g.restore()
    g.strokeStyle = st.color; g.lineWidth = 1
    for (let i = 1; i <= 3; i++)
    {
        g.globalAlpha = .5 - i * .12
        g.beginPath(); g.ellipse(x - facing * i * 3, y, rx * (1 - i * .22), ry * (1 - i * .2), 0, 0, 2 * Math.PI); g.stroke()
    }
    g.globalAlpha = 1
    g.lineWidth = 4.5; g.shadowColor = st.glow; g.shadowBlur = 22
    g.beginPath(); g.ellipse(x, y, rx, ry, 0, 0, 2 * Math.PI); g.stroke()
    g.shadowBlur = 0; g.strokeStyle = 'rgba(255,250,240,.85)'; g.lineWidth = 1.1; g.stroke()
    g.restore()
}
// the game ball, clean: ice ring, hatched lower-right half, soft glow, small cross (js/sketch.js hatch)
function logoBall(g, x, y, r, glow)
{
    g.save()
    hatch(g, () => { g.beginPath(); g.arc(x, y, r, -Math.PI / 4, Math.PI * 3 / 4); g.closePath() },
        x - r * 1.5, y - r * 1.5, r * 3, r * 3, -Math.PI / 4, Math.max(2.2, r * .26) * Math.SQRT2, THEME.ink, .9, .75)
    g.fillStyle = 'rgba(7,26,48,.35)'; g.beginPath(); g.arc(x, y, r, 0, 2 * Math.PI); g.fill()
    g.strokeStyle = THEME.ink; g.lineWidth = 1.8
    g.shadowColor = 'rgba(200,235,255,.8)'; g.shadowBlur = glow
    g.beginPath(); g.arc(x, y, r, 0, 2 * Math.PI); g.stroke()
    g.shadowBlur = 0; g.lineWidth = 1
    g.beginPath(); g.moveTo(x - r * .3, y); g.lineTo(x + r * .3, y); g.moveTo(x, y - r * .3); g.lineTo(x, y + r * .3); g.stroke()
    g.restore()
}
