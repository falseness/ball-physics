// Ball physics invariant checker CLI (TASK-198). The checks live in tests/physics/invariants_core.js
// (I1 no stuck / livelock, I2 plausible velocity, I3 energy, T teleport speed; see its header).
//
//   node tests/physics/invariants.mjs --selftest [--out FILE]
//       synthetic traces (clean, stuck, livelock, tangential kick, free-flight kick, moving-away flip,
//       energy gain, teleport speed change): each invariant must fire on its own trace only, and stay
//       silent on the clean traces; plus loader parity (fast loader == TASK-197 vm loader, bit for bit).
//   node tests/physics/invariants.mjs [--fuzz A-B] [--levels] [--scenes N] [--frames F] [--level-frames F] [--out FILE]
//       --fuzz A-B: seeds A..B, N scenes each (default 2000), each a random 1-4 line scene with a ball drop,
//       F frames (default 600) of 500 steps, real js/ball.js, every step checked; a scene ends early only
//       when the ball leaves the map (the game restarts the level there). Seeds run as parallel child
//       processes (--shard SEED internally).
//       --chains A-B: seeds A..B, N scenes each, each a random chain of 2-5 connected segments (shared end
//       points; convex and concave joints, segments in random order and direction, a quarter with the joint
//       end points up to 1 px apart, i.e. within dotRadius) and a ball dropped onto it from above or below.
//       --levels: every shoot levelNN reference solution inside the game (tests/physics/invariants_browser.py).
//   node tests/physics/invariants.mjs --browser --portal-fuzz A-B [--portal-cases N] [--portal-frames F] [--out FILE]
//       TASK-201: portal fuzz scenes inside the game (Playwright, tests/physics/invariants_browser.py
//       --portal-fuzz SEED, one child process per seed in parallel): N scenes per seed (default 2000) from the
//       tests/portal/fuzz.py generators in turn (default, --crossing, --backside, --touching), F frames
//       (default 300) of 500 steps, every step checked; teleport steps by the T rule (speed preserved), rim
//       bounces and refused teleports as contacts with their normals. --browser is required (it runs the game).
//   Output: compact JSON (counts per invariant, sub-counts, first 5 examples each, per seed / per level).
//   Exit 1 when any violation is found (or a selftest check fails), 0 otherwise.
// Node 12: no ?? / ?. syntax.
import fs from 'node:fs'
import path from 'node:path'
import { spawn, execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import * as h from './harness.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const Core = new Function(fs.readFileSync(path.join(HERE, 'invariants_core.js'), 'utf8') + '\nreturn InvariantsCore')()
const { R, G, STEPS_PER_FRAME } = h

function arg(name, def)
{
    const i = process.argv.indexOf(name)
    return i < 0 ? def : process.argv[i + 1]
}
const has = (name) => process.argv.includes(name)

// mulberry32
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

// A random scene: 1-4 lines (length 30-600 px, any angle, inside x 60..1220, y 120..760), and a ball drop
// aimed at a random point of a random line (x within +-20 px of it, 20-300 px above it, vx 0 or
// +-0.01 px/step) that starts clear of every line (distance >= R + 1).
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

// A random chain scene (TASK-200): 2-5 segments joined end to end (30-300 px each), the first heading within
// +-60 deg of horizontal, every joint turning the same way (convex seen from one side, concave from the other)
// by 3-120 deg, or in a random direction per joint (zigzag) in a third of the chains. The segments are shuffled
// and randomly reversed (the contact model must not depend on line order or direction). In a quarter of the
// chains each joint's second end point is moved by up to 1 px (joined within dotRadius, not exactly). The ball
// is dropped from above or below a random point of a random segment like makeScene, clear of every line.
function makeChainScene(rand)
{
    const n = 2 + Math.floor(rand() * 4), zig = rand() < 1 / 3, sign = rand() < 0.5 ? -1 : 1, jitter = rand() < 0.25
    const rnd = (v) => Math.round(v * 100) / 100
    for (let tries = 0; ; ++tries)
    {
        let x = 120 + rand() * 1040, y = 200 + rand() * 480, a = (rand() * 2 - 1) * Math.PI / 3
        if (rand() < 0.5) a += Math.PI
        const pts = [[rnd(x), rnd(y)]]
        let ok = true
        for (let i = 0; i < n; ++i)
        {
            if (i > 0) a += (zig ? (rand() < 0.5 ? -1 : 1) : sign) * (3 + rand() * 117) * Math.PI / 180
            const L = 30 + rand() * 270
            x += L * Math.cos(a); y += L * Math.sin(a)
            if (x < 60 || x > 1220 || y < 120 || y > 760) { ok = false; break }
            pts.push([rnd(x), rnd(y)])
        }
        if (!ok) { if (tries > 1000) return makeChainScene(rand); continue }
        let segs = []
        for (let i = 0; i < n; ++i)
        {
            const p = pts[i].slice()
            if (jitter && i > 0) { p[0] = rnd(p[0] + rand() * 2 - 1); p[1] = rnd(p[1] + rand() * 2 - 1) }
            segs.push(rand() < 0.5 ? [p[0], p[1], pts[i + 1][0], pts[i + 1][1]] : [pts[i + 1][0], pts[i + 1][1], p[0], p[1]])
        }
        for (let i = segs.length - 1; i > 0; --i) { const j = Math.floor(rand() * (i + 1)), t = segs[i]; segs[i] = segs[j]; segs[j] = t }
        // a near-degenerate zigzag (a later segment crossing an earlier one) is fine: still a valid level geometry
        for (let k = 0; k < 1000; ++k)
        {
            const s = segs[Math.floor(rand() * segs.length)], t = rand(), up = rand() < 0.75
            const bx = s[0] + t * (s[2] - s[0]) + (rand() * 40 - 20), by = s[1] + t * (s[3] - s[1]) + (up ? -1 : 1) * (20 + rand() * 280)
            const vx = rand() < 0.5 ? 0 : (rand() < 0.5 ? -0.01 : 0.01)
            if (by > R && by < 800 - R && bx > R && bx < 1280 - R && h.distToSegments(bx, by, segs) >= R + 1)
                return { segs, ball: [rnd(bx), rnd(by), vx, 0], chain: { n, zig, sign, jitter } }
        }
    }
}

function runScene(scene, frames, label, makeWorld)
{
    const w = (makeWorld || h.makeFastWorld)(scene.segs)
    const b = w.ball(scene.ball[0], scene.ball[1], scene.ball[2], scene.ball[3])
    const chk = Core.makeChecker({ g: G, r: R, segs: scene.segs, label })
    const total = frames * STEPS_PER_FRAME
    let s = 0, offMap = false
    for (; s < total; ++s)
    {
        const x0 = b.posX, y0 = b.posY, vx0 = b.speedX, vy0 = b.speedY
        b.physics(); b.move()
        chk.step(x0, y0, vx0, vy0, b.posX, b.posY, b.speedX, b.speedY, false)
        if (!b.onMap()) { offMap = true; ++s; break }
    }
    const res = chk.result()
    res.offMap = offMap
    return res
}

function shard(seed, scenes, frames, kind)
{
    const rand = rng(kind === 'chains' ? 0x5EED0000 + seed : seed), results = [], perScene = []
    const gen = kind === 'chains' ? makeChainScene : makeScene
    let offMap = 0
    const t0 = Date.now()
    for (let i = 0; i < scenes; ++i)
    {
        const sc = gen(rand), label = (kind === 'chains' ? 'c' : 's') + seed + '#' + i
        const res = runScene(sc, frames, label)
        if (res.offMap) ++offMap
        const tot = res.counts.I1 + res.counts.I2 + res.counts.I3 + res.counts.T
        if (tot) perScene.push([i, res.counts.I1, res.counts.I2, res.counts.I3])
        // the scene definition goes with its examples so any example can be replayed
        Core.KINDS.forEach(k => res.examples[k].forEach(e => { e.lines = sc.segs; e.ball0 = sc.ball }))
        results.push(res)
    }
    const m = Core.merge(results)
    return { seed, kind: kind || 'fuzz', scenes, frames, scenesOffMap: offMap, scenesWithViolations: perScene.length,
        seconds: (Date.now() - t0) / 1000, ...m, violatingScenes: perScene.slice(0, 50) }
}

function runShards(seeds, scenes, frames, kind)
{
    return Promise.all(seeds.map(seed => new Promise((resolve, reject) =>
    {
        const p = spawn(process.execPath, [fileURLToPath(import.meta.url), '--shard', String(seed), '--scenes', String(scenes),
            '--frames', String(frames), '--kind', kind || 'fuzz'], { stdio: ['ignore', 'pipe', 'inherit'] })
        let out = ''
        p.stdout.on('data', d => { out += d })
        p.on('close', code => code === 0 ? resolve(JSON.parse(out)) : reject(new Error('shard ' + seed + ' exit ' + code)))
    })))
}

function runPortalFuzz(seeds, cases, frames)
{
    return Promise.all(seeds.map(seed => new Promise((resolve, reject) =>
    {
        const p = spawn('python3', [path.join(HERE, 'invariants_browser.py'), '--portal-fuzz', String(seed), '--cases', String(cases),
            '--frames', String(frames)], { stdio: ['ignore', 'pipe', 'inherit'] })
        let out = ''
        p.stdout.on('data', d => { out += d })
        p.on('close', code =>
        {
            if (code !== 0) return reject(new Error('portal fuzz seed ' + seed + ' exit ' + code))
            const r = JSON.parse(out), perScene = [], kinds = {}
            r.scenes.forEach(sc =>
            {
                const k = kinds[sc.kind] = kinds[sc.kind] || { scenes: 0, teleports: 0, blockedExits: 0, hostHits: 0, offMap: 0 }
                ++k.scenes; k.teleports += sc.teleports; k.blockedExits += sc.blockedExits; k.hostHits += sc.hostHits; k.offMap += sc.offMap ? 1 : 0
                const tot = sc.counts.I1 + sc.counts.I2 + sc.counts.I3 + sc.counts.T
                if (tot) perScene.push([sc.scene, sc.kind, sc.counts.I1, sc.counts.I2, sc.counts.I3, sc.counts.T])
            })
            resolve({ seed, scenes: r.scenes.length, frames: r.frames, kinds, scenesWithViolations: perScene.length,
                pageErrors: r.pageErrors, seconds: r.seconds, ...Core.merge(r.scenes), violatingScenes: perScene.slice(0, 50) })
        })
    })))
}

function runLevels(levelFrames)
{
    const args = [path.join(HERE, 'invariants_browser.py')]
    if (levelFrames) args.push('--frames', String(levelFrames))
    return new Promise((resolve, reject) =>
    {
        const p = spawn('python3', args, { stdio: ['ignore', 'pipe', 'inherit'] })
        let out = ''
        p.stdout.on('data', d => { out += d })
        p.on('close', code => code === 0 ? resolve(JSON.parse(out)) : reject(new Error('browser mode exit ' + code)))
    })
}

// ---------------- selftest ----------------
// Each trace is a list of steps [x0, y0, vx0, vy0, x1, y1, vx1, vy1, tele, vmx, vmy] over a fixed geometry.
// Reference engine for the clean trace: reflect about the closest-point normal only when moving in,
// push out to the radius, then gravity, then move.
function refTrace(segs, x, y, vx, vy, n)
{
    const out = []
    for (let s = 0; s < n; ++s)
    {
        const x0 = x, y0 = y, vx0 = vx, vy0 = vy
        let best = null
        for (const seg of segs)
        {
            const c = Core.closest(x, y, seg)
            if (c[2] < R && c[2] > 0 && (!best || c[2] < best[2])) best = c
        }
        if (best)
        {
            const nx = (x - best[0]) / best[2], ny = (y - best[1]) / best[2], vn = vx * nx + vy * ny
            if (vn < 0) { vx -= 2 * vn * nx; vy -= 2 * vn * ny }
        }
        vy += G
        x += vx; y += vy
        out.push([x0, y0, vx0, vy0, x, y, vx, vy, false])
    }
    return out
}

function selftest()
{
    const floor = [[100, 400, 900, 400]]
    const slope = [[100, 200, 700, 500]]
    const cases = []
    const run = (name, segs, trace, expect, opts) =>
    {
        const chk = Core.makeChecker(Object.assign({ g: G, r: R, segs }, opts || {}))
        trace.forEach(t => chk.step.apply(null, t))
        const res = chk.result()
        const fired = Core.KINDS.filter(k => res.counts[k] > 0)
        const pass = expect === null ? fired.length === 0 : (fired.length === 1 && fired[0] === expect)
        cases.push({ name, expect: expect || 'none', steps: res.steps, contactSteps: res.contactSteps, counts: res.counts, sub: res.sub,
            fired, pass, example: expect ? res.examples[expect][0] : null })
    }
    // clean: drop onto a floor, several bounces (reference engine), 30000 steps
    run('clean_floor_bounces', floor, refTrace(floor, 500, 300, 0.003, 0, 30000), null)
    // clean: drop onto a 26.6 deg slope and roll / bounce down it, 30000 steps
    run('clean_slope_roll', slope, refTrace(slope, 200, 230, 0, 0, 30000), null)
    // clean: a free step, then a teleport that turns the velocity by 2.1 rad and keeps the speed exactly
    {
        const v0 = [0.012, 0.016], v1 = [v0[0], v0[1] + G], a = 2.1, c = Math.cos(a), sn = Math.sin(a)
        const vr = [v1[0] * c - v1[1] * sn, v1[0] * sn + v1[1] * c]
        run('clean_teleport', [], [[300, 100, v0[0], v0[1], 300 + v1[0], 100 + v1[1], v1[0], v1[1], false],
            [300 + v1[0], 100 + v1[1], v1[0], v1[1], 800, 200, vr[0], vr[1], true, v1[0], v1[1]]], null)
    }
    // I1 stuck: centre 2 px inside the floor, sliding at 0.01 px/step, gravity absorbed by the line (10 steps)
    {
        const t = [], y = 400 - R + 2
        for (let s = 0; s < 10; ++s) t.push([300 + 0.01 * s, y, 0.01, 0, 300 + 0.01 * (s + 1), y, 0.01, 0, false])
        run('stuck_inside_line', floor, t, 'I1')
    }
    // I1 livelock: a slot of two lines 2R - 0.2 apart, the ball bounces between them every step at 0.01 px/step
    {
        const slot = [[100, 400, 900, 400], [100, 400 - 2 * R + 0.2, 900, 400 - 2 * R + 0.2]]
        const t = []
        let y = 400 - R + 0.1 - 0.005, vy = 0.01
        for (let s = 0; s < 300; ++s)
        {
            const vy1 = -vy
            t.push([500, y, 0, vy, 500, y + vy1, 0, vy1, false])
            y += vy1; vy = vy1
        }
        run('livelock_slot', slot, t, 'I1')
    }
    // I2 tangential kick: rolling on the floor, one contact step slows vx by 1e-5 (energy goes down)
    {
        const y = 400 - R + 0.001, vx = 0.01
        const t = [[300, y, vx, 0.0001, 300 + vx - 1e-5, y - 0.0001, vx - 1e-5, -0.0001, false]]
        run('tangential_kick', floor, t, 'I2')
    }
    // I2 free-flight kick: no contact, vx changes by 1e-12
    run('free_flight_kick', floor, [[500, 100, 0.01, 0, 500.01, 100 + G, 0.01 + 1e-12, G, false]], 'I2')
    // I2 moving away flipped (the end-point flip of js/ball.js): 9 px from the end of the floor, moving away
    run('moving_away_flipped', floor, [[100 - 9, 400, -0.01, 0, 100 - 9 + 0.01, 400 + G, 0.01, G, false]], 'I2')
    // I3 energy gain: a floor bounce that leaves faster than it came, by g (allowed by I2's vn_grow, caught by I3)
    {
        const y = 400 - R + 0.005, vy = 0.01, vy1 = -(vy + G)
        run('energy_gain_bounce', floor, [[500, y, 0, vy, 500, y + vy1, 0, vy1, false]], 'I3')
    }
    // T: a teleport whose speed grows by 1e-6 relative
    {
        const v = [0.012, 0.016], k = 1 + 1e-6
        run('teleport_speed_change', [], [[300, 100, v[0], v[1] - G, 800, 200, -v[1] * k, v[0] * k, true, v[0], v[1]]], 'T')
    }
    // loader parity: the fast loader steps exactly like the TASK-197 vm loader
    const parity = []
    const rand = rng(12345)
    for (let i = 0; i < 4; ++i)
    {
        const sc = i === 0 ? { segs: [[100, 200, 400, 300], [400, 300, 700, 300]], ball: [150, 150, 0, 0] } : makeScene(rand)
        const a = h.makeWorld(sc.segs), b = h.makeFastWorld(sc.segs)
        const ba = a.ball(...sc.ball), bb = b.ball(...sc.ball)
        let same = true, s = 0
        for (; s < 20000 && same; ++s)
        {
            a.step(ba); b.step(bb)
            same = ba.posX === bb.posX && ba.posY === bb.posY && ba.speedX === bb.speedX && ba.speedY === bb.speedY
        }
        parity.push({ scene: sc, steps: s, identical: same, end: [ba.posX, ba.posY] })
    }
    const allPass = cases.every(c => c.pass) && parity.every(p => p.identical)
    return { mode: 'selftest', commit: commit(), pass: allPass, params: Core.params, cases, parity }
}

function commit()
{
    try { return execSync('git rev-parse --short HEAD', { cwd: h.ROOT }).toString().trim() } catch (e) { return null }
}

function writeOut(obj)
{
    const s = JSON.stringify(obj)
    const out = arg('--out', null)
    if (out) { fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true }); fs.writeFileSync(out, s + '\n') }
    return s
}

function summary(name, m)
{
    return name + ': steps ' + m.steps + ' contactSteps ' + m.contactSteps + ' I1 ' + m.counts.I1 + ' I2 ' + m.counts.I2 +
        ' I3 ' + m.counts.I3 + ' T ' + m.counts.T
}

async function main()
{
    if (has('--shard'))
    {
        const r = shard(+arg('--shard'), +arg('--scenes', 2000), +arg('--frames', 600), arg('--kind', 'fuzz'))
        process.stdout.write(JSON.stringify(r))
        return 0
    }
    if (has('--selftest'))
    {
        const r = selftest()
        writeOut(r)
        r.cases.forEach(c => console.log((c.pass ? 'PASS ' : 'FAIL ') + c.name + ' expect ' + c.expect + ' fired [' + c.fired.join(',') +
            '] counts ' + JSON.stringify(c.counts)))
        r.parity.forEach((p, i) => console.log((p.identical ? 'PASS ' : 'FAIL ') + 'loader_parity#' + i + ' ' + p.steps + ' steps identical=' + p.identical))
        console.log('SELFTEST ' + (r.pass ? 'PASS' : 'FAIL'))
        return r.pass ? 0 : 1
    }
    const t0 = Date.now()
    const out = { mode: 'check', commit: commit(), params: Core.params, args: process.argv.slice(2) }
    const parts = []
    const fz = arg('--fuzz', null)
    const scenes = +arg('--scenes', 2000), frames = +arg('--frames', 600)
    const jobs = []
    const seedList = (spec) =>
    {
        const [a, b] = spec.split('-').map(Number), seeds = []
        for (let s = a; s <= (b || a); ++s) seeds.push(s)
        return seeds
    }
    if (fz)
        jobs.push(runShards(seedList(fz), scenes, frames, 'fuzz').then(r => { out.fuzz = { scenesPerSeed: scenes, frames, seeds: r, total: Core.merge(r) } }))
    const ch = arg('--chains', null)
    if (ch)
        jobs.push(runShards(seedList(ch), scenes, frames, 'chains').then(r => { out.chains = { scenesPerSeed: scenes, frames, seeds: r, total: Core.merge(r) } }))
    const pf = arg('--portal-fuzz', null)
    if (pf && !has('--browser'))
        throw new Error('--portal-fuzz runs the game: add --browser')
    const pcases = +arg('--portal-cases', 2000), pframes = +arg('--portal-frames', 300)
    if (pf)
        jobs.push(runPortalFuzz(seedList(pf), pcases, pframes).then(r =>
        {
            out.portalFuzz = { scenesPerSeed: pcases, frames: pframes, seeds: r, pageErrors: [].concat(...r.map(x => x.pageErrors)), total: Core.merge(r) }
        }))
    if (has('--levels'))
        jobs.push(runLevels(arg('--level-frames', null)).then(r =>
        {
            out.levels = { list: r.levels, pageErrors: r.pageErrors, total: Core.merge(r.levels) }
        }))
    await Promise.all(jobs)
    if (out.fuzz)
    {
        out.fuzz.seeds.forEach(s => console.log(summary('fuzz seed ' + s.seed + ' (' + s.scenes + ' scenes, ' + s.scenesWithViolations + ' violating)', s)))
        console.log(summary('fuzz total', out.fuzz.total))
        parts.push(out.fuzz.total)
    }
    if (out.chains)
    {
        out.chains.seeds.forEach(s => console.log(summary('chains seed ' + s.seed + ' (' + s.scenes + ' scenes, ' + s.scenesWithViolations + ' violating)', s)))
        console.log(summary('chains total', out.chains.total))
        parts.push(out.chains.total)
    }
    if (out.portalFuzz)
    {
        out.portalFuzz.seeds.forEach(s => console.log(summary('portal fuzz seed ' + s.seed + ' (' + s.scenes + ' scenes, ' + s.scenesWithViolations +
            ' violating, teleports ' + s.teleports + ', kinds ' + JSON.stringify(s.kinds) + ')', s)))
        console.log(summary('portal fuzz total', out.portalFuzz.total) + ' teleports ' + out.portalFuzz.total.teleports + ' pageErrors ' + out.portalFuzz.pageErrors.length)
        parts.push(out.portalFuzz.total)
    }
    if (out.levels)
    {
        out.levels.list.forEach(l => console.log(summary('level' + l.src + ' won=' + l.won + ' teleports=' + l.teleports, l)))
        console.log(summary('levels total', out.levels.total))
        parts.push(out.levels.total)
    }
    out.total = Core.merge(parts)
    out.seconds = (Date.now() - t0) / 1000
    out.violations = out.total.counts.I1 + out.total.counts.I2 + out.total.counts.I3 + out.total.counts.T
    if (out.portalFuzz && out.portalFuzz.pageErrors.length)
        out.violations += out.portalFuzz.pageErrors.length
    writeOut(out)
    console.log(summary('TOTAL', out.total) + ' -> ' + (out.violations ? 'VIOLATIONS ' + out.violations + ' (exit 1)' : 'clean (exit 0)'))
    return out.violations ? 1 : 0
}

main().then(code => process.exit(code), e => { console.error(e); process.exit(2) })
