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
    // TASK-182: live layer on top of the cached map: subtle hover / selection highlight, then the preview card
    if (mapHover >= 0) mapHighlight(ctx, mapHover, 0.13)
    if (mapSel >= 0 && mapSel !== mapHover) mapHighlight(ctx, mapSel, 0.1)
    const ci = mapCardLevel()
    window.mapCard = ci >= 0 ? mapCardLayout(ci) : null
    if (window.mapCard) mapCardDraw(ctx, window.mapCard)
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

// TASK-181/182: the pause menu's 'Levels' button opens the map (the HUD menu icon on it leads back)
function mapOpen()
{
    drawMap = true
    drawMenu = false
    levelCompletedWindow = false
    drawMenuIcon = true
    physics = false
    mapSel = mapHover = -1
    mapCursor('')
}

// ---- TASK-182: preview card (concept 305: glass panel, number, line glyphs, portal badge, thumbnail, play) ----
// mapHover = level under the mouse (mousemove), mapSel = level selected by a click / tap. The card shows the
// hovered level, else the selected one. A click on the card's play button, or a second click / tap on the selected
// level, starts it; a first click / tap only selects.
let mapHover = -1, mapSel = -1
window.mapCard = null
const MAP_CARD = { thumbW: 192, pad: 12, head: 44, gap: 8, play: 40, ptr: 16, gapFlag: 18, margin: 6 }
MAP_CARD.thumbH = MAP_CARD.thumbW * GAME_H / GAME_W
MAP_CARD.w = MAP_CARD.thumbW + MAP_CARD.pad * 2
MAP_CARD.h = MAP_CARD.pad * 2 + MAP_CARD.head + MAP_CARD.thumbH + MAP_CARD.gap + MAP_CARD.play

function mapCardLevel()
{
    return mapHover >= 0 ? mapHover : mapSel
}

function mapCursor(c)
{
    if (canvas.style.cursor !== c) canvas.style.cursor = c
}

const mapRectHit = (r, x, y) => r[0] <= x && x <= r[2] && r[1] <= y && y <= r[3]
const mapRectsOverlap = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]

function mapMenuIconBox()
{
    return [menuIconRect[0][0], menuIconRect[0][1], menuIconRect[0][0] + menuIconRect[1][0], menuIconRect[0][1] + menuIconRect[1][1]]
}

// Card layout for play-order level i, placed by rule: the card sits above / right / left / below the level's flag
// rect (routeFlagRect) at several offsets along that side (if none fits: further away with a longer pointer, lift
// 40 / 80 / 120 px), and the first spot that is fully on screen and covers
// neither the menu icon, the selected flag nor the next level's flag wins. The pointer triangle sits on the side
// facing the flag, at the flag's pole (above / below) or the pennant height (left / right), its tip 2 px off the
// flag rect. Returns null for a level without a slot.
function mapCardLayout(i)
{
    const id = routeSlotOf(levels, i)
    if (id === null) return null
    const C = MAP_CARD, W = C.w, H = C.h, F = routeFlagRect(id), [cx, top, , s] = ROUTEMAP.slots[id]
    const nid = i + 1 < levels.length ? routeSlotOf(levels, i + 1) : null, NF = nid === null ? null : routeFlagRect(nid)
    const ax = cx + 12 * s / 0.62, ay = top - 30 * s / 0.62, icon = mapMenuIconBox()
    const avoid = [icon, F].concat(NF ? [NF] : [])
    const T = [0.5, 0.3, 0.7, 0.15, 0.85, 0.09, 0.91]
    let best = null
    for (const lift of [0, 40, 80, 120])
    for (const side of ['above', 'right', 'left', 'below'])
        for (const t of T)
        {
            const off = C.gapFlag + lift
            let x0, y0, tip, base
            if (side === 'above' || side === 'below')
            {
                x0 = Math.round(ax - t * W)
                y0 = side === 'above' ? F[1] - off - H : F[3] + off
                const ey = side === 'above' ? y0 + H : y0
                tip = [ax, side === 'above' ? F[1] - 2 : F[3] + 2]; base = [[ax - 12, ey], [ax + 12, ey]]
            }
            else
            {
                y0 = Math.round(ay - t * H)
                x0 = side === 'right' ? F[2] + off : F[0] - off - W
                const ex = side === 'right' ? x0 : x0 + W
                tip = [side === 'right' ? F[2] + 2 : F[0] - 2, ay]; base = [[ex, ay - 12], [ex, ay + 12]]
            }
            const body = [x0, y0, x0 + W, y0 + H]
            const ptr = [Math.min(tip[0], base[0][0], base[1][0]), Math.min(tip[1], base[0][1], base[1][1]),
                Math.max(tip[0], base[0][0], base[1][0]), Math.max(tip[1], base[0][1], base[1][1])]
            const all = [Math.min(body[0], ptr[0]), Math.min(body[1], ptr[1]), Math.max(body[2], ptr[2]), Math.max(body[3], ptr[3])]
            const onscreen = all[0] >= C.margin && all[1] >= C.margin && all[2] <= GAME_W - C.margin && all[3] <= GAME_H - C.margin
            let overlaps = 0
            for (const r of avoid) overlaps += (mapRectsOverlap(body, r) ? 1 : 0) + (mapRectsOverlap(ptr, r) ? 1 : 0)
            const bad = (onscreen ? 0 : 1) + overlaps
            if (!best || bad < best.bad)
                best = { i, n: i + 1, srcId: levels[i].srcId, slot: id, side, t, lift, x: x0, y: y0, w: W, h: H, body, ptr, all, tip,
                    base, flag: F, nextSlot: nid, nextFlag: NF, menuIcon: icon, overlaps, onscreen, bad,
                    play: [x0 + W / 2, y0 + C.pad + C.head + C.thumbH + C.gap + C.play / 2, C.play] }
            if (bad === 0) return best
        }
    return best
}

// play button hit rect of a card layout
function mapCardPlayBox(c)
{
    const [x, y, sz] = c.play, h = sz / 2 + 4
    return [x - h, y - h, x + h, y + h]
}

// the HUD's "one line" glyph, scaled
function mapLineGlyph(g, x, y, k)
{
    g.save(); g.strokeStyle = THEME.coral; g.lineWidth = 2.5; g.shadowColor = THEME.coral; g.shadowBlur = 6
    g.beginPath(); g.moveTo(x - 14 * k, y + 6 * k); g.lineTo(x + 14 * k, y - 6 * k); g.stroke()
    for (const [px, py] of [[x - 14 * k, y + 6 * k], [x + 14 * k, y - 6 * k]]) { g.beginPath(); g.arc(px, py, 3.5 * k, 0, Math.PI * 2); g.stroke() }
    g.restore()
}

// two linked rings in the portal colours
function mapPortalBadge(g, x, y, s)
{
    g.save(); g.lineWidth = 2
    for (let j = 0; j < 2; j++)
    {
        g.strokeStyle = PORTAL_STYLE[j].color; g.shadowColor = PORTAL_STYLE[j].glow; g.shadowBlur = 6
        g.beginPath(); g.ellipse(x + (j ? 1 : -1) * s * .35, y, s * .3, s * .55, 0, 0, Math.PI * 2); g.stroke()
    }
    g.restore()
}

// Miniature of level L drawn from its own data: lines, resolved portals, flag (rotated flagCoords), ball start.
function mapThumb(g, L, x0, y0, w)
{
    const h = w * GAME_H / GAME_W, k = w / GAME_W
    g.save(); g.fillStyle = '#071a30'; g.fillRect(x0, y0, w, h)
    g.strokeStyle = 'rgba(92,200,255,0.12)'; g.lineWidth = 1; g.beginPath()
    for (let gx = 0; gx <= GAME_W; gx += 100) { g.moveTo(x0 + gx * k, y0); g.lineTo(x0 + gx * k, y0 + h) }
    for (let gy = 0; gy <= GAME_H; gy += 100) { g.moveTo(x0, y0 + gy * k); g.lineTo(x0 + w, y0 + gy * k) }
    g.stroke()
    g.beginPath(); g.rect(x0, y0, w, h); g.clip()
    g.strokeStyle = THEME.ink; g.lineWidth = Math.max(1.5, 7 * k); g.lineCap = 'round'; g.shadowColor = THEME.ink; g.shadowBlur = 3
    g.beginPath()
    for (const l of L.lines) { g.moveTo(x0 + l.posX * k, y0 + l.posY * k); g.lineTo(x0 + l.posX2 * k, y0 + l.posY2 * k) }
    g.stroke()
    for (const q of portalResolveAll(L.portals, L.lines))
    {
        const st = PORTAL_STYLE[q.name === 'B' ? 1 : 0], tx = -Math.sin(q.angle), ty = Math.cos(q.angle)
        g.strokeStyle = st.color; g.shadowColor = st.glow; g.lineWidth = Math.max(3, 14 * k)
        g.beginPath(); g.moveTo(x0 + (q.x - tx * q.h) * k, y0 + (q.y - ty * q.h) * k)
        g.lineTo(x0 + (q.x + tx * q.h) * k, y0 + (q.y + ty * q.h) * k); g.stroke()
    }
    // flag: the game's flagCoords polygon rotated by flagRotate (levelChoosed), scaled with a readable minimum
    const fk = Math.max(k, 0.16), F = flagCoords.map(p => pointRotation(p[0], p[1], L.flagRotate))
    const fx = x0 + L.flagX * k, fy = y0 + L.flagY * k, P = F.map(p => [fx + p[0] * fk, fy + p[1] * fk])
    g.strokeStyle = THEME.ink; g.lineWidth = 1.5; g.shadowColor = THEME.coral; g.shadowBlur = 4
    g.beginPath(); g.moveTo(...P[0]); g.lineTo(...P[1]); g.stroke()
    g.fillStyle = THEME.coral; g.beginPath(); g.moveTo(...P[2]); g.lineTo(...P[3]); g.lineTo(...P[4]); g.closePath(); g.fill()
    g.fillStyle = THEME.ink; g.shadowColor = THEME.ink
    g.beginPath(); g.arc(x0 + L.ballX * k, y0 + L.ballY * k, Math.max(3, 12 * k), 0, Math.PI * 2); g.fill()
    g.restore()
    return { lines: L.lines.length, portals: (L.portals || []).length, flag: [L.flagX, L.flagY], ball: [L.ballX, L.ballY] }
}

// the in-game start triangle in its square
function mapPlayButton(g, x, y, s, hot)
{
    g.save(); g.strokeStyle = THEME.cyan; g.lineWidth = 2; g.shadowColor = THEME.cyan; g.shadowBlur = hot ? 16 : 10
    g.fillStyle = hot ? 'rgba(24,66,110,0.95)' : 'rgba(15,49,86,0.9)'
    g.fillRect(x - s / 2, y - s / 2, s, s); g.strokeRect(x - s / 2, y - s / 2, s, s)
    g.fillStyle = THEME.coral; g.shadowColor = THEME.coral
    g.beginPath(); g.moveTo(x - s * .22, y - s * .3); g.lineTo(x + s * .32, y); g.lineTo(x - s * .22, y + s * .3); g.closePath(); g.fill()
    g.restore()
}

function mapCardDraw(g, c)
{
    const C = MAP_CARD, L = levels[c.i], x0 = c.x, y0 = c.y, W = c.w, H = c.h
    g.save()
    g.fillStyle = 'rgba(2,8,18,0.45)'; mapRoundRect(g, x0 + 5, y0 + 7, W, H, 10); g.fill()
    // glass panel + pointer (same fill / stroke)
    const panel = () => mapRoundRect(g, x0, y0, W, H, 10)
    g.fillStyle = 'rgba(11,39,71,0.88)'; g.strokeStyle = THEME.cyan; g.lineWidth = 2; g.shadowColor = THEME.cyan; g.shadowBlur = 12
    panel(); g.fill(); g.stroke(); g.shadowBlur = 0
    const sheen = g.createLinearGradient(0, y0, 0, y0 + H * 0.5)
    sheen.addColorStop(0, 'rgba(255,255,255,0.10)'); sheen.addColorStop(1, 'rgba(255,255,255,0)')
    g.fillStyle = sheen; panel(); g.fill()
    g.fillStyle = 'rgba(11,39,71,0.96)'
    g.beginPath(); g.moveTo(...c.base[0]); g.lineTo(...c.tip); g.lineTo(...c.base[1]); g.closePath(); g.fill()
    g.beginPath(); g.moveTo(...c.base[0]); g.lineTo(...c.tip); g.lineTo(...c.base[1]); g.stroke()
    g.restore()
    // header: number, one glyph per allowed line, portal badge
    const hy = y0 + C.pad + C.head / 2 - 2
    g.save(); g.font = '40px ' + THEME.fontStack; g.fillStyle = THEME.ink; g.textBaseline = 'middle'
    g.fillText(String(c.n), x0 + C.pad, hy + 2); g.restore()
    for (let k = 0; k < L.lineK; k++) mapLineGlyph(g, x0 + C.pad + 60 + k * 26, hy, 0.8)
    if (L.portals && L.portals.length) mapPortalBadge(g, x0 + W - C.pad - 12, hy, 18)
    const th = mapThumb(g, L, x0 + C.pad, y0 + C.pad + C.head, C.thumbW)
    mapPlayButton(g, c.play[0], c.play[1], c.play[2], mapPlayHot)
    // what this frame's card showed (tests read it)
    window.mapCardInfo = { i: c.i, n: c.n, srcId: c.srcId, glyphs: L.lineK, badge: !!(L.portals && L.portals.length), thumb: th }
}

let mapPlayHot = false

function mapRoundRect(g, x, y, w, h, r)
{
    g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r)
    g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath()
}

// soft glow on a hovered / selected level's flag
function mapHighlight(g, i, a)
{
    const id = routeSlotOf(levels, i)
    if (id === null) return
    const [cx, top, w, s] = ROUTEMAP.slots[id], px = cx + 12 * s / 0.62
    mapGlow(g, px + 6, top - 26, 58, '233,246,255', a)
    g.save(); g.strokeStyle = 'rgba(233,246,255,' + (a * 2.5) + ')'; g.lineWidth = 1.5
    g.beginPath(); g.ellipse(cx, top + 3, w / 2 + 6, 7, 0, 0, Math.PI * 2); g.stroke(); g.restore()
}

// mouse move on the map: hover highlight + card, pointer cursor over a level or the play button. Over the shown card
// the hover is kept (the card stays while the mouse travels to its play button).
function mapMove(coords)
{
    const [x, y] = coords, c = window.mapCard
    if (c && mapRectHit(c.all, x, y))
    {
        mapPlayHot = mapRectHit(mapCardPlayBox(c), x, y)
        mapCursor(mapPlayHot ? 'pointer' : '')
        return
    }
    mapPlayHot = false
    mapHover = routeLevelAt(levels, x, y)
    mapCursor(mapHover >= 0 || inMenuIcon(coords) ? 'pointer' : '')
}

function mapStart(i)
{
    mapSel = mapHover = -1
    mapPlayHot = false
    mapCursor('')
    levelPick(i)
}

// A click or tap at logical coords while the map is shown: the menu icon goes back to the pause menu; the shown
// card's play button starts its level (elsewhere on the card does nothing); a level's slot hit box (routeSlotBox)
// selects it, or starts it when it is already selected; empty space clears the selection.
function mapClick(coords)
{
    if (inMenuIcon(coords))
    {
        drawMap = false
        drawMenu = true
        drawMenuIcon = false
        mapSel = mapHover = -1
        mapCursor('')
        return
    }
    const ci = mapCardLevel(), c = ci >= 0 ? mapCardLayout(ci) : null
    if (c && mapRectHit(mapCardPlayBox(c), coords[0], coords[1]))
        return mapStart(c.i)
    if (c && mapRectHit(c.all, coords[0], coords[1]))
        return
    const i = routeLevelAt(levels, coords[0], coords[1])
    if (i >= 0 && i === mapSel)
        return mapStart(i)
    mapSel = i
}

// Test hook: the card layout of every level (or the given ones) with its overlap / on-screen checks
window.mapCardCheck = function(list)
{
    const ids = list || levels.map((l, i) => i)
    return ids.map(i => mapCardLayout(i)).filter(c => c)
}
