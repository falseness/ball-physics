// Energy conservation suite (TASK-266). Runs the real js/ball.js (tests/physics/harness.mjs fast loader, 500 steps
// per frame, every step checked) on named deterministic scenes plus seeded random fuzz scenes, and checks that the
// ball neither loses nor gains energy (no portals here: a teleport is exempt by rule T, it keeps speed, not height).
//
// Energy: E = |v|^2/2 + g vy/2 + g (H - y), px/step units, H = 800 (as tests/physics/invariants_core.js I3). It is
// the exact free-flight invariant of the game's integrator (ball.physics(): contacts, v += g; ball.move(): x += v),
// so a free step keeps it to rounding and an elastic contact must keep it too.
// E_ref of a scene = g H + max |v|^2/2 over the scene (initial state and every step).
//   per step (every step, contact or free):   |E1 - E0| <= 1e-9 * E_ref
//   per scene:                                |E_end - E_start| <= 1e-7 * E_ref
// A step is a contact step when the centre at the start of the step is within R + 1e-9 (js/ball.js CONTACT_SLOP) of
// a line (ball.physics() resolves contacts at the start position), else a free step. Losses (E1 < E0) and gains
// (E1 > E0) are counted separately, with the 5 worst of each (position / velocity before and after).
// A scene ends early when the ball leaves the map (the game restarts the level there).
//
//   node tests/physics/energy.mjs [--out FILE] [--fuzz A-B] [--scenes N] [--frames F] [--only name,name] [--no-fuzz]
//       deterministic scenes + fuzz seeds A..B (default 1-3), N scenes each (default 200), F frames each (default
//       300) of random 1-4 line scenes (the tests/physics/invariants.mjs generator); work is split into parallel
//       child processes (--shard internally).
//   node tests/physics/energy.mjs --selftest [--out FILE]
//       synthetic traces: a clean one must pass, one with a loss and one with a gain must each fail with that sign.
// Output: compact JSON (per failing scene: loss/gain counts, worst examples, end drift; totals). Exit 1 when any
// scene fails (or a selftest check fails), 0 otherwise.
// Node 12: no ?? / ?. syntax.
import fs from 'node:fs'
import path from 'node:path'
import { spawn, execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import * as h from './harness.mjs'

const SELF = fileURLToPath(import.meta.url)
const { R, G, STEPS_PER_FRAME } = h
const H = 800, STEP_REL = 1e-9, SCENE_REL = 1e-7, CONTACT_EPS = 1e-9, MAX_EX = 5
const DET_SHARDS = 3

function arg(name, def)
{
    const i = process.argv.indexOf(name)
    return i < 0 ? def : process.argv[i + 1]
}
const has = (name) => process.argv.includes(name)
const rr = (v) => (typeof v === 'number' && isFinite(v)) ? +v.toPrecision(10) : v

export function energy(y, vx, vy) { return 0.5 * (vx * vx + vy * vy) + 0.5 * G * vy + G * (H - y) }

// ---------------- checker ----------------
// Feed every step: step(x0, y0, vx0, vy0, x1, y1, vx1, vy1). Candidates beyond the (still growing) running threshold
// are kept and re-filtered against the final E_ref in result().
export function makeChecker(segs, x, y, vx, vy)
{
    const boxes = segs.map(s => [Math.min(s[0], s[2]) - R - 1, Math.max(s[0], s[2]) + R + 1, Math.min(s[1], s[3]) - R - 1, Math.max(s[1], s[3]) + R + 1])
    let maxKE = 0.5 * (vx * vx + vy * vy), steps = 0, contactSteps = 0
    const Estart = energy(y, vx, vy)
    let Eend = Estart
    const cand = []
    function inContact(px, py)
    {
        for (let i = 0; i < segs.length; ++i)
        {
            const b = boxes[i]
            if (px < b[0] || px > b[1] || py < b[2] || py > b[3]) continue
            const c = h.closestOnSegment(px, py, segs[i])
            if (Math.hypot(px - c[0], py - c[1]) < R + CONTACT_EPS) return true
        }
        return false
    }
    return {
        step(x0, y0, vx0, vy0, x1, y1, vx1, vy1)
        {
            ++steps
            const contact = inContact(x0, y0)
            if (contact) ++contactSteps
            const ke = 0.5 * (vx1 * vx1 + vy1 * vy1)
            if (ke > maxKE) maxKE = ke
            const E0 = energy(y0, vx0, vy0), E1 = energy(y1, vx1, vy1), dE = E1 - E0
            Eend = E1
            if (Math.abs(dE) > STEP_REL * (G * H + maxKE))
                cand.push({ step: steps - 1, dE, contact, pos0: [x0, y0], v0: [vx0, vy0], pos1: [x1, y1], v1: [vx1, vy1] })
        },
        result()
        {
            const Eref = G * H + maxKE, lim = STEP_REL * Eref
            const viol = cand.filter(c => Math.abs(c.dE) > lim)
            const side = (sign) =>
            {
                const l = viol.filter(c => sign < 0 ? c.dE < 0 : c.dE > 0)
                const worst = l.slice().sort((a, b) => Math.abs(b.dE) - Math.abs(a.dE)).slice(0, MAX_EX).map(c => ({
                    step: c.step, frame: Math.floor(c.step / STEPS_PER_FRAME), dE: rr(c.dE), rel: rr(c.dE / Eref), contact: c.contact,
                    pos0: c.pos0.map(rr), v0: c.v0.map(rr), pos1: c.pos1.map(rr), v1: c.v1.map(rr) }))
                let sum = 0
                for (const c of l) sum += c.dE
                return { steps: l.length, contactSteps: l.filter(c => c.contact).length, freeSteps: l.filter(c => !c.contact).length, sumDE: rr(sum), worst }
            }
            const drift = Eend - Estart
            const endFail = Math.abs(drift) > SCENE_REL * Eref
            const loss = side(-1), gain = side(1)
            return {
                steps, contactSteps, freeSteps: steps - contactSteps, Eref: rr(Eref), Estart: rr(Estart), Eend: rr(Eend),
                endDrift: rr(drift), endDriftRel: rr(drift / Eref), endFail, endSign: endFail ? (drift < 0 ? 'loss' : 'gain') : null,
                loss, gain, pass: !endFail && loss.steps === 0 && gain.steps === 0,
            }
        },
    }
}

// ---------------- scenes ----------------
const rad = (d) => d * Math.PI / 180
function slopeLine(deg, cx = 640, cy = 500, half = 300)
{
    // descending to the right (screen y grows downward)
    const c = Math.cos(rad(deg)), s = Math.sin(rad(deg))
    return [cx - half * c, cy - half * s, cx + half * c, cy + half * s].map(v => +v.toFixed(6))
}
// The level lines of srcId 6 (js/levels.js, 6th definition) and the 3 player lines of artifacts/energy_lost.png
const SRC6_LEVEL = [[0, 280, 450, 280], [450, 280, 450, 400], [450, 400, 280, 400]]
const SRC6_PLAYER = [[132, 58, 881, 153], [540, 624, 961, 27], [1000, 199, 1031, 778]]

export function deterministicScenes()
{
    const S = []
    const floor = [200, 700, 1000, 700]
    // floor drops: gap between the ball's bottom and the floor
    for (const d of [1, 2, 5, 10, 17, 30, 100, 300])
        S.push({ name: `floor_drop_${d}px`, segs: [floor], ball: [600, 700 - R - d, 0, 0], frames: 600 })
    // drops onto slopes, 100 px above the slope at x = 600
    for (const a of [5, 20, 45, 70])
    {
        const L = slopeLine(a), ys = L[1] + (600 - L[0]) * Math.tan(rad(a))
        S.push({ name: `slope_drop_${a}deg`, segs: [L], ball: [600, +(ys - R / Math.cos(rad(a)) - 100).toFixed(6), 0, 0], frames: 300 })
    }
    // rolls from rest at 20 % of the slope
    for (const a of [7, 20, 45])
    {
        const L = slopeLine(a), p = h.restingOn(L, 0.2)
        S.push({ name: `slope_roll_${a}deg`, segs: [L], ball: [p[0], p[1], 0, 0], frames: 300 })
    }
    // V corners (opening angle), vertex (640, 600), arms 300 px; dropped 25 px right of the axis, 200 px above the vertex
    for (const a of [30, 60, 90, 120])
    {
        const hh = rad(a / 2), V = [640, 600]
        const l = [V[0] - 300 * Math.sin(hh), V[1] - 300 * Math.cos(hh)], r = [V[0] + 300 * Math.sin(hh), V[1] - 300 * Math.cos(hh)]
        S.push({ name: `v_corner_${a}deg`, segs: [[...l, ...V].map(v => +v.toFixed(6)), [...V, ...r].map(v => +v.toFixed(6))],
            ball: [V[0] + 25, V[1] - 200, 0, 0], frames: 600 })
    }
    // line ends of (400,300)-(700,300): a drop whose centre is d px left of the free end (400, 300) (hit), and a ball
    // moving right at 0.02 px/step whose centre passes d px above the end (graze, as edge_cases graze)
    for (let d = 1; d <= 9; ++d)
    {
        S.push({ name: `end_hit_${d}px`, segs: [[400, 300, 700, 300]], ball: [400 - d, 250, 0, 0], frames: 300 })
        S.push({ name: `end_graze_${d}px`, segs: [[400, 300, 700, 300]], ball: [400 - Math.sqrt(R * R - d * d) - 2, 300 - d, 0.02, 0], frames: 300 })
    }
    // spike tip (as edge_cases spike)
    S.push({ name: 'spike_tip', segs: [[400, 300, 400, 500]], ball: [403, 270, 0, 0], frames: 300 })
    // convex joint (a ridge: 20 deg up then 20 deg down, joined at (640, 400)) and concave joint (slope into a floor)
    S.push({ name: 'joint_convex', segs: [[400, 487.35, 640, 400], [640, 400, 880, 487.35]], ball: [652, 360, 0, 0], frames: 300 })
    S.push({ name: 'joint_concave', segs: [[100, 200, 400, 300], [400, 300, 700, 300]], ball: [...h.restingOn([100, 200, 400, 300], 0.1), 0, 0], frames: 600 })
    // two crossing lines (an X), dropped onto the upper V of the X
    S.push({ name: 'crossing_lines', segs: [[400, 300, 800, 600], [400, 600, 800, 300]], ball: [610, 300, 0, 0], frames: 600 })
    // a 2-px-from-parallel pair: a floor and a line over it whose ends differ by 2 px in height (a narrowing slot)
    S.push({ name: 'near_parallel_pair', segs: [[300, 600, 900, 600], [300, 570, 900, 572]], ball: [500, 588, 0.01, 0], frames: 300 })
    // high-speed hits, initial speed 20 px/frame (0.04 px/step)
    const vf = 20 / STEPS_PER_FRAME
    S.push({ name: 'fast_floor_down', segs: [floor], ball: [600, 400, 0, vf], frames: 300 })
    S.push({ name: 'fast_floor_oblique', segs: [floor], ball: [400, 400, vf * Math.SQRT1_2, vf * Math.SQRT1_2], frames: 300 })
    S.push({ name: 'fast_slope_45', segs: [slopeLine(45)], ball: [500, 200, vf, 0], frames: 300 })
    S.push({ name: 'fast_v_90', segs: [[440, 400, 640, 600], [640, 600, 840, 400]], ball: [600, 300, 0, vf], frames: 300 })
    // long run: 10000 frames of floor bouncing (drop of 50 px)
    S.push({ name: 'floor_bounce_10000f', segs: [floor], ball: [600, 700 - R - 50, 0, 0], frames: 10000 })
    // srcId 6 replay (artifacts/energy_lost.png): the level's own lines plus the 3 player lines, ball from the start
    S.push({ name: 'src6_replay', segs: [...SRC6_LEVEL, ...SRC6_PLAYER], ball: [200, 50, 0, 0], frames: 600 })
    return S
}

// ---------------- fuzz (the tests/physics/invariants.mjs generator) ----------------
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
    const chk = makeChecker(sc.segs, b.posX, b.posY, b.speedX, b.speedY)
    const n = sc.frames * STEPS_PER_FRAME
    let offMap = false
    for (let s = 0; s < n; ++s)
    {
        const x0 = b.posX, y0 = b.posY, vx0 = b.speedX, vy0 = b.speedY
        w.step(b)
        chk.step(x0, y0, vx0, vy0, b.posX, b.posY, b.speedX, b.speedY)
        if (!b.onMap()) { offMap = true; break }
    }
    const res = chk.result()
    res.offMap = offMap
    return res
}
function summarize(name, res, extra)
{
    const o = Object.assign({ name, pass: res.pass }, extra || {})
    o.steps = res.steps; o.contactSteps = res.contactSteps; o.offMap = res.offMap
    o.loss = { steps: res.loss.steps, contact: res.loss.contactSteps, free: res.loss.freeSteps, sumDE: res.loss.sumDE }
    o.gain = { steps: res.gain.steps, contact: res.gain.contactSteps, free: res.gain.freeSteps, sumDE: res.gain.sumDE }
    o.Eref = res.Eref; o.endDrift = res.endDrift; o.endDriftRel = res.endDriftRel; o.endFail = res.endFail
    if (!res.pass)
    {
        o.failSides = [res.loss.steps || res.endSign === 'loss' ? 'loss' : null, res.gain.steps || res.endSign === 'gain' ? 'gain' : null].filter(Boolean)
        o.worstLoss = res.loss.worst; o.worstGain = res.gain.worst
    }
    return o
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
        // greedy balance by step budget (the 10000-frame run alone is a big part)
        const bins = Array.from({ length: m }, () => ({ cost: 0, idx: [] }))
        all.map((s, i) => [s.frames, i]).sort((a, b) => b[0] - a[0] || a[1] - b[1]).forEach(([c, i]) =>
        {
            const bin = bins.reduce((a, b) => (b.cost < a.cost ? b : a))
            bin.cost += c; bin.idx.push(i)
        })
        for (const i of bins[k].idx.sort((a, b) => a - b))
        {
            const sc = all[i]
            out.push(Object.assign(summarize(sc.name, runScene(sc)), { order: i, segs: sc.segs, ball: sc.ball, frames: sc.frames }))
        }
    }
    else
    {
        const seed = +spec.slice(5), rand = rng(seed)
        for (let i = 0; i < N; ++i)
        {
            const sc = makeScene(rand)
            const res = runScene({ segs: sc.segs, ball: sc.ball, frames })
            const s = summarize(`fuzz_s${seed}_${i}`, res, { seed, index: i })
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
    try { return execSync('git status --porcelain js/ball.js js/portal.js', { cwd: h.ROOT }).toString().trim() !== '' } catch (e) { return null }
}

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
    const all = det.concat(fuzz)
    const tot = { scenes: all.length, failing: 0, steps: 0, contactSteps: 0, loss: { scenes: 0, steps: 0, contact: 0, free: 0 }, gain: { scenes: 0, steps: 0, contact: 0, free: 0 }, endDriftFail: 0 }
    const wl = [], wg = []
    for (const s of all)
    {
        tot.steps += s.steps; tot.contactSteps += s.contactSteps
        if (!s.pass) ++tot.failing
        if (s.endFail) ++tot.endDriftFail
        for (const side of ['loss', 'gain'])
        {
            const t = tot[side], x = s[side]
            if (s.failSides && s.failSides.indexOf(side) >= 0) ++t.scenes
            t.steps += x.steps; t.contact += x.contact; t.free += x.free
        }
        for (const e of s.worstLoss || []) wl.push(Object.assign({ scene: s.name }, e))
        for (const e of s.worstGain || []) wg.push(Object.assign({ scene: s.name }, e))
    }
    const worst = (l) => l.sort((a, b) => Math.abs(b.rel) - Math.abs(a.rel)).slice(0, MAX_EX)
    const failingDet = det.filter(s => !s.pass)
    const report = {
        mode: 'suite', commit: commit(), ballOrPortalDirty: ballDirty(),
        params: { g: G, H, R, stepsPerFrame: STEPS_PER_FRAME, stepRel: STEP_REL, sceneRel: SCENE_REL, contactEps: CONTACT_EPS,
            fuzz: has('--no-fuzz') ? null : arg('--fuzz', '1-3'), fuzzScenes: +arg('--scenes', 200), fuzzFrames: +arg('--frames', 300) },
        wallSeconds: (Date.now() - t0) / 1000,
        exit: tot.failing ? 1 : 0,
        totals: tot,
        failingScenes: failingDet.map(s => s.name),
        failingFuzz: fuzz.filter(s => !s.pass).map(s => s.name),
        failingSummary: failingDet.map(s => ({ name: s.name, sides: s.failSides, loss: s.loss.steps, gain: s.gain.steps, endDriftRel: s.endDriftRel })),
        worstLoss: worst(wl), worstGain: worst(wg),
        scenes: det.map(s => { const o = Object.assign({}, s); delete o.order; return o }),
        fuzz: fuzz.map(s => s.pass ? { name: s.name, pass: true, steps: s.steps } : s),
    }
    const outFile = arg('--out', null)
    if (outFile) fs.writeFileSync(outFile, JSON.stringify(report) + '\n')
    for (const s of det)
        console.log(`${s.pass ? 'PASS' : 'FAIL'} ${s.name} steps ${s.steps} loss ${s.loss.steps} (sum ${s.loss.sumDE}) gain ${s.gain.steps} (sum ${s.gain.sumDE}) endDriftRel ${s.endDriftRel}`)
    console.log(`fuzz: ${fuzz.length} scenes, ${report.failingFuzz.length} failing`)
    console.log(`totals: scenes ${tot.scenes} failing ${tot.failing} steps ${tot.steps} contactSteps ${tot.contactSteps} loss steps ${tot.loss.steps} (scenes ${tot.loss.scenes}) gain steps ${tot.gain.steps} (scenes ${tot.gain.scenes}) wall ${report.wallSeconds}s`)
    console.log(tot.failing ? `ENERGY FAIL: ${failingDet.map(s => s.name).join(', ')}${report.failingFuzz.length ? ` + ${report.failingFuzz.length} fuzz` : ''}` : 'ENERGY PASS')
    process.exit(report.exit)
}

// ---------------- selftest ----------------
// Synthetic traces over a floor (100,400)-(900,400): the exact integrator in free flight, and an energy-exact bounce
// (outgoing normal speed chosen to keep E) -> must pass; the same trace with one bounce at 0.9 of the outgoing
// speed (loss) and one with the outgoing speed + 2g (gain) -> must fail with that sign only; plus a real js/ball.js
// free fall with no lines (must pass) as a sanity check of the runner.
function synthTrace(kind)
{
    const floorY = 400, out = []
    let x = 500, y = 300, vx = 0.003, vy = 0, bounces = 0
    for (let s = 0; s < 40000; ++s)
    {
        const x0 = x, y0 = y, vx0 = vx, vy0 = vy
        if (y > floorY - R && vy > 0)
        {
            // floor normal (0, -1): vn = -vy; E-exact outgoing normal speed w: 0.5 w^2 + b w = 0.5 vn^2 + b vn, b = -g/2
            const vn = -vy, b = -0.5 * G
            let w = -b + Math.sqrt(b * b + vn * vn + 2 * b * vn)
            ++bounces
            if (bounces === 2 && kind === 'loss') w *= 0.9
            if (bounces === 2 && kind === 'gain') w += 2 * G
            vy = -w
        }
        vy += G
        x += vx; y += vy
        out.push([x0, y0, vx0, vy0, x, y, vx, vy])
    }
    return out
}
function selftest()
{
    const floor = [[100, 400, 900, 400]]
    const cases = []
    for (const [kind, expect] of [['clean', null], ['loss', 'loss'], ['gain', 'gain']])
    {
        const tr = synthTrace(kind), c = makeChecker(floor, tr[0][0], tr[0][1], tr[0][2], tr[0][3])
        tr.forEach(t => c.step(...t))
        const r = c.result()
        const sides = [r.loss.steps ? 'loss' : null, r.gain.steps ? 'gain' : null].filter(Boolean)
        const pass = expect === null ? r.pass : (!r.pass && sides.length === 1 && sides[0] === expect && r.endSign === expect)
        cases.push({ name: `synthetic_${kind}`, expect: expect || 'pass', steps: r.steps, contactSteps: r.contactSteps, lossSteps: r.loss.steps,
            gainSteps: r.gain.steps, endDriftRel: r.endDriftRel, endSign: r.endSign, scenePass: r.pass, pass, example: (r.loss.worst[0] || r.gain.worst[0] || null) })
    }
    {
        const r = runScene({ segs: [], ball: [300, 100, 0.01, 0], frames: 20 })
        cases.push({ name: 'real_free_fall', expect: 'pass', steps: r.steps, lossSteps: r.loss.steps, gainSteps: r.gain.steps, endDriftRel: r.endDriftRel, scenePass: r.pass, pass: r.pass })
    }
    const pass = cases.every(c => c.pass)
    for (const c of cases) console.log(`${c.pass ? 'PASS' : 'FAIL'} ${c.name} expect ${c.expect} loss ${c.lossSteps} gain ${c.gainSteps} endDriftRel ${c.endDriftRel}`)
    console.log(pass ? 'SELFTEST PASS' : 'SELFTEST FAIL')
    const report = { mode: 'selftest', commit: commit(), pass, params: { stepRel: STEP_REL, sceneRel: SCENE_REL }, cases }
    const outFile = arg('--out', null)
    if (outFile) fs.writeFileSync(outFile, JSON.stringify(report) + '\n')
    process.exit(pass ? 0 : 1)
}

if (has('--shard')) shard(arg('--shard'))
else if (has('--selftest')) selftest()
else main().catch(e => { console.error(e); process.exit(2) })
