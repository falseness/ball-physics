// Fast portal suite (TASK-269): "not stuck in textures" and energy around portal interactions, in node (no browser).
// Runs the real js/ball.js + js/portal.js + index.html's gamePhysics() (tests/physics/harness.mjs makePortalWorld,
// TASK-268, bit-identical to the browser), every step checked. No physics change.
//
// Geometry: the scene's lines, each wall portal's opening (c +- h t) cut out of its host line ('solid', as
// tests/physics/invariants_browser.py does for I1). A step is a teleport step when portalState.teleports grows.
// Checks (counts per scene):
//   a post-teleport embed: in the teleport step and the 2 steps after it, the centre is never closer than 0.5 px to
//     a solid segment (the exit host's pieces or any other line), i.e. no overlap deeper than R - 0.5 px.
//     (aShallow, info only: the same steps with an overlap deeper than 0.5 px, distance < R - 0.5)
//   b no rim trap (tests/portal/rimtrap.py definition): after a teleport the ball leaves the exit portal's zone
//     (centre within h + r + 2 px of the exit centre) within 60 frames, unless... it is still there after 60 frames with
//     no further teleport while its mean speed along the exit's tangent over those frames is > 1 px/frame: that is
//     the rim shuttle -> b (bExit). A ball still in the zone that is not shuttling (resting / bouncing in place) is
//     counted as `linger` (info). Also the rimtrap.py detector itself over the whole run, any portal (240 frames,
//     same rule) -> b (bRim240).
//   c teleport speed (rule T): |v at the end of the teleport step| = |v right before portalStep| (teleport record
//     `before`) within 1e-9 relative (rim bounces later in the same step keep |v| too).
//   d energy, two-sided (as tests/physics/energy.mjs, TASK-266): E = |v|^2/2 + g vy/2 + g (H - y), H = 800, px/step;
//     on every non-teleport step |E1 - E0| <= 1e-9 * E_ref, E_ref = g H + max |v|^2/2 over the scene. Losses and
//     gains are counted separately (dLoss / dGain).
//   e stuck (tests/physics/stuck.mjs makeChecker, TASK-267, on the solid geometry): e.a depth (> 0.5 px for two
//     consecutive states), e.b tunnelling (centre crosses a solid segment's interior; not tested on teleport
//     steps), e.c livelock, e.d freeze. e.a is counted per deep run here: a run of consecutive deep states that
//     ends in a teleport step is a capture (the TASK-074 'generous edge': a ball being captured is not stopped by
//     the host line next to the opening, it sinks in until it touches the opening and is teleported; the same rule
//     tests/physics/invariants_browser.py's capture zone exempts) and is counted as captureDeep (info); every other
//     run (it ends with the ball out of the line, or the scene ends) counts its steps as e.a, as in stuck.mjs.
//     eaAfterExit (info, part of e.a): e.a steps of runs that began in the teleport step itself (the exit placement,
//     local (-clamp(s), d) with the entry depth d < r, left the ball overlapping the exit's host line by > 0.5 px).
// Scenes:
//   levels:  every level of js/levels.js with a portal pair; for each portal of the pair, each half of its opening
//            (s = -h/2, +h/2), 3 speeds (3 / 10 / 20 px/frame) x 3 angles (-30 / 0 / +30 deg from the normal): the
//            ball starts 3 px before touching the opening, moving into its front (the level's own lines only, no
//            player lines); 300 frames.
//   repro:   the tests/portal/rimtrap.py level 19 repro (srcId 19 + its 2 player lines, 900 frames) and its 3 cfg
//            detector controls (600 frames), the tests/portal/embed.py level 24 repro (x 480 / 482, 200 frames).
//   fuzz:    tests/physics/portal_fast_scenes.py (tests/portal/fuzz.py default / crossing / backside / touching),
//            seeds 1, 2 x 100 scenes per mode, 300 frames.
// A scene ends early when the ball leaves the map (the game restarts the level there).
//
//   node tests/physics/portal_fast.mjs [--out FILE] [--seeds 1,2] [--per-mode N] [--frames F] [--jobs J] [--only group]
//   node tests/physics/portal_fast.mjs --selftest [--out FILE]
//       synthetic traces: clean, embedded-after-teleport, rim trap, teleport speed change, energy loss; each bad
//       one must fire only its own check, the clean one none.
// Output: compact JSON. Exit 1 when any scene fails a check (or a selftest case fails), 0 otherwise.
// Node 12: no ?? / ?. syntax.
import fs from 'node:fs'
import path from 'node:path'
import { spawn, execSync, execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import * as h from './harness.mjs'
import { makeChecker as makeStuckChecker } from './stuck.mjs'

const SELF = fileURLToPath(import.meta.url)
const { R, G, STEPS_PER_FRAME } = h
const H = 800, STEP_REL = 1e-9, TELE_REL = 1e-9, MAX_EX = 3
const EMBED_DIST = 0.5, EMBED_STEPS = 2, SHALLOW = 0.5
const TRAP_MARGIN = 2, TRAP_MIN_SPEED = 1.0, EXIT_FRAMES = 60, TRAP_FRAMES = 240
const CHECKS = ['a', 'b', 'c', 'd', 'e']
const LEVEL_SPEEDS = [3, 10, 20], LEVEL_ANGLES = [-30, 0, 30], GAP = 3

function arg(name, def)
{
    const i = process.argv.indexOf(name)
    return i < 0 ? def : process.argv[i + 1]
}
const has = (name) => process.argv.includes(name)
const rr = (v) => (typeof v === 'number' && isFinite(v)) ? +v.toPrecision(10) : v
export function energy(y, vx, vy) { return 0.5 * (vx * vx + vy * vy) + 0.5 * G * vy + G * (H - y) }

// ---------------- geometry ----------------
// portals: [{x, y, h, nx, ny, tx, ty, line, name}]; solid: lines with every wall portal's opening cut out
export function solidGeometry(lines, portals)
{
    const cut = {}
    portals.forEach(p => { if (typeof p.line == 'number') (cut[p.line] = cut[p.line] || []).push(p) })
    const solid = []
    lines.forEach((s, k) =>
    {
        if (!cut[k]) { solid.push(s.slice()); return }
        const dx = s[2] - s[0], dy = s[3] - s[1], L = Math.hypot(dx, dy)
        const iv = cut[k].map(p => { const u = ((p.x - s[0]) * dx + (p.y - s[1]) * dy) / (L * L), w = p.h / L; return [u - w, u + w] })
            .sort((a, b) => a[0] - b[0])
        let t = 0
        for (const [a, b] of iv)
        {
            if (a > t) solid.push([s[0] + t * dx, s[1] + t * dy, s[0] + Math.min(a, 1) * dx, s[1] + Math.min(a, 1) * dy])
            t = Math.max(t, b)
        }
        if (t < 1) solid.push([s[0] + t * dx, s[1] + t * dy, s[2], s[3]])
    })
    return solid
}
function portalsOf(W)
{
    return (W.portals() || []).map(P => ({ x: P.x, y: P.y, h: P.h, nx: Math.cos(P.angle), ny: Math.sin(P.angle),
        tx: -Math.sin(P.angle), ty: Math.cos(P.angle), line: P.line, name: P.name }))
}

// ---------------- checker ----------------
// step(x0, y0, vx0, vy0, x1, y1, vx1, vy1, tele) for every step, in order (tele: null, or {to: exit portal index,
// vb: [vx, vy] right before portalStep}); result() at the end.
export function makeChecker(geo, x, y, vx, vy)
{
    const solid = geo.solid, P = geo.portals
    const boxes = solid.map(s => [Math.min(s[0], s[2]) - R - 2, Math.max(s[0], s[2]) + R + 2, Math.min(s[1], s[3]) - R - 2, Math.max(s[1], s[3]) + R + 2])
    function minDist(px, py)
    {
        let best = Infinity
        for (let i = 0; i < solid.length; ++i)
        {
            const b = boxes[i]
            if (px < b[0] || px > b[1] || py < b[2] || py > b[3]) continue
            const c = h.closestOnSegment(px, py, solid[i]), d = Math.hypot(px - c[0], py - c[1])
            if (d < best) best = d
        }
        return best
    }
    const stuck = makeStuckChecker(solid, x, y)
    const cnt = { a: 0, b: 0, c: 0, d: 0, e: 0 }, sub = { aShallow: 0, bExit: 0, bRim240: 0, linger: 0, dLoss: 0, dGain: 0, captureDeep: 0, eaAfterExit: 0 }
    const ex = { a: [], b: [], c: [], d: [] }
    // e.a per deep run (see the header): pending = deep-after-deep steps of the current run
    let prevDeep = R - minDist(x, y) > 0.5, pending = 0, pendingEx = null, eA = 0, fromExit = false
    const eAex = []
    function closeRun(capture)
    {
        if (!pending) return
        if (capture) sub.captureDeep += pending
        else
        {
            eA += pending
            if (fromExit) { sub.eaAfterExit += pending; pendingEx.fromExit = true }
            if (eAex.length < MAX_EX) eAex.push(pendingEx)
        }
        pending = 0; pendingEx = null
    }
    let steps = 0, teleports = 0, maxKE = 0.5 * (vx * vx + vy * vy), postLeft = -1, postHit = false, postShallow = false
    const cand = []
    // (b) per-frame state
    let fk = 0, tpFrame = false, lastExit = -1
    let watch = null                       // {k, frames, sumT, from}
    const trap = P.map(() => ({ run: 0, ring: new Float64Array(TRAP_FRAMES), sum: 0 }))
    let near = -1, trapped = false
    function tangential(k, vx1, vy1) { return Math.abs(vx1 * P[k].tx + vy1 * P[k].ty) * STEPS_PER_FRAME }
    function inZone(k, px, py) { return Math.hypot(px - P[k].x, py - P[k].y) <= P[k].h + R + TRAP_MARGIN }
    function endFrame(x1, y1, vx1, vy1)
    {
        const f = Math.floor(steps / STEPS_PER_FRAME)
        // exit window
        if (tpFrame) watch = { k: lastExit, frames: 0, sumT: 0, from: f }
        else if (watch)
        {
            if (!inZone(watch.k, x1, y1)) watch = null
            else
            {
                ++watch.frames; watch.sumT += tangential(watch.k, vx1, vy1)
                if (watch.frames >= EXIT_FRAMES)
                {
                    const mean = watch.sumT / watch.frames
                    if (mean > TRAP_MIN_SPEED)
                    {
                        ++cnt.b; ++sub.bExit
                        if (ex.b.length < MAX_EX) ex.b.push({ kind: 'exit', portal: P[watch.k].name, teleportFrame: watch.from, frame: f, meanTangential: rr(mean), pos: [x1, y1].map(rr) })
                    }
                    else ++sub.linger
                    watch = null
                }
            }
        }
        // rimtrap.py detector (240 frames, any portal)
        let k = -1
        for (let i = 0; i < P.length; ++i) if (inZone(i, x1, y1)) { k = i; break }
        const T = k >= 0 ? trap[k] : null
        if (tpFrame || k < 0 || k !== near) for (const t of trap) { t.run = 0; t.sum = 0 }
        near = tpFrame ? -1 : k
        if (near >= 0)
        {
            const sp = tangential(near, vx1, vy1)
            if (T.run >= TRAP_FRAMES) T.sum -= T.ring[T.run % TRAP_FRAMES]
            T.ring[T.run % TRAP_FRAMES] = sp; T.sum += sp; ++T.run
            if (!trapped && T.run >= TRAP_FRAMES && T.sum / TRAP_FRAMES > TRAP_MIN_SPEED)
            {
                trapped = true; ++cnt.b; ++sub.bRim240
                if (ex.b.length < MAX_EX) ex.b.push({ kind: 'rim240', portal: P[near].name, frame: f, meanTangential: rr(T.sum / TRAP_FRAMES), pos: [x1, y1].map(rr) })
            }
        }
        tpFrame = false; fk = 0
    }
    return {
        step(x0, y0, vx0, vy0, x1, y1, vx1, vy1, tele)
        {
            const s = steps
            ++steps
            stuck.step(x0, y0, x1, y1, vx1, vy1, !!tele)
            const depth1 = R - minDist(x1, y1), deep = depth1 > 0.5
            if (tele) { closeRun(true); prevDeep = deep; fromExit = deep }
            else
            {
                if (deep && !prevDeep) fromExit = false
                if (deep && prevDeep) { if (!pending) pendingEx = { step: s, frame: Math.floor(s / STEPS_PER_FRAME), depth: rr(depth1), pos: [x1, y1].map(rr), v: [vx1, vy1].map(rr) }; ++pending }
                else if (!deep) closeRun(false)
                prevDeep = deep
            }
            const ke = 0.5 * (vx1 * vx1 + vy1 * vy1)
            if (ke > maxKE) maxKE = ke
            if (tele)
            {
                ++teleports; tpFrame = true; lastExit = tele.to
                const sb = Math.hypot(tele.vb[0], tele.vb[1]), sa = Math.hypot(vx1, vy1)
                if (Math.abs(sa - sb) > TELE_REL * Math.max(sb, 1e-300))
                {
                    ++cnt.c
                    if (ex.c.length < MAX_EX) ex.c.push({ step: s, vBefore: tele.vb.map(rr), vAfter: [vx1, vy1].map(rr), rel: rr((sa - sb) / sb) })
                }
                postLeft = EMBED_STEPS + 1; postHit = false; postShallow = false
            }
            else
            {
                const dE = energy(y1, vx1, vy1) - energy(y0, vx0, vy0)
                if (Math.abs(dE) > STEP_REL * (G * H + maxKE))
                    cand.push({ step: s, dE, pos0: [x0, y0], v0: [vx0, vy0], v1: [vx1, vy1] })
            }
            if (postLeft > 0)
            {
                const d = minDist(x1, y1)
                if (d < EMBED_DIST && !postHit)
                {
                    postHit = true; ++cnt.a
                    if (ex.a.length < MAX_EX) ex.a.push({ step: s, afterTeleport: EMBED_STEPS + 1 - postLeft, dist: rr(d), pos: [x1, y1].map(rr), v: [vx1, vy1].map(rr) })
                }
                if (d < R - SHALLOW && !postShallow) { postShallow = true; ++sub.aShallow }
                --postLeft
            }
            if (++fk === STEPS_PER_FRAME) endFrame(x1, y1, vx1, vy1)
        },
        result()
        {
            const Eref = G * H + maxKE, lim = STEP_REL * Eref
            const viol = cand.filter(c => Math.abs(c.dE) > lim)
            sub.dLoss = viol.filter(c => c.dE < 0).length
            sub.dGain = viol.filter(c => c.dE > 0).length
            cnt.d = viol.length
            ex.d = viol.slice().sort((p, q) => Math.abs(q.dE) - Math.abs(p.dE)).slice(0, MAX_EX).map(c => ({ step: c.step, dE: rr(c.dE), rel: rr(c.dE / Eref),
                pos0: c.pos0.map(rr), v0: c.v0.map(rr), v1: c.v1.map(rr) }))
            closeRun(false)
            const st = stuck.result()
            const e = { a: eA, b: st.counts.b, c: st.counts.c, d: st.counts.d }
            cnt.e = e.a + e.b + e.c + e.d
            const examples = {}
            for (const k of ['a', 'b', 'c', 'd']) if (ex[k].length) examples[k] = ex[k]
            if (cnt.e)
            {
                examples.e = {}
                if (eAex.length) examples.e.a = eAex
                for (const k of ['b', 'c', 'd']) if (st.examples[k]) examples.e[k] = st.examples[k]
            }
            return { steps, frames: Math.floor(steps / STEPS_PER_FRAME), teleports, counts: Object.assign({}, cnt), sub: Object.assign({}, sub), e,
                Eref: rr(Eref), maxDepth: st.maxDepth, transientDeep: st.transientDeep, pass: CHECKS.every(k => cnt[k] === 0), examples }
        },
    }
}

// ---------------- scenes ----------------
function loadLevels()
{
    const src = fs.readFileSync(path.join(h.ROOT, 'js', 'levels.js'), 'utf8')
    function Line(a, b, c, d) { this.posX = a; this.posY = b; this.posX2 = c; this.posY2 = d }
    return new Function('Line', 'GAME_W', 'GAME_H', 'dotRadius', 'levelLineColor', src + '\nreturn levels')(Line, 1280, 800, 5, '#000')
}
const lineArr = (l) => [l.posX, l.posY, l.posX2, l.posY2]
// rimtrap.py / embed.py repro geometry
const RIM_REPRO_LINES = [[40, 400, 295, 750], [295, 750, 980, 240]]
const EMBED_REPRO_XS = [480, 482]
const B_PORTAL_GEOM = { x: 80, y: 400, angle: 0, h: 45, name: 'B' }

// sim.py wall_line / wcfg: each portal cut into its own 300 px host line at u = 0.5 (side -1 gives n)
function wcfg(ball, portals, extra)
{
    const L = 300
    const lines = portals.map(P => { const tx = -Math.sin(P.angle), ty = Math.cos(P.angle); return [P.x - L / 2 * tx, P.y - L / 2 * ty, P.x + L / 2 * tx, P.y + L / 2 * ty] })
    return { wall: true, ball, lines: lines.concat(extra || []), portals: portals.map((P, i) => ({ line: i, u: 0.5, side: -1, h: P.h, name: P.name })) }
}

function levelScenes(frames)
{
    const out = []
    const levels = loadLevels().filter(l => l.portals && l.portals.length >= 2)
    for (const lv of levels)
    {
        const lines = lv.lines.map(lineArr)
        const cfg0 = { wall: true, lines, portals: lv.portals, ball: { x: lv.ballX, y: lv.ballY, vx: 0, vy: 0, r: R } }
        const W = h.makePortalWorld(cfg0), P = portalsOf(W), solid = solidGeometry(lines, P)
        P.forEach((p, k) =>
        {
            for (const half of [-1, 1])
                for (const sp of LEVEL_SPEEDS)
                    for (const ang of LEVEL_ANGLES)
                    {
                        const s = half * p.h / 2, t = ang * Math.PI / 180
                        const cx = p.x + s * p.tx + R * p.nx, cy = p.y + s * p.ty + R * p.ny
                        const dx = -Math.cos(t) * p.nx + Math.sin(t) * p.tx, dy = -Math.cos(t) * p.ny + Math.sin(t) * p.ty
                        const v = sp / STEPS_PER_FRAME
                        const ball = { x: cx - GAP * dx, y: cy - GAP * dy, vx: v * dx, vy: v * dy, r: R }
                        const clear = h.distToSegments(ball.x, ball.y, solid)
                        out.push({ id: `src${lv.srcId}_${p.name}_${half < 0 ? 'lo' : 'hi'}_v${sp}_a${ang}`, group: 'levels', srcId: lv.srcId,
                            cfg: { wall: true, lines, portals: lv.portals, ball }, frames, spawnClear: +clear.toFixed(4) })
                    }
        })
    }
    return out
}

function reproScenes()
{
    const levels = loadLevels(), bySrc = (n) => levels.find(l => l.srcId === n)
    const out = []
    const l19 = bySrc(19), l24 = bySrc(24)
    out.push({ id: 'rimtrap_level19_repro', group: 'repro', frames: 900,
        cfg: { wall: true, lines: l19.lines.map(lineArr).concat(RIM_REPRO_LINES), portals: l19.portals, ball: { x: l19.ballX, y: l19.ballY, vx: 0, vy: 0, r: R } } })
    const plain = [[300, 400, 700, 400]], floorDown = { x: 500, y: 400, angle: Math.PI / 2, h: 45, name: 'A' }
    out.push({ id: 'rimtrap_ctl_restingPlainLine', group: 'repro', frames: 600, cfg: { wall: true, lines: plain, portals: [], ball: { x: 500, y: 400 - R, vx: 0, vy: 0, r: R } } })
    out.push({ id: 'rimtrap_ctl_restingBackOfPortal', group: 'repro', frames: 600, cfg: wcfg({ x: 500, y: 400 - R, vx: 0, vy: 0, r: R }, [floorDown, B_PORTAL_GEOM]) })
    out.push({ id: 'rimtrap_ctl_rollingPlainLine', group: 'repro', frames: 600, cfg: { wall: true, lines: plain, portals: [], ball: { x: 320, y: 400 - R, vx: 5 / STEPS_PER_FRAME, vy: 0, r: R } } })
    for (const x of EMBED_REPRO_XS)
        out.push({ id: `embed_level24_repro_x${x}`, group: 'repro', frames: 200,
            cfg: { wall: true, lines: l24.lines.map(lineArr), portals: l24.portals, ball: { x, y: 700, vx: 0, vy: 0.02, r: R } } })
    return out
}

function fuzzScenes(frames)
{
    const seeds = arg('--seeds', '1,2'), per = arg('--per-mode', '100')
    const data = JSON.parse(execFileSync('python3', [path.join(h.ROOT, 'tests', 'physics', 'portal_fast_scenes.py'), '--seeds', seeds, '--per-mode', per],
        { maxBuffer: 1 << 30, encoding: 'utf8' }))
    return data.scenes.map(s => ({ id: s.id, group: 'fuzz', mode: s.mode, seed: s.seed, cfg: s.cfg, frames }))
}

// ---------------- runner ----------------
export function runScene(sc)
{
    const W = h.makePortalWorld(sc.cfg)
    const P = portalsOf(W), solid = solidGeometry(sc.cfg.lines, P)
    const b = W.ball()
    const idx = {}
    P.forEach((p, i) => { idx[p.name] = i })
    const chk = makeChecker({ solid, portals: P }, b.posX, b.posY, b.speedX, b.speedY)
    const n = sc.frames * STEPS_PER_FRAME
    let offMap = false, blocked = 0
    for (let s = 0; s < n; ++s)
    {
        const st = W.state(), nt = st.teleports.length
        const x0 = b.posX, y0 = b.posY, vx0 = b.speedX, vy0 = b.speedY
        W.gamePhysics()
        const st1 = W.state()
        let tele = null
        if (st1.teleports.length > nt)
        {
            const rec = st1.teleports[st1.teleports.length - 1]
            tele = { to: idx[rec.to], vb: [rec.before[2], rec.before[3]] }
        }
        chk.step(x0, y0, vx0, vy0, b.posX, b.posY, b.speedX, b.speedY, tele)
        if (!b.onMap()) { offMap = true; break }
    }
    const res = chk.result()
    const st = W.state()
    res.offMap = offMap
    res.blockedExits = st.blockedExits
    res.rimHits = st.rimHits
    res.end = [b.posX, b.posY].map(rr)
    return res
}

function allScenes()
{
    const frames = +arg('--frames', 300)
    const only = arg('--only', null)
    let S = []
    if (!only || only === 'levels') S = S.concat(levelScenes(frames))
    if (!only || only === 'repro') S = S.concat(reproScenes())
    if (!only || only === 'fuzz') S = S.concat(fuzzScenes(frames))
    return S
}

function shard(spec)
{
    const [k, m] = spec.split('/').map(Number)
    const S = JSON.parse(fs.readFileSync(arg('--scenes-file'), 'utf8'))
    const out = []
    for (let i = k; i < S.length; i += m)
    {
        const sc = S[i], res = runScene(sc)
        const o = Object.assign({ id: sc.id, group: sc.group, order: i }, sc.mode ? { mode: sc.mode } : {}, sc.srcId ? { srcId: sc.srcId } : {},
            sc.spawnClear !== undefined ? { spawnClear: sc.spawnClear } : {}, res)
        if (!res.pass) { o.cfg = sc.cfg; o.framesRun = sc.frames }
        out.push(o)
    }
    process.stdout.write(JSON.stringify(out))
}

function runChild(spec, file)
{
    return new Promise((resolve, reject) =>
    {
        const p = spawn(process.execPath, [SELF, '--shard', spec, '--scenes-file', file], { stdio: ['ignore', 'pipe', 'inherit'] })
        let buf = ''
        p.stdout.on('data', d => { buf += d })
        p.on('close', code => code === 0 ? resolve(JSON.parse(buf)) : reject(new Error(`shard ${spec} exited ${code}`)))
    })
}

function commit()
{
    try { return execSync('git rev-parse --short HEAD', { cwd: h.ROOT }).toString().trim() } catch (e) { return null }
}
function codeDirty()
{
    try { return execSync('git status --porcelain js/ index.html', { cwd: h.ROOT }).toString().trim() !== '' } catch (e) { return null }
}
const params = () => ({ R, g: G, H, stepsPerFrame: STEPS_PER_FRAME, embedDistPx: EMBED_DIST, embedSteps: EMBED_STEPS, stepRel: STEP_REL, teleRel: TELE_REL,
    trapMarginPx: TRAP_MARGIN, trapMinSpeedPxPerFrame: TRAP_MIN_SPEED, exitFrames: EXIT_FRAMES, trapFrames: TRAP_FRAMES,
    levelSpeedsPxPerFrame: LEVEL_SPEEDS, levelAnglesDeg: LEVEL_ANGLES, levelGapPx: GAP })

function totals(list)
{
    const t = { scenes: list.length, failing: 0, steps: 0, teleports: 0, offMap: 0, blockedExits: 0, rimHits: 0,
        counts: { a: 0, b: 0, c: 0, d: 0, e: 0 }, scenesFailing: { a: 0, b: 0, c: 0, d: 0, e: 0 },
        sub: { aShallow: 0, bExit: 0, bRim240: 0, linger: 0, dLoss: 0, dGain: 0, captureDeep: 0, eaAfterExit: 0 }, e: { a: 0, b: 0, c: 0, d: 0 }, maxDepth: 0 }
    for (const s of list)
    {
        t.steps += s.steps; t.teleports += s.teleports; t.blockedExits += s.blockedExits; t.rimHits += s.rimHits
        if (s.offMap) ++t.offMap
        if (!s.pass) ++t.failing
        if (s.maxDepth > t.maxDepth) t.maxDepth = s.maxDepth
        for (const k of CHECKS) { t.counts[k] += s.counts[k]; if (s.counts[k]) ++t.scenesFailing[k] }
        for (const k in t.sub) t.sub[k] += s.sub[k]
        for (const k in t.e) t.e[k] += s.e[k]
    }
    return t
}

async function main()
{
    const t0 = Date.now()
    const S = allScenes()
    const tGen = (Date.now() - t0) / 1000
    const file = path.join(fs.mkdtempSync('/tmp/portal_fast_'), 'scenes.json')
    fs.writeFileSync(file, JSON.stringify(S))
    const J = +arg('--jobs', 8)
    const specs = []
    for (let k = 0; k < J; ++k) specs.push(`${k}/${J}`)
    const parts = await Promise.all(specs.map(sp => runChild(sp, file)))
    fs.rmSync ? fs.rmSync(path.dirname(file), { recursive: true }) : (fs.unlinkSync(file), fs.rmdirSync(path.dirname(file)))
    const all = [].concat(...parts).sort((a, b) => a.order - b.order)
    all.forEach(s => delete s.order)
    const groups = {}
    for (const g of ['levels', 'repro', 'fuzz'])
    {
        const l = all.filter(s => s.group === g)
        if (l.length) groups[g] = totals(l)
    }
    const fuzzModes = {}
    for (const m of ['default', 'crossing', 'backside', 'touching'])
    {
        const l = all.filter(s => s.group === 'fuzz' && s.mode === m)
        if (l.length) fuzzModes[m] = totals(l)
    }
    const perLevel = {}
    for (const s of all.filter(s => s.group === 'levels'))
    {
        const p = perLevel[s.srcId] = perLevel[s.srcId] || { scenes: 0, failing: 0, a: 0, b: 0, c: 0, d: 0, e: 0, teleports: 0 }
        ++p.scenes; if (!s.pass) ++p.failing; p.teleports += s.teleports
        for (const k of CHECKS) p[k] += s.counts[k]
    }
    const failing = all.filter(s => !s.pass)
    const exit = failing.length ? 1 : 0
    const report = {
        mode: 'suite', task: 'TASK-269', commit: commit(), codeDirty: codeDirty(), params: params(),
        fuzzParams: { seeds: arg('--seeds', '1,2'), perMode: +arg('--per-mode', 100), frames: +arg('--frames', 300) },
        jobs: J, sceneGenSeconds: tGen, wallSeconds: (Date.now() - t0) / 1000, exit,
        total: totals(all), groups, fuzzModes, perLevel,
        failingIds: failing.map(s => s.id),
        scenes: all.map(s => s.pass ? { id: s.id, pass: true, teleports: s.teleports, steps: s.steps, sub: s.sub } : s),
    }
    const outFile = arg('--out', null)
    if (outFile) fs.writeFileSync(outFile, JSON.stringify(report) + '\n')
    const fmt = (t) => `${t.scenes} scenes, ${t.failing} failing, teleports ${t.teleports}, a ${t.counts.a} b ${t.counts.b} c ${t.counts.c} d ${t.counts.d} (loss ${t.sub.dLoss} gain ${t.sub.dGain}) e ${t.counts.e} [e.a ${t.e.a} e.b ${t.e.b} e.c ${t.e.c} e.d ${t.e.d}]; scenes failing a/b/c/d/e ${CHECKS.map(k => t.scenesFailing[k]).join('/')}`
    for (const g in groups) console.log(`${g}: ${fmt(groups[g])}`)
    for (const m in fuzzModes) console.log(`  fuzz ${m}: ${fmt(fuzzModes[m])}`)
    for (const s of all.filter(s => s.group === 'repro')) console.log(`  ${s.pass ? 'PASS' : 'FAIL'} ${s.id} teleports ${s.teleports} counts ${JSON.stringify(s.counts)}`)
    console.log(`total: ${fmt(report.total)}`)
    console.log(`wall ${report.wallSeconds}s`)
    console.log(exit ? `PORTAL_FAST FAIL: ${failing.length} scenes` : 'PORTAL_FAST PASS')
    process.exit(exit)
}

// ---------------- selftest ----------------
// Geometry: rimtrap.py's pair, A a floor portal facing up at (500, 400), B a wall portal facing right at (80, 400),
// h 45, host lines 300 px (sim.py wcfg). Each trace is exact free flight (vy += g, then x += v; E is exact for it)
// with one event:
//   clean:      falls from (800, 200), teleports to B's front (92, 400) (speed kept, pointing +x), flies on -> none
//   embedAfter: the teleport puts the centre 0.2 px in front of B's host piece below the opening (80.2, 460), the
//               next step jumps 9.5 px away along +x (no 2-state overlap for e.a) -> a only
//   rimTrap:    teleports out of A at (545, 388) and then shuttles along A's tangent between x 535 and 555 at
//               2 px/frame, y fixed (E constant), for 100 frames -> b only
//   speedChange: as clean, but the teleport's exit speed is 1 % higher than before portalStep -> c only
//   energyLoss: as clean, but one free step loses 1 % of the speed -> d only
//   stuckDeep:  rolls on A's host piece (x from 360, y 390) and is 2 px deep for 10 steps (speed raised so E is
//               exact), then rolls on -> e only (e.a)
//   captureSink: the same sink, but the run ends in a teleport to B's front -> none (captureDeep, the generous edge)
function selftest()
{
    const ball = { x: 800, y: 200, vx: 0, vy: 0, r: R }
    const cfg = wcfg(ball, [{ x: 500, y: 400, angle: -Math.PI / 2, h: 45, name: 'A' }, B_PORTAL_GEOM])
    const W = h.makePortalWorld(cfg), P = portalsOf(W), geo = { solid: solidGeometry(cfg.lines, P), portals: P }
    const N = 100 * STEPS_PER_FRAME, TP = 20 * STEPS_PER_FRAME
    function trace(kind)
    {
        const out = []
        let x = 800, y = 200, vx = 0.002, vy = 0
        if (kind === 'rimTrap') { x = 545; y = 388; vx = 0.004 }
        if (kind === 'stuckDeep' || kind === 'captureSink') { x = 360; y = 390 }
        for (let s = 0; s < N; ++s)
        {
            const x0 = x, y0 = y, vx0 = vx, vy0 = vy
            let tele = null
            if (kind === 'stuckDeep' || kind === 'captureSink')
            {
                // rolling on A's host piece left of the opening (y 390 = touching), 2 px deep for steps 1000..1009 with
                // the speed raised so that E stays exact; captureSink is teleported to B's front right after the sink
                if (kind === 'captureSink' && s === 1010) { tele = { to: 1, vb: [vx, vy] }; x = 92; y = 400 }
                else if (kind === 'captureSink' && s > 1010) x += vx
                else
                {
                    const deep = s >= 1000 && s < 1010
                    vx = deep ? Math.sqrt(0.002 * 0.002 + 2 * G * 2) : 0.002
                    y = deep ? 392 : 390
                    x += vx
                }
            }
            else if (kind === 'rimTrap')
            {
                if (s === 0) tele = { to: 0, vb: [vx, vy] }
                if ((x >= 555 && vx > 0) || (x <= 535 && vx < 0)) vx = -vx
                x += vx
            }
            else if (s === TP)
            {
                const sp = Math.hypot(vx, vy)
                tele = { to: 1, vb: [vx, vy] }
                if (kind === 'embedAfter') { x = 80.2; y = 460; vx = 9.5; vy = 0 }
                else { x = 92; y = 400; vx = kind === 'speedChange' ? sp * 1.01 : sp; vy = 0 }
                if (kind === 'embedAfter') tele.vb = [9.5, 0]
            }
            else
            {
                vy += G
                if (kind === 'energyLoss' && s === TP + 1000) { vx *= 0.99; vy *= 0.99 }
                x += vx; y += vy
            }
            out.push([x0, y0, vx0, vy0, x, y, vx, vy, tele])
        }
        return out
    }
    const cases = []
    for (const [kind, expect] of [['clean', null], ['embedAfter', 'a'], ['rimTrap', 'b'], ['speedChange', 'c'], ['energyLoss', 'd'],
        ['stuckDeep', 'e'], ['captureSink', null]])
    {
        const tr = trace(kind)
        const c = makeChecker(geo, tr[0][0], tr[0][1], tr[0][2], tr[0][3])
        tr.forEach(t => c.step(...t))
        const r = c.result()
        const fired = CHECKS.filter(k => r.counts[k] > 0)
        const pass = expect === null ? fired.length === 0 : (fired.length === 1 && fired[0] === expect)
        const extra = kind === 'captureSink' ? r.sub.captureDeep > 0 : kind === 'stuckDeep' ? r.e.a > 0 : true
        cases.push({ name: `synthetic_${kind}`, expect: expect || 'none', fired, counts: r.counts, sub: r.sub, e: r.e, teleports: r.teleports, pass: pass && extra, examples: r.examples })
    }
    {
        // a real run: B's front, ball thrown into A at 10 px/frame, must teleport and pass every check
        const sc = { id: 'real_teleport', frames: 120, cfg: wcfg({ x: 500, y: 300, vx: 0, vy: 0.02, r: R }, [{ x: 500, y: 400, angle: -Math.PI / 2, h: 45, name: 'A' }, B_PORTAL_GEOM]) }
        const r = runScene(sc)
        const fired = CHECKS.filter(k => r.counts[k] > 0)
        cases.push({ name: 'real_teleport', expect: 'none (>= 1 teleport)', fired, counts: r.counts, sub: r.sub, teleports: r.teleports, pass: r.teleports >= 1 && fired.length === 0, examples: r.examples })
    }
    const pass = cases.every(c => c.pass)
    for (const c of cases) console.log(`${c.pass ? 'PASS' : 'FAIL'} ${c.name} expect ${c.expect} fired [${c.fired.join(',')}] counts ${JSON.stringify(c.counts)} teleports ${c.teleports}`)
    console.log(pass ? 'SELFTEST PASS' : 'SELFTEST FAIL')
    const report = { mode: 'selftest', task: 'TASK-269', commit: commit(), codeDirty: codeDirty(), pass, params: params(), cases }
    const outFile = arg('--out', null)
    if (outFile) fs.writeFileSync(outFile, JSON.stringify(report) + '\n')
    process.exit(pass ? 0 : 1)
}

const isMain = process.argv[1] && fs.realpathSync(process.argv[1]) === fs.realpathSync(SELF)
if (!isMain) { /* imported */ }
else if (has('--shard')) shard(arg('--shard'))
else if (has('--selftest')) selftest()
else main().catch(e => { console.error(e); process.exit(2) })
