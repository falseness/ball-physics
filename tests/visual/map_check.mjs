// TASK-179: route map validator (node, no browser).
//
// Usage: node tests/visual/map_check.mjs [--routemap PATH] [--root DIR] [--boxes]
//   --routemap PATH  validate another copy of js/routemap.js (negative tests)
//   --root DIR       tree to load js/levels.js and index.html from (default: this repo)
//   --boxes          also print every slot / flag / obstacle box (for tests/visual/map_slots.py)
// Loads js/levels.js the way the game does (a plain script in one global scope; Line and
// localStorage are stubbed) and js/routemap.js, then prints one compact JSON line and exits 1 when
// any rule fails:
//   a level has no slot; two slots closer than MIN_DIST; an obstacle (or the central wall / a portal)
//   intersects a platform box or a flag box (50x70 above the platform centre); a hop references a
//   missing slot or level, or a consecutive pair of used slots has no hop; a slot or obstacle lies
//   outside x 30..1250, y 30..772; a slot overlaps the menu-icon rect; fewer than 4 spare main slots.
import fs from 'fs'
import path from 'path'
import vm from 'vm'
import { fileURLToPath } from 'url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2)
const opt = name => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null }
const ROOT = path.resolve(opt('--root') || path.join(HERE, '..', '..'))
const MAP_PATH = path.resolve(opt('--routemap') || path.join(ROOT, 'js', 'routemap.js'))
const MIN_DIST = 70, MIN_SPARE = 4, BOUNDS = { x1: 30, y1: 30, x2: 1250, y2: 772 }

// --- load the game's globals ---------------------------------------------------------------------
const ctx = {
    console, Math, JSON,
    GAME_W: 1280, GAME_H: 800, dotRadius: 5, levelLineColor: '#000',
    Line: class { constructor(x1, y1, x2, y2, r, color, type) { Object.assign(this, { posX: x1, posY: y1, posX2: x2, posY2: y2, radius: r, color, type }) } },
    localStorage: { getItem() { return null }, setItem() {} }
}
vm.createContext(ctx)
const themeSrc = fs.readFileSync(path.join(ROOT, 'js', 'theme.js'), 'utf8')
const gw = /const\s+GAME_W\s*=\s*(\d+)\s*,\s*GAME_H\s*=\s*(\d+)/.exec(themeSrc)
if (gw) { ctx.GAME_W = +gw[1]; ctx.GAME_H = +gw[2] }
// levels.js and routemap.js share one script scope, as in index.html
vm.runInContext(fs.readFileSync(path.join(ROOT, 'js', 'levels.js'), 'utf8') + '\n;\n' +
    fs.readFileSync(MAP_PATH, 'utf8') +
    '\n;this.__out = { levels, map: ROUTEMAP, assign: routeAssign(levels, ROUTEMAP), branchOf: i => routeBranch(levels, i) }', ctx)
const { levels, map, assign } = ctx.__out

// menu icon rect from index.html: menuIconRect = [[GAME_W - a - b, y], [w, h]]
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')
const mm = /menuIconRect\s*=\s*\[\s*\[\s*GAME_W\s*-\s*(\d+)\s*-\s*(\d+)\s*,\s*(\d+)\s*\]\s*,\s*\[\s*(\d+)\s*,\s*(\d+)\s*\]/.exec(html)
if (!mm) { console.log(JSON.stringify({ pass: false, problems: ['menuIconRect not found in index.html'] })); process.exit(2) }
const menu = { x1: ctx.GAME_W - +mm[1] - +mm[2], y1: +mm[3] }
menu.x2 = menu.x1 + +mm[4]; menu.y2 = menu.y1 + +mm[5]

// --- boxes -----------------------------------------------------------------------------------------
const r1 = v => Math.round(v * 10) / 10
const rect = (x1, y1, x2, y2) => ({ x1: r1(Math.min(x1, x2)), y1: r1(Math.min(y1, y2)), x2: r1(Math.max(x1, x2)), y2: r1(Math.max(y1, y2)) })
const hit = (a, b) => a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2
const inside = a => a.x1 >= BOUNDS.x1 && a.x2 <= BOUNDS.x2 && a.y1 >= BOUNDS.y1 && a.y2 <= BOUNDS.y2
const B = map.box
function slotBoxes(id)
{
    const [cx, top, w] = map.slots[id]
    return { platform: rect(cx - w / 2, top, cx + w / 2, top + B.platformDepth), flag: rect(cx - B.flagW / 2, top - B.flagH, cx + B.flagW / 2, top) }
}
function obstacleBox(o)
{
    switch (o.kind)
    {
    case 'bumper': return rect(o.x - o.r, o.y - o.r, o.x + o.r, o.y + o.r)
    case 'spring': return rect(o.x - o.w, o.y - o.h, o.x + o.w, o.y)
    case 'block': return rect(o.x, o.y, o.x + o.w, o.y + o.h)
    default:
        if ([o.x1, o.y1, o.x2, o.y2, o.w].some(v => typeof v !== 'number')) return null
        return rect(Math.min(o.x1, o.x2) - o.w / 2, Math.min(o.y1, o.y2) - o.w / 2, Math.max(o.x1, o.x2) + o.w / 2, Math.max(o.y1, o.y2) + o.w / 2)
    }
}
// the central wall and the portal openings are solid too
const solids = map.obstacles.map(o => ({ id: o.id, kind: o.kind, box: obstacleBox(o) }))
solids.push({ id: 'wall', kind: 'wall', box: rect(map.wall.x, map.wall.y, map.wall.x + map.wall.w, map.wall.y + map.wall.h) })
for (const p of map.portals)
{
    const tx = -p.ny, ty = p.nx
    solids.push({ id: 'portal_' + p.name, kind: 'portal', box: obstacleBox({ x1: p.x - tx * p.h, y1: p.y - ty * p.h, x2: p.x + tx * p.h, y2: p.y + ty * p.h, w: 5 }) })
}

// --- checks ------------------------------------------------------------------------------------------
const problems = []
const slotIds = Object.keys(map.slots)
const levelOfSlot = {}
for (const id in assign) levelOfSlot[id] = assign[id]
const usedSlots = Object.keys(levelOfSlot)

// 1. every level has a slot (slots of a branch must exist in the table)
for (const b in map.branches) for (const id of map.branches[b]) if (!map.slots[id]) problems.push('branch ' + b + ' names missing slot ' + id)
const placed = new Set(Object.values(levelOfSlot))
const noSlot = []
for (let i = 0; i < levels.length; ++i) if (!placed.has(i) || !map.slots[Object.keys(levelOfSlot).find(k => levelOfSlot[k] === i)]) noSlot.push(levels[i].srcId)
for (const s of noSlot) problems.push('level srcId ' + s + ' has no slot')
const branchCount = { start: 0, main: 0, extra: 0 }
for (let i = 0; i < levels.length; ++i) branchCount[ctx.__out.branchOf(i)]++
const spareSlots = map.branches.main.length - branchCount.main
if (spareSlots < MIN_SPARE) problems.push('only ' + spareSlots + ' spare main-branch slots (need ' + MIN_SPARE + ')')

// 2. slot spacing (all slots, so the spares are already clear of the used ones)
let minSlotDistance = Infinity, minUsedSlotDistance = Infinity, closest = null
const tooClose = []
for (let i = 0; i < slotIds.length; ++i) for (let j = i + 1; j < slotIds.length; ++j)
{
    const a = map.slots[slotIds[i]], b = map.slots[slotIds[j]], d = Math.hypot(a[0] - b[0], a[1] - b[1])
    if (d < minSlotDistance) { minSlotDistance = d; closest = [slotIds[i], slotIds[j]] }
    if (slotIds[i] in levelOfSlot && slotIds[j] in levelOfSlot) minUsedSlotDistance = Math.min(minUsedSlotDistance, d)
    if (d < MIN_DIST) { tooClose.push([slotIds[i], slotIds[j], r1(d)]); problems.push('slots ' + slotIds[i] + ' and ' + slotIds[j] + ' are ' + r1(d) + ' px apart (< ' + MIN_DIST + ')') }
}

// 3. obstacle / wall / portal vs platform and flag boxes
const overlaps = []
for (const s of solids)
{
    if (!s.box) { problems.push('obstacle ' + s.id + ' has no geometry'); continue }
    for (const id of slotIds)
    {
        const sb = slotBoxes(id)
        for (const part of ['platform', 'flag']) if (hit(s.box, sb[part]))
        {
            overlaps.push([s.id, id, part])
            problems.push(s.kind + ' ' + s.id + ' intersects the ' + part + ' box of slot ' + id + (id in levelOfSlot ? ' (srcId ' + levels[levelOfSlot[id]].srcId + ')' : ' (spare)'))
        }
    }
}
for (const o of map.obstacles) if (o.kind === 'gate' && !map.obstacles.some(c => c.id === o.ceiling && c.kind === 'ceiling')) problems.push('gate ' + o.id + ' has no ceiling beam ' + o.ceiling)

// 4. hops
const hopMissing = []
const hopKey = new Set()
for (const h of map.hops)
{
    const [a, b, via] = h
    hopKey.add(a + '>' + b)
    for (const id of [a, b])
    {
        if (!map.slots[id]) { hopMissing.push([a, b, id]); problems.push('hop ' + a + '->' + b + ' references missing slot ' + id) }
        else if (id in levelOfSlot && !levels[levelOfSlot[id]]) { hopMissing.push([a, b, id]); problems.push('hop ' + a + '->' + b + ' references missing level at ' + id) }
    }
    if (via !== undefined && !(Array.isArray(via) && via.every(v => v === 'gap' || (Array.isArray(v) && v.length === 2 && v.every(Number.isFinite)))))
        problems.push('hop ' + a + '->' + b + ' has a bad via list')
}
const needHop = []
for (const b in map.branches)
{
    const used = map.branches[b].filter(id => id in levelOfSlot)
    for (let i = 0; i + 1 < used.length; ++i) needHop.push([used[i], used[i + 1]])
}
const s2 = map.branches.start[1]
for (const b of ['main', 'extra']) { const f = map.branches[b].find(id => id in levelOfSlot); if (s2 in levelOfSlot && f) needHop.push([s2, f]) }
const hopUncovered = needHop.filter(([a, b]) => !hopKey.has(a + '>' + b))
for (const [a, b] of hopUncovered) problems.push('no hop ' + a + '->' + b)
const gapHops = map.hops.filter(h => Array.isArray(h[2]) && h[2].includes('gap')).map(h => h[0] + '>' + h[1])
if (gapHops.length !== 1) problems.push('expected exactly 1 portal gap hop, found ' + gapHops.length)

// 5. offscreen, 6. menu icon
const offscreen = [], menuOverlaps = []
for (const id of slotIds)
{
    const sb = slotBoxes(id)
    for (const part of ['platform', 'flag'])
    {
        if (!inside(sb[part])) { offscreen.push([id, part]); problems.push('slot ' + id + ' ' + part + ' box ' + JSON.stringify(sb[part]) + ' is outside x 30..1250, y 30..772') }
        if (hit(sb[part], menu)) { menuOverlaps.push([id, part]); problems.push('slot ' + id + ' ' + part + ' box overlaps the menu icon') }
    }
}
for (const s of solids) if (s.box && !inside(s.box)) { offscreen.push([s.id]); problems.push(s.kind + ' ' + s.id + ' is outside x 30..1250, y 30..772') }

const out = {
    pass: problems.length === 0,
    routemap: path.relative(process.cwd(), MAP_PATH),
    levelCount: levels.length,
    branchLevels: branchCount,
    slotsTotal: slotIds.length,
    slotsUsed: usedSlots.length,
    spareSlots,
    minSlotDistance: r1(minSlotDistance), closestSlots: closest,
    minUsedSlotDistance: r1(minUsedSlotDistance),
    tooClose: tooClose.length,
    obstacles: map.obstacles.length, solidsChecked: solids.length,
    obstacleOverlaps: overlaps.length,
    hops: map.hops.length, hopMissing: hopMissing.length, hopUncovered: hopUncovered.length, gapHops,
    offscreen: offscreen.length,
    menuIconRect: menu, menuOverlaps: menuOverlaps.length,
    noSlot: noSlot.length,
    assignment: Object.fromEntries(usedSlots.map(id => [id, levels[levelOfSlot[id]].srcId])),
    problems
}
if (args.includes('--boxes'))
{
    out.boxes = {
        slots: slotIds.map(id => Object.assign({ id, srcId: id in levelOfSlot ? levels[levelOfSlot[id]].srcId : null }, slotBoxes(id))),
        solids: solids.map(s => ({ id: s.id, kind: s.kind, box: s.box })),
        hops: map.hops.map(h => ({ from: h[0], to: h[1], via: h[2] || [] })),
        slotXY: map.slots, obstacles: map.obstacles, portals: map.portals, menu
    }
}
console.log(JSON.stringify(out))
process.exit(out.pass ? 0 : 1)
