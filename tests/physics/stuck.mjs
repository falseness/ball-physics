// "Not stuck in textures" suite (TASK-267). Runs the real js/ball.js (tests/physics/harness.mjs fast loader, 500
// steps per frame, every step checked) on named deterministic scenes plus seeded random fuzz scenes, no portals.
// Checks (counts per scene):
//   a depth:      after every step the centre is at least R - 0.5 px from every segment; a deeper overlap is allowed
//                 for one state only (it must be gone after the next step): a = steps whose end state AND the state
//                 before the step (the previous step's end, or the spawn) are both deeper than 0.5 px.
//                 (transientDeep, info only: steps that end deeper than 0.5 px but are fixed by the next step)
//   b tunnelling: the centre crosses a segment's interior between two steps: the start and end centre are strictly on
//                 opposite sides of the segment's line and the crossing point lies inside the segment (more than
//                 1e-6 px from both end points; passing around an end point is allowed). b = such steps.
//   c livelock:   harness livelockWindows (a 1 s window, stride 0.5 s, in which every step's centre stays inside a
//                 2 px box while the mean speed is >= 0.002 px/step). c = such windows.
//   d freeze:     the ball keeps the same position (every step of a frame within a 0.01 px box, and the frame end
//                 within 0.01 px of the streak's first frame end) for 60+ consecutive frames while overlapping a
//                 segment (frame-end distance < R - 0.05 px; a resting ball sits at R). d = such streaks.
// Deterministic scenes (except the single thin line ones and the srcId-10 pocket) are enclosed in a box. A scene ends early when the ball leaves the map (the game restarts the level there).
//
//   node tests/physics/stuck.mjs [--out FILE] [--fuzz A-B] [--scenes N] [--frames F] [--only name,name] [--no-fuzz]
//       deterministic scenes + fuzz seeds A..B (default 1-3), N scenes each (default 200), F frames each (default
//       300) of random 1-4 line scenes (the tests/physics/invariants.mjs / energy.mjs generator); work is split
//       into parallel child processes (--shard internally).
//   node tests/physics/stuck.mjs --selftest [--out FILE]
//       synthetic traces: clean, deep overlap, tunnelling, livelock and freeze; each bad one must fire only its own
//       check, the clean one none.
// Output: compact JSON. Exit 1 when any scene fails a check (or a selftest case fails), 0 otherwise.
// Node 12: no ?? / ?. syntax.
import fs from 'node:fs'
import { spawn, execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import * as h from './harness.mjs'

const SELF = fileURLToPath(import.meta.url)
const { R, STEPS_PER_FRAME, FPS } = h
const DEPTH_TOL = 0.5, END_EPS = 1e-6, FREEZE_BOX = 0.01, FREEZE_OVERLAP = 0.05, FREEZE_FRAMES = 60, MAX_EX = 3
const DET_SHARDS = 3
const CHECKS = ['a', 'b', 'c', 'd']

function arg(name, def)
{
    const i = process.argv.indexOf(name)
    return i < 0 ? def : process.argv[i + 1]
}
const has = (name) => process.argv.includes(name)
const rr = (v) => (typeof v === 'number' && isFinite(v)) ? +v.toPrecision(8) : v

// ---------------- checker ----------------
// step(x0, y0, x1, y1, vx1, vy1) for every step, in order; result() at the end.
export function makeChecker(segs, x, y)
{
    const S = segs.map(s =>
    {
        const dx = s[2] - s[0], dy = s[3] - s[1], L = Math.hypot(dx, dy)
        return { s, dx, dy, L, box: [Math.min(s[0], s[2]) - R - 2, Math.max(s[0], s[2]) + R + 2, Math.min(s[1], s[3]) - R - 2, Math.max(s[1], s[3]) + R + 2] }
    })
    function minDist(px, py)
    {
        let best = Infinity
        for (const q of S)
        {
            const b = q.box
            if (px < b[0] || px > b[1] || py < b[2] || py > b[3]) continue
            const c = h.closestOnSegment(px, py, q.s), d = Math.hypot(px - c[0], py - c[1])
            if (d < best) best = d
        }
        return best
    }
    // index of a segment whose interior the move (x0,y0)->(x1,y1) crosses, or -1
    function crossed(x0, y0, x1, y1)
    {
        const far = Math.abs(x1 - x0) + Math.abs(y1 - y0) > 1
        for (let i = 0; i < S.length; ++i)
        {
            const q = S[i], b = q.box
            if (!far && (x1 < b[0] || x1 > b[1] || y1 < b[2] || y1 > b[3])) continue
            if (q.L === 0) continue
            const s0 = q.dx * (y0 - q.s[1]) - q.dy * (x0 - q.s[0]), s1 = q.dx * (y1 - q.s[1]) - q.dy * (x1 - q.s[0])
            if (!(s0 < 0 && s1 > 0 || s0 > 0 && s1 < 0)) continue
            const t = s0 / (s0 - s1), cx = x0 + t * (x1 - x0), cy = y0 + t * (y1 - y0)
            const along = ((cx - q.s[0]) * q.dx + (cy - q.s[1]) * q.dy) / q.L
            if (along > END_EPS && along < q.L - END_EPS) return i
        }
        return -1
    }
    const ex = { a: [], b: [], c: [], d: [] }
    const cnt = { a: 0, b: 0, c: 0, d: 0 }
    let steps = 0, transientDeep = 0, maxDepth = Math.max(0, R - minDist(x, y))
    let prevDeep = R - minDist(x, y) > DEPTH_TOL
    // per-frame accumulators
    const frames = []
    let fk = 0, fsp = 0, fx0 = Infinity, fx1 = -Infinity, fy0 = Infinity, fy1 = -Infinity
    let streak = 0, anchor = null, streakStart = 0, freezeFrames = 0
    function endFrame(x1, y1)
    {
        frames.push({ x: x1, y: y1, meanSpeed: fsp / fk, minX: fx0, maxX: fx1, minY: fy0, maxY: fy1 })
        const f = frames.length - 1
        const still = Math.max(fx1 - fx0, fy1 - fy0) < FREEZE_BOX
        const over = R - minDist(x1, y1) > FREEZE_OVERLAP
        if (still && over && anchor && Math.hypot(x1 - anchor[0], y1 - anchor[1]) < FREEZE_BOX) ++streak
        else if (still && over) { closeStreak(); streak = 1; anchor = [x1, y1]; streakStart = f }
        else { closeStreak(); streak = 0; anchor = null }
        fk = 0; fsp = 0; fx0 = Infinity; fx1 = -Infinity; fy0 = Infinity; fy1 = -Infinity
    }
    function closeStreak()
    {
        if (streak >= FREEZE_FRAMES)
        {
            ++cnt.d; freezeFrames += streak
            if (ex.d.length < MAX_EX) ex.d.push({ fromFrame: streakStart, frames: streak, pos: anchor.map(rr), depth: rr(R - minDist(anchor[0], anchor[1])) })
        }
    }
    return {
        step(x0, y0, x1, y1, vx1, vy1)
        {
            const depth = R - minDist(x1, y1), deep = depth > DEPTH_TOL
            if (depth > maxDepth) maxDepth = depth
            if (deep && prevDeep)
            {
                ++cnt.a
                if (ex.a.length < MAX_EX) ex.a.push({ step: steps, frame: Math.floor(steps / STEPS_PER_FRAME), depth: rr(depth), pos: [x1, y1].map(rr), v: [vx1, vy1].map(rr) })
            }
            else if (deep) ++transientDeep
            prevDeep = deep
            const ci = crossed(x0, y0, x1, y1)
            if (ci >= 0)
            {
                ++cnt.b
                if (ex.b.length < MAX_EX) ex.b.push({ step: steps, frame: Math.floor(steps / STEPS_PER_FRAME), seg: ci, from: [x0, y0].map(rr), to: [x1, y1].map(rr), v: [vx1, vy1].map(rr) })
            }
            ++steps
            fsp += Math.hypot(vx1, vy1)
            if (x1 < fx0) fx0 = x1
            if (x1 > fx1) fx1 = x1
            if (y1 < fy0) fy0 = y1
            if (y1 > fy1) fy1 = y1
            if (++fk === STEPS_PER_FRAME) endFrame(x1, y1)
        },
        result()
        {
            closeStreak()
            const ll = h.livelockWindows(frames)
            cnt.c = ll.length
            ex.c = ll.slice(0, MAX_EX)
            const examples = {}
            for (const k of CHECKS) if (ex[k].length) examples[k] = ex[k]
            return { steps, frames: frames.length, counts: Object.assign({}, cnt), transientDeep, maxDepth: rr(maxDepth), freezeFrames,
                pass: CHECKS.every(k => cnt[k] === 0), examples }
        },
    }
}

// ---------------- scenes ----------------
const rad = (d) => d * Math.PI / 180
const fix = (a) => a.map(v => +v.toFixed(6))
// The srcId-10 pocket from artifacts/edges_bug.png (tests/physics/edge_cases.mjs shelf_pocket, TASK-197)
const SHELF10 = [[100, 10, 100, 300], [100, 300, 300, 300], [300, 200, 200, 200], [200, 200, 200, 150], [200, 150, 300, 150], [300, 200, 300, 10]]
const BOX = [[20, 0, 20, 780], [20, 780, 1260, 780], [1260, 780, 1260, 0]]
const POCKET_STARTS = [[207, 285, 0, -0.03224], [182.322, 217.678, 0.010607, -0.010607], [150, 195, 0.02, 0]]
function polyline(pts) { const o = []; for (let i = 0; i + 1 < pts.length; ++i) o.push(fix([...pts[i], ...pts[i + 1]])); return o }
// n joined segments on a circular arc of radius rad0 centred at (cx, cy), from angle a0 to a1 (degrees, screen coords)
function arc(cx, cy, rad0, a0, a1, n)
{
    const pts = []
    for (let i = 0; i <= n; ++i) { const a = rad(a0 + (a1 - a0) * i / n); pts.push([cx + rad0 * Math.cos(a), cy + rad0 * Math.sin(a)]) }
    return polyline(pts)
}

export function deterministicScenes()
{
    const S = [], D = 2 * R, F = 600
    const lowFloor = [100, 760, 1180, 760]
    for (const k of [0.9, 1.0, 1.1])
    {
        const w = k * D, tag = k.toFixed(1)
        // a vertical slot: two parallel walls w apart (centre to centre), floor below; dropped centred and 3 px off
        const sl = [[640 - w / 2, 450, 640 - w / 2, 700], [640 + w / 2, 450, 640 + w / 2, 700], lowFloor].map(fix)
        S.push({ name: `slot_${tag}D_centre`, segs: sl, ball: [640, 350, 0, 0], frames: F })
        S.push({ name: `slot_${tag}D_off3`, segs: sl, ball: [643, 350, 0, 0], frames: F })
        // a floor gap: two collinear horizontal lines whose ends are w apart, floor below
        const fg = [[300, 600, 640 - w / 2, 600], [640 + w / 2, 600, 980, 600], lowFloor].map(fix)
        S.push({ name: `floor_gap_${tag}D_centre`, segs: fg, ball: [640, 500, 0, 0], frames: F })
        S.push({ name: `floor_gap_${tag}D_off3`, segs: fg, ball: [643, 500, 0, 0], frames: F })
    }
    // wedges (opening angle), vertex (640, 650), arms 400 px, dropped 2 px right of the axis 300 px above the vertex
    for (const a of [5, 10])
    {
        const hh = rad(a / 2), V = [640, 650]
        const l = [V[0] - 400 * Math.sin(hh), V[1] - 400 * Math.cos(hh)], r = [V[0] + 400 * Math.sin(hh), V[1] - 400 * Math.cos(hh)]
        S.push({ name: `wedge_${a}deg`, segs: [fix([...l, ...V]), fix([...V, ...r])], ball: [642, 350, 0, 0], frames: F })
    }
    // coincident lines: the same line twice (also reversed), and two partly overlapping collinear slopes
    S.push({ name: 'coincident_same', segs: [[300, 600, 900, 600], [300, 600, 900, 600]], ball: [600, 500, 0.005, 0], frames: F })
    S.push({ name: 'coincident_reversed', segs: [[300, 600, 900, 600], [900, 600, 300, 600]], ball: [600, 500, 0.005, 0], frames: F })
    S.push({ name: 'coincident_overlap_slope', segs: [[200, 400, 700, 550], [500, 490, 1000, 640]], ball: [...h.restingOn([200, 400, 700, 550], 0.1), 0, 0], frames: F })
    // crossing lines: an X (dropped into its upper V, and onto the crossing from above-left) and a + crossing
    S.push({ name: 'crossing_x_upper_v', segs: [[400, 300, 800, 600], [400, 600, 800, 300]], ball: [610, 300, 0, 0], frames: F })
    S.push({ name: 'crossing_x_side', segs: [[400, 300, 800, 600], [400, 600, 800, 300]], ball: [450, 250, 0.01, 0], frames: F })
    S.push({ name: 'crossing_plus', segs: [[400, 500, 800, 500], [600, 300, 600, 700]], ball: [620, 350, 0, 0], frames: F })
    // a ball at 20 px/frame (0.04 px/step) into a single thin line: down, up, oblique, horizontal into a vertical line,
    // and down onto the line 3 px inside its end point
    const vf = 20 / STEPS_PER_FRAME, thin = [400, 500, 900, 500]
    S.push({ name: 'fast_thin_down', segs: [thin], ball: [600, 300, 0, vf], frames: F })
    S.push({ name: 'fast_thin_up', segs: [thin], ball: [600, 700, 0, -vf], frames: F })
    S.push({ name: 'fast_thin_oblique', segs: [thin], ball: [500, 350, vf * Math.SQRT1_2, vf * Math.SQRT1_2], frames: F })
    S.push({ name: 'fast_thin_vertical', segs: [[700, 200, 700, 700]], ball: [400, 400, vf, 0], frames: F })
    S.push({ name: 'fast_thin_near_end', segs: [thin], ball: [403, 300, 0, vf], frames: F })
    // spawned exactly touching (centre at distance R) and overlapping by 3 px (distance R - 3), floor and slope
    const slope = fix([300, 400, 900, 600])
    S.push({ name: 'spawn_touching_floor', segs: [thin], ball: [600, 500 - R, 0, 0], frames: F })
    S.push({ name: 'spawn_overlap3_floor', segs: [thin], ball: [600, 500 - R + 3, 0, 0], frames: F })
    S.push({ name: 'spawn_touching_slope', segs: [slope], ball: [...h.restingOn(slope, 0.4), 0, 0], frames: F })
    S.push({ name: 'spawn_overlap3_slope', segs: [slope], ball: [...h.restingOn(slope, 0.4, R - 3), 0, 0], frames: F })
    // chains of 3-5 joined segments on circular arcs: convex (a hump, ball dropped near its top) and concave (a bowl)
    for (const n of [3, 4, 5])
    {
        S.push({ name: `chain_convex_${n}`, segs: arc(640, 800, 300, -150, -30, n), ball: [652, 400, 0, 0], frames: F })
        S.push({ name: `chain_concave_${n}`, segs: arc(640, 300, 300, 30, 150, n), ball: [520, 450, 0, 0], frames: F })
    }
    // the srcId-10 shelf pocket (artifacts/edges_bug.png, TASK-197), the 3 edge_cases starts, 10 s each
    // every scene but the single thin line ones and the level pocket runs inside a box (walls x = 20 / 1260, floor
    // y = 780), so the ball stays on the map for the full 10 s instead of rolling off
    for (const sc of S) if (!/^fast_thin_/.test(sc.name)) sc.segs = sc.segs.concat(BOX)
    POCKET_STARTS.forEach((b, i) => S.push({ name: `shelf_pocket_src10_${i}`, segs: SHELF10, ball: b, frames: F }))
    return S
}

// ---------------- fuzz (the tests/physics/invariants.mjs / energy.mjs generator) ----------------
function rng(seed)
{
    let a = seed >>> 0
    return function ()
    {
        a = (a + 0x6D2B79F5) >>> 0
        let t = a
        t = Math.imul(t ^ (t >>> 15), t | 1)
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }
}
function makeScene(rand)
{
    const n = 1 + Math.floor(rand() * 4), segs = []
    while (segs.length < n)
    {
        const x1 = 60 + rand() * 1160, y1 = 120 + rand() * 640, L = 30 + rand() * 570, a = rand() * 2 * Math.PI
        const x2 = x1 + L * Math.cos(a), y2 = y1 + L * Math.sin(a)
        if (x2 < 60 || x2 > 1220 || y2 < 120 || y2 > 760) continue
        segs.push([x1, y1, x2, y2].map(v => Math.round(v * 100) / 100))
    }
    for (let tries = 0; ; ++tries)
    {
        const s = segs[Math.floor(rand() * segs.length)], t = rand()
        const x = s[0] + t * (s[2] - s[0]) + (rand() * 40 - 20), y = s[1] + t * (s[3] - s[1]) - (20 + rand() * 280)
        const vx = rand() < 0.5 ? 0 : (rand() < 0.5 ? -0.01 : 0.01)
        if (y > R && x > R && x < 1280 - R && h.distToSegments(x, y, segs) >= R + 1)
            return { segs, ball: [Math.round(x * 100) / 100, Math.round(y * 100) / 100, vx, 0] }
        if (tries > 1000) return makeScene(rand)
    }
}

// ---------------- runner ----------------
function runScene(sc)
{
    const w = h.makeFastWorld(sc.segs), b = w.ball(...sc.ball)
    const chk = makeChecker(sc.segs, b.posX, b.posY)
    const n = sc.frames * STEPS_PER_FRAME
    let offMap = false
    for (let s = 0; s < n; ++s)
    {
        const x0 = b.posX, y0 = b.posY
        w.step(b)
        chk.step(x0, y0, b.posX, b.posY, b.speedX, b.speedY)
        if (!b.onMap()) { offMap = true; break }
    }
    const res = chk.result()
    res.offMap = offMap
    res.end = [b.posX, b.posY].map(rr)
    return res
}

function shard(spec)
{
    const frames = +arg('--frames', 300), N = +arg('--scenes', 200)
    const out = []
    if (spec.startsWith('det:'))
    {
        const [k, m] = spec.slice(4).split('/').map(Number)
        const only = arg('--only', null), want = only ? only.split(',') : null
        const all = deterministicScenes().filter(s => !want || want.indexOf(s.name) >= 0)
        for (let i = k; i < all.length; i += m)
        {
            const sc = all[i]
            out.push(Object.assign({ name: sc.name, order: i }, runScene(sc), { segs: sc.segs, ball: sc.ball }))
        }
    }
    else
    {
        const seed = +spec.slice(5), rand = rng(seed)
        for (let i = 0; i < N; ++i)
        {
            const sc = makeScene(rand)
            const res = runScene({ segs: sc.segs, ball: sc.ball, frames })
            const s = Object.assign({ name: `fuzz_s${seed}_${i}`, seed, index: i }, res)
            if (!res.pass) { s.segs = sc.segs; s.ball = sc.ball }
            out.push(s)
        }
    }
    process.stdout.write(JSON.stringify(out))
}

function runChild(spec)
{
    return new Promise((resolve, reject) =>
    {
        const args = [SELF, '--shard', spec]
        for (const k of ['--frames', '--scenes', '--only']) { const v = arg(k, null); if (v !== null) args.push(k, v) }
        const p = spawn(process.execPath, args, { stdio: ['ignore', 'pipe', 'inherit'] })
        let buf = ''
        p.stdout.on('data', d => { buf += d })
        p.on('close', code => code === 0 ? resolve(JSON.parse(buf)) : reject(new Error(`shard ${spec} exited ${code}`)))
    })
}

function commit()
{
    try { return execSync('git rev-parse --short HEAD', { cwd: h.ROOT }).toString().trim() } catch (e) { return null }
}
function ballDirty()
{
    try { return execSync('git status --porcelain js/ball.js js/sprite.js js/portal.js', { cwd: h.ROOT }).toString().trim() !== '' } catch (e) { return null }
}
const params = () => ({ R, stepsPerFrame: STEPS_PER_FRAME, fps: FPS, depthTolPx: DEPTH_TOL, endEpsPx: END_EPS, livelockBoxPx: h.LIVELOCK_BOX_PX,
    livelockMeanSpeed: h.LIVELOCK_MEAN_SPEED, freezeBoxPx: FREEZE_BOX, freezeOverlapPx: FREEZE_OVERLAP, freezeFrames: FREEZE_FRAMES })

async function main()
{
    const t0 = Date.now()
    const specs = []
    for (let k = 0; k < DET_SHARDS; ++k) specs.push(`det:${k}/${DET_SHARDS}`)
    if (!has('--no-fuzz'))
    {
        const [a, b] = arg('--fuzz', '1-3').split('-').map(Number)
        for (let s = a; s <= b; ++s) specs.push(`fuzz:${s}`)
    }
    const parts = await Promise.all(specs.map(runChild))
    const det = [].concat(...parts.slice(0, DET_SHARDS)).sort((a, b) => a.order - b.order)
    const fuzz = [].concat(...parts.slice(DET_SHARDS))
    const tot = (l) =>
    {
        const t = { scenes: l.length, failing: 0, steps: 0, offMap: 0, transientDeep: 0, maxDepth: 0, a: 0, b: 0, c: 0, d: 0, scenesFailing: { a: 0, b: 0, c: 0, d: 0 } }
        for (const s of l)
        {
            t.steps += s.steps; t.transientDeep += s.transientDeep; if (s.offMap) ++t.offMap
            if (s.maxDepth > t.maxDepth) t.maxDepth = s.maxDepth
            if (!s.pass) ++t.failing
            for (const k of CHECKS) { t[k] += s.counts[k]; if (s.counts[k]) ++t.scenesFailing[k] }
        }
        return t
    }
    const failingDet = det.filter(s => !s.pass), failingFuzz = fuzz.filter(s => !s.pass)
    const exit = failingDet.length || failingFuzz.length ? 1 : 0
    const report = {
        mode: 'suite', commit: commit(), ballOrPortalDirty: ballDirty(), params: params(),
        fuzzParams: { fuzz: has('--no-fuzz') ? null : arg('--fuzz', '1-3'), scenes: +arg('--scenes', 200), frames: +arg('--frames', 300) },
        wallSeconds: (Date.now() - t0) / 1000, exit,
        totals: { det: tot(det), fuzz: tot(fuzz) },
        failingScenes: failingDet.map(s => ({ name: s.name, counts: s.counts })),
        failingFuzz: failingFuzz.map(s => ({ name: s.name, counts: s.counts })),
        scenes: det.map(s => { const o = Object.assign({}, s); delete o.order; return o }),
        fuzz: fuzz.map(s => s.pass ? { name: s.name, pass: true, steps: s.steps, transientDeep: s.transientDeep, maxDepth: s.maxDepth } : s),
    }
    const outFile = arg('--out', null)
    if (outFile) fs.writeFileSync(outFile, JSON.stringify(report) + '\n')
    for (const s of det)
        console.log(`${s.pass ? 'PASS' : 'FAIL'} ${s.name} frames ${s.frames} a ${s.counts.a} b ${s.counts.b} c ${s.counts.c} d ${s.counts.d} transientDeep ${s.transientDeep} maxDepth ${s.maxDepth}${s.offMap ? ' offMap' : ''}`)
    const tf = report.totals.fuzz
    console.log(`fuzz: ${tf.scenes} scenes, ${tf.failing} failing, a ${tf.a} b ${tf.b} c ${tf.c} d ${tf.d}, maxDepth ${tf.maxDepth}`)
    console.log(`wall ${report.wallSeconds}s`)
    console.log(exit ? `STUCK FAIL: ${failingDet.map(s => s.name).join(', ')}${failingFuzz.length ? ` + ${failingFuzz.length} fuzz` : ''}` : 'STUCK PASS')
    process.exit(exit)
}

// ---------------- selftest ----------------
// Synthetic traces over a floor (100,400)-(900,400), 80 frames each (500 steps per frame), fed to the same checker:
//   clean:    a ball rolling along the floor (centre at y = 390, distance R) at 0.01 px/step -> no check fires
//   deep:     a ball moving right at 0.01 px/step whose centre sinks to 2 px under R for 10 steps, then back -> a only
//   tunnel:   a ball at 0.01 px/step moving down, centre jumping from y = 385 to y = 415 in one step (distance 15 px
//             both sides, so no overlap), then moving on -> b only
//   livelock: a ball far from the floor alternating between x = 500 and 500.5 with |v| = 0.01 -> c only
//   freeze:   a ball standing still (v = 0) 0.3 px inside the floor (distance R - 0.3, under the 0.5 px depth gate)
//             -> d only
function synthTrace(kind)
{
    const out = [], N = 80 * STEPS_PER_FRAME
    let x = 200, y = 390
    for (let s = 0; s < N; ++s)
    {
        const x0 = x, y0 = y
        let vx = 0.01, vy = 0
        if (kind === 'clean' || kind === 'deep') { x += vx; y = 390; if (kind === 'deep' && s >= 1000 && s < 1010) y = 392 }
        else if (kind === 'tunnel') { vx = 0.01; vy = 0; x += vx; y = s < 1000 ? 385 : 415 }
        else if (kind === 'livelock') { y = 200; x = s % 2 ? 500.5 : 500; vx = s % 2 ? 0.01 : -0.01 }
        else if (kind === 'freeze') { x = 500; y = 390.3; vx = 0 }
        out.push([x0, y0, x, y, vx, vy])
    }
    return out
}
function selftest()
{
    const floor = [[100, 400, 900, 400]]
    const cases = []
    for (const [kind, expect] of [['clean', null], ['deep', 'a'], ['tunnel', 'b'], ['livelock', 'c'], ['freeze', 'd']])
    {
        const tr = synthTrace(kind)
        const start = kind === 'freeze' ? [500, 390.3] : kind === 'livelock' ? [500, 200] : [200, kind === 'tunnel' ? 385 : 390]
        const c = makeChecker(floor, start[0], start[1])
        tr.forEach(t => c.step(...t))
        const r = c.result()
        const fired = CHECKS.filter(k => r.counts[k] > 0)
        const pass = expect === null ? fired.length === 0 : (fired.length === 1 && fired[0] === expect)
        cases.push({ name: `synthetic_${kind}`, expect: expect || 'none', fired, counts: r.counts, transientDeep: r.transientDeep, maxDepth: r.maxDepth, pass, examples: r.examples })
    }
    {
        const r = runScene({ segs: [[100, 600, 1100, 600]], ball: [600, 500, 0.003, 0], frames: 120 })
        const fired = CHECKS.filter(k => r.counts[k] > 0)
        cases.push({ name: 'real_floor_drop', expect: 'none', fired, counts: r.counts, transientDeep: r.transientDeep, maxDepth: r.maxDepth, pass: fired.length === 0 })
    }
    const pass = cases.every(c => c.pass)
    for (const c of cases) console.log(`${c.pass ? 'PASS' : 'FAIL'} ${c.name} expect ${c.expect} fired [${c.fired.join(',')}] counts ${JSON.stringify(c.counts)}`)
    console.log(pass ? 'SELFTEST PASS' : 'SELFTEST FAIL')
    const report = { mode: 'selftest', commit: commit(), pass, params: params(), cases }
    const outFile = arg('--out', null)
    if (outFile) fs.writeFileSync(outFile, JSON.stringify(report) + '\n')
    process.exit(pass ? 0 : 1)
}

if (has('--shard')) shard(arg('--shard'))
else if (has('--selftest')) selftest()
else main().catch(e => { console.error(e); process.exit(2) })
