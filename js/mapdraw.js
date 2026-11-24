'use strict'
// TASK-180: full-screen level route map (concept artifacts/concepts/routemap/305-wall-full.png). Input (TASK-181):
// mapOpen() from the pause menu's 'Levels' button, mapClick() for clicks / taps while the map is shown. Data: js/routemap.js (ROUTEMAP slots/branches/wall/portals/obstacles/hops, routeAssign).
// The whole map (background, floor, wall, portals, obstacles, hops, platforms, flags, lamp, ball) is rendered into
// an offscreen layer that is rebuilt only when the progress or the backing size changes, then blitted each frame.
// Level numbers on the map are the play-order numbers (index + 1); solved = levels[i].unlock == 2; the next level
// is the first unsolved one by number.
let drawMap = false
let mapCanvas = null, mapKey = ''
window.mapState = null
const MAP_FLOOR = 772
const MAP_COL = {
    solved: THEME.coral, open: 'rgba(130,210,255,0.95)', next: THEME.physicsOn,
    glow: { solved: '255,106,85', open: '130,210,255', next: '89,240,160' }
}
const MAP_LAMP_RGB = '225,240,255'

// state of every level by number: 'solved' / 'next' / 'open'
function mapLevelStates()
{
    const st = levels.map(l => l.unlock == 2 ? 'solved' : 'open')
    const next = st.indexOf('open')
    if (next >= 0) st[next] = 'next'
    return { st, next }
}

// soft additive radial glow
function mapGlow(g, x, y, r, rgb, a)
{
    g.save(); g.globalCompositeOperation = 'lighter'
    const gr = g.createRadialGradient(x, y, 0, x, y, r)
    gr.addColorStop(0, 'rgba(' + rgb + ',' + a + ')'); gr.addColorStop(1, 'rgba(' + rgb + ',0)')
    g.fillStyle = gr; g.fillRect(x - r, y - r, r * 2, r * 2); g.restore()
}

// glowing neon tube with hatching underneath (platforms and the floor line); k = thickness scale
function mapTube(g, x1, y, x2, k)
{
    g.save()
    const gr = g.createLinearGradient(0, y, 0, y + 30 * k)
    gr.addColorStop(0, 'rgba(130,210,255,0.22)'); gr.addColorStop(1, 'rgba(130,210,255,0)')
    g.fillStyle = gr; g.fillRect(x1, y, x2 - x1, 30 * k)
    g.strokeStyle = 'rgba(233,246,255,0.9)'; g.lineWidth = 4 * k; g.lineCap = 'round'
    g.shadowColor = THEME.cyan; g.shadowBlur = 18 * k; g.globalAlpha = .45
    g.beginPath(); g.moveTo(x1, y); g.lineTo(x2, y); g.stroke()
    g.globalAlpha = 1; g.shadowBlur = 0
    hatch(g, () => { g.beginPath(); g.rect(x1, y + 1.5 * k, x2 - x1, 10 * k) }, x1, y, x2 - x1, 12 * k, Math.PI * .75, 8 * k, THEME.ink, 1.1 * k, .6)
    g.shadowColor = LINE_GLOW_INK; g.shadowBlur = 8 * k
    handLine(g, sketchRng(sketchSeed([x1, y, x2, 180])), x1, y, x2, y, THEME.ink, 3 * k, 2, 0.5, 1)
    g.fillStyle = THEME.ink
    g.beginPath(); g.arc(x1, y, 3.5 * k, 0, Math.PI * 2); g.arc(x2, y, 3.5 * k, 0, Math.PI * 2); g.fill()
    g.restore()
}

// game-style hatched line (like a level line): glowing hand stroke plus short ticks on one side
function mapWallLine(g, x1, y1, x2, y2, w, a)
{
    const L = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / L, uy = (y2 - y1) / L
    g.save(); g.globalAlpha = a
    g.strokeStyle = THEME.ink; g.lineWidth = 1; g.globalAlpha = a * .55
    g.beginPath()
    for (let d = 4; d < L; d += 9)
    {
        const x = x1 + ux * d, y = y1 + uy * d
        g.moveTo(x, y); g.lineTo(x - 7 * ux - 9 * uy, y - 7 * uy + 9 * ux)
    }
    g.stroke()
    g.globalAlpha = a; g.shadowColor = LINE_GLOW_INK; g.shadowBlur = 8
    handLine(g, sketchRng(sketchSeed([x1, y1, x2, y2])), x1, y1, x2, y2, THEME.ink, w, 2, 0.5, 1)
    g.restore()
}

function mapBumper(g, o)
{
    mapGlow(g, o.x, o.y, o.r * 2.4, '130,210,255', 0.14)
    g.save(); g.shadowColor = THEME.cyan; g.shadowBlur = 12
    handCircle(g, sketchRng(sketchSeed([o.x, o.y, o.r])), o.x, o.y, o.r, THEME.ink, 2.5, 1.05)
    g.shadowBlur = 0; g.lineWidth = 1; g.strokeStyle = 'rgba(233,246,255,0.5)'
    g.beginPath(); g.arc(o.x, o.y, o.r * 0.62, 0, Math.PI * 2); g.stroke()
    g.fillStyle = THEME.ink; g.beginPath(); g.arc(o.x, o.y, 2.5, 0, Math.PI * 2); g.fill()
    g.restore()
}

function mapSpring(g, o)
{
    const x = o.x, y = o.y, h = o.h, w = o.w
    g.save(); g.strokeStyle = 'rgba(233,246,255,0.8)'; g.lineWidth = 1.6; g.shadowColor = THEME.cyan; g.shadowBlur = 6
    g.beginPath(); g.moveTo(x, y)
    for (let i = 1; i <= 8; i++) g.lineTo(x + (i % 2 ? w : -w), y - h * i / 9)
    g.lineTo(x, y - h); g.stroke()
    g.lineWidth = 2.5; g.beginPath()
    g.moveTo(x - 14, y - h); g.lineTo(x + 14, y - h); g.moveTo(x - 14, y); g.lineTo(x + 14, y); g.stroke()
    g.restore()
}

// hatched solid box (floor blocks, the central wall)
function mapBlock(g, x, y, w, h, gap)
{
    g.save(); g.fillStyle = 'rgba(4,16,32,0.75)'; g.fillRect(x, y, w, h); g.restore()
    hatch(g, () => { g.beginPath(); g.rect(x, y, w, h) }, x, y, w, h, -Math.PI / 4, gap, THEME.ink, 1, .35)
    g.save(); g.strokeStyle = 'rgba(233,246,255,0.8)'; g.lineWidth = 2; g.shadowColor = THEME.cyan; g.shadowBlur = 8
    g.strokeRect(x, y, w, h); g.restore()
}

function mapObstacle(g, o)
{
    if (o.kind === 'bumper') mapBumper(g, o)
    else if (o.kind === 'spring') mapSpring(g, o)
    else if (o.kind === 'block') mapBlock(g, o.x, o.y, o.w, o.h, 8)
    else mapWallLine(g, o.x1, o.y1, o.x2, o.y2, o.w, o.kind === 'ceiling' ? 0.6 : 0.85)
}

// wall portal opening: coloured bar on the wall face with a light fan along its normal (PORTAL_STYLE colours)
function mapPortal(g, p, style)
{
    const tx = -p.ny, ty = p.nx, h = p.h, c = style.color
    g.save()
    const gr = g.createLinearGradient(p.x, p.y, p.x + p.nx * 46, p.y + p.ny * 46)
    gr.addColorStop(0, style.glow.replace(/[\d.]+\)$/, '0.30)')); gr.addColorStop(1, 'rgba(0,0,0,0)')
    g.fillStyle = gr; g.beginPath()
    g.moveTo(p.x - tx * h, p.y - ty * h); g.lineTo(p.x + tx * h, p.y + ty * h)
    g.lineTo(p.x + tx * h * .8 + p.nx * 46, p.y + ty * h * .8 + p.ny * 46)
    g.lineTo(p.x - tx * h * .8 + p.nx * 46, p.y - ty * h * .8 + p.ny * 46)
    g.closePath(); g.fill()
    g.lineCap = 'round'; g.strokeStyle = c; g.lineWidth = 5; g.shadowColor = style.glow; g.shadowBlur = 16
    g.beginPath(); g.moveTo(p.x - tx * h, p.y - ty * h); g.lineTo(p.x + tx * h, p.y + ty * h); g.stroke()
    g.shadowBlur = 0; g.strokeStyle = 'rgba(255,245,230,0.8)'; g.lineWidth = 1.4; g.stroke()
    g.restore()
}

// dotted hop between two slot tops, via optional bounce points; 'gap' = portal crossing (nothing drawn)
function mapHop(g, a, b, via, coral)
{
    const pts = [[a[0], a[1] - 10]].concat(via || [], [[b[0], b[1] - 10]])
    g.save()
    g.strokeStyle = coral ? 'rgba(255,106,85,0.85)' : 'rgba(159,198,230,0.45)'
    g.lineWidth = 2.1; g.setLineDash([2, 6]); g.lineCap = 'round'
    if (coral) { g.shadowColor = g.strokeStyle; g.shadowBlur = 7 }
    const single = pts.length === 2
    for (let i = 0; i < pts.length - 1; i++)
    {
        const p = pts[i], q = pts[i + 1]
        if (p === 'gap' || q === 'gap') continue
        const d = Math.hypot(q[0] - p[0], q[1] - p[1])
        const lift = single ? 25 + Math.min(60, d * 0.3) : 14 + Math.min(34, d * 0.14)
        g.beginPath(); g.moveTo(p[0], p[1])
        g.quadraticCurveTo((p[0] + q[0]) / 2, Math.min(p[1], q[1]) - lift, q[0], q[1]); g.stroke()
    }
    g.restore()
}

// flag pin on a platform: pole + pennant (the game's flagCoords shape, scaled), number disc on the pole.
// solved = filled coral pennant + green check, open = outlined cyan, next = green.
function mapFlag(g, x, y, s, num, state)
{
    const k = s * 64 / 99, col = MAP_COL[state]
    const P = flagCoords.map(p => [x + p[0] * k + 9 * k, y + p[1] * k])  // pole on x (flagCoords pole is at -9)
    const tri = [P[2], P[3], P[4]], R = sketchRng(sketchSeed([x, y, num]))
    const path = () => { g.beginPath(); g.moveTo(...tri[0]); g.lineTo(...tri[1]); g.lineTo(...tri[2]); g.closePath() }
    const bx = Math.min(tri[0][0], tri[1][0], tri[2][0]), by = Math.min(tri[0][1], tri[1][1], tri[2][1])
    const bw = Math.max(tri[0][0], tri[1][0], tri[2][0]) - bx, bh = Math.max(tri[0][1], tri[1][1], tri[2][1]) - by
    mapGlow(g, x, y - 35 * s, 84 * s, MAP_COL.glow[state], 0.2)
    g.save()
    // shadow ellipse + base ring
    g.fillStyle = 'rgba(0,0,0,0.45)'; g.beginPath(); g.ellipse(x, y + 2 * s, 26 * s, 8 * s, 0, 0, Math.PI * 2); g.fill()
    // pole
    g.shadowColor = LINE_GLOW_INK; g.shadowBlur = 6
    handLine(g, R, x, y, x, P[2][1], THEME.ink, 2.5 * s, 2, 0.4, 0)
    // pennant
    g.shadowColor = col; g.shadowBlur = 14
    if (state !== 'open')
    {
        g.fillStyle = state === 'solved' ? 'rgba(255,106,85,0.9)' : 'rgba(89,240,160,0.85)'
        path(); g.fill()
    }
    g.lineWidth = 2.5 * s; g.lineJoin = 'round'; g.strokeStyle = col; path(); g.stroke()
    g.shadowBlur = 0
    g.restore()
    hatch(g, path, bx, by, bw, bh, Math.PI / 4, 4, state === 'solved' ? 'rgba(120,20,10,0.8)' : col, 1.1, state === 'open' ? .4 : .5)
    // number disc
    const dy = y - 20 * s, dr = 15 * s
    g.save()
    g.fillStyle = '#0b2747'; g.strokeStyle = col; g.lineWidth = 2
    g.beginPath(); g.arc(x, dy, dr, 0, Math.PI * 2); g.fill(); g.stroke()
    g.fillStyle = THEME.ink; g.font = Math.round(24 * s) + 'px ' + THEME.fontStack
    g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(String(num), x, dy + 1)
    // check mark on solved flags
    if (state === 'solved')
    {
        const cx = x + 30 * s, cy = y - 72 * s, c = 14 * s
        g.strokeStyle = THEME.physicsOn; g.lineWidth = 2.2; g.lineCap = 'round'; g.lineJoin = 'round'
        g.shadowColor = THEME.physicsOn; g.shadowBlur = 6
        g.beginPath(); g.moveTo(cx - c * .45, cy); g.lineTo(cx - c * .1, cy + c * .35); g.lineTo(cx + c * .5, cy - c * .4); g.stroke()
    }
    g.restore()
}

// trapezoid light cone from under a platform down to the floor
function mapConePath(g, x1, x2, top, spread, inset)
{
    g.beginPath(); g.moveTo(x1 + inset, top); g.lineTo(x2 - inset, top)
    g.lineTo(x2 + spread, MAP_FLOOR); g.lineTo(x1 - spread, MAP_FLOOR); g.closePath()
}

// the single lamp: soft cone, floor pool, and the grid lit inside the cone
function mapLamp(g, x1, x2, y)
{
    const top = y + 6, spread = 30, inset = 8
    g.save(); g.globalCompositeOperation = 'lighter'; g.filter = 'blur(5px)'
    const gr = g.createLinearGradient(0, top, 0, MAP_FLOOR)
    gr.addColorStop(0, 'rgba(' + MAP_LAMP_RGB + ',0.26)'); gr.addColorStop(1, 'rgba(' + MAP_LAMP_RGB + ',0.05)')
    g.fillStyle = gr; mapConePath(g, x1, x2, top, spread, inset); g.fill()
    g.restore()
    // floor pool
    g.save(); g.translate((x1 + x2) / 2, MAP_FLOOR); g.scale(1, 0.16)
    mapGlow(g, 0, 0, (x2 - x1) / 2 + 40, MAP_LAMP_RGB, 0.8); g.restore()
    mapGlow(g, (x1 + x2) / 2, y - 24, 120, '200,230,255', 0.12)
    // lit grid (same 16/80 px lattice as the background), clipped to the cone
    g.save(); mapConePath(g, x1, x2, top, spread, inset); g.clip()
    g.globalCompositeOperation = 'lighter'; g.lineWidth = 1
    const grids = [[16, 'rgba(130,210,255,0.22)'], [80, 'rgba(160,225,255,0.5)']]
    for (const [step, col] of grids)
    {
        g.strokeStyle = col; g.beginPath()
        for (let x = 40.5; x <= GAME_W - 30; x += step) { g.moveTo(x, top); g.lineTo(x, MAP_FLOOR) }
        for (let yy = 30.5; yy <= GAME_H - 30; yy += step) if (yy >= top) { g.moveTo(40, yy); g.lineTo(GAME_W - 30, yy) }
        g.stroke()
    }
    g.restore()
}

// Render the whole map into g (logical units). Returns the dumped state.
function mapRender(g)
{
    const M = ROUTEMAP, assign = routeAssign(levels), { st, next } = mapLevelStates()
    const stats = { next: next + 1, hops: 0, coralHops: 0, lamps: 0, flags: { solved: 0, open: 0, next: 0 },
        platforms: 0, obstacles: 0, portals: 0, ball: null, slots: {} }
    // background, dimmed a little so the lamp and flags carry the light
    if (bgCanvas) { g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(bgCanvas, 0, 0); g.restore() }
    g.save(); g.fillStyle = 'rgba(2,8,18,0.32)'; g.fillRect(0, 0, GAME_W, GAME_H); g.restore()
    const nextSlot = Object.keys(assign).find(id => assign[id] === next)
    if (nextSlot)
    {
        const [cx, top, w] = M.slots[nextSlot]
        mapLamp(g, cx - w / 2, cx + w / 2, top); stats.lamps++
    }
    // central wall + its portal pair
    mapBlock(g, M.wall.x, M.wall.y, M.wall.w, M.wall.h, 9)
    // floor line
    mapTube(g, 40, MAP_FLOOR, GAME_W - 30, 1)
    for (const o of M.obstacles) { mapObstacle(g, o); stats.obstacles++ }
    for (let i = 0; i < M.portals.length; i++) { mapPortal(g, M.portals[i], PORTAL_STYLE[i % 2]); stats.portals++ }
    // hops between used slots
    for (const [a, b, via] of M.hops)
    {
        if (assign[a] === undefined || assign[b] === undefined) continue
        const coral = st[assign[a]] === 'solved' && st[assign[b]] === 'solved'
        mapHop(g, M.slots[a], M.slots[b], via, coral)
        stats.hops++; if (coral) stats.coralHops++
    }
    // platforms, then flags on top
    for (const id in assign)
    {
        const [cx, top, w, s] = M.slots[id]
        mapTube(g, cx - w / 2, top, cx + w / 2, s / 0.62); stats.platforms++
    }
    for (const id in assign)
    {
        const [cx, top, w, s] = M.slots[id], i = assign[id]
        mapFlag(g, cx + 12 * s / 0.62, top, s, i + 1, st[i])
        stats.flags[st[i]]++
        stats.slots[id] = { n: i + 1, srcId: levels[i].srcId, state: st[i] }
    }
    // the ball resting on the next level (the game's Ball drawing)
    if (nextSlot)
    {
        const [cx, top, w, s] = M.slots[nextSlot], r = 9, bx = cx - w / 2 + 12, by = top - r - 1
        mapGlow(g, bx, by, 70, '230,245,255', 0.35)
        g.save(); g.fillStyle = 'rgba(0,0,0,0.45)'; g.beginPath(); g.ellipse(bx, top + 2, 13, 4, 0, 0, Math.PI * 2); g.fill()
        const rg = g.createRadialGradient(bx - 3, by - 4, 1, bx, by, r)
        rg.addColorStop(0, 'rgba(255,255,255,0.95)'); rg.addColorStop(1, 'rgba(191,227,255,0.55)')
        g.fillStyle = rg; g.shadowColor = THEME.ink; g.shadowBlur = 18
        g.beginPath(); g.arc(bx, by, r, 0, Math.PI * 2); g.fill(); g.restore()
        const b = new Ball(r, bx, by, 0, 0, THEME.ink, 'mapball'), saved = ctx
        ctx = g
        try { b.draw() } finally { ctx = saved }
        stats.ball = { slot: nextSlot, x: bx, y: by }
    }
    return stats
}

// Draw the map for this frame (rebuilding the cached layer when the progress or backing size changed)
function mapDraw()
{
    const key = canvas.width + 'x' + canvas.height + ':' + levels.map(l => l.unlock == 2 ? 1 : 0).join('')
    if (!mapCanvas || key !== mapKey)
    {
        if (!mapCanvas) mapCanvas = document.createElement('canvas')
        mapCanvas.width = canvas.width; mapCanvas.height = canvas.height
        const g = mapCanvas.getContext('2d'), k = canvas.width / GAME_W
        g.setTransform(k, 0, 0, k, 0, 0)
        const stats = mapRender(g)
        stats.builds = ((window.mapState && window.mapState.builds) || 0) + 1
        window.mapState = stats
        mapKey = key
    }
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(mapCanvas, 0, 0); ctx.restore()
    menuIcon()
}

// Debug hook for screenshots: map on, with exactly the given srcIds solved (in memory only, nothing saved)
window.mapDebug = function(solvedSrcIds)
{
    const set = new Set(solvedSrcIds || [])
    for (const l of levels) l.unlock = set.has(l.srcId) ? 2 : 1
    drawMap = true
    physics = false
    drawMenu = false
    drawMenuIcon = true
    levelCompletedWindow = false
    return mapLevelStates().next + 1
}

// TASK-181: the pause menu's 'Levels' button opens the map (the HUD menu icon on it leads back)
function mapOpen()
{
    drawMap = true
    drawMenu = false
    levelCompletedWindow = false
    drawMenuIcon = true
    physics = false
}

// A click or tap at logical coords while the map is shown: the menu icon goes back to the pause menu, a level's
// platform / flag hit box (routeSlotBox) starts that level through levelPick (js/levelsRects.js).
function mapClick(coords)
{
    if (inMenuIcon(coords))
    {
        drawMap = false
        drawMenu = true
        drawMenuIcon = false
        return
    }
    const i = routeLevelAt(levels, coords[0], coords[1])
    if (i >= 0)
        levelPick(i)
}
