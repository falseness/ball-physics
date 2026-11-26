// TASK-268: headless portal parity. Runs portal scenes from the tests/portal/fuzz.py generators (default, --crossing,
// --backside, --touching; N each, exported as JSON by tests/physics/invariants_browser.py --parity-export) in node
// (harness makePortalWorld: the real js/ball.js + js/portal.js, index.html's gamePhysics()) and in the browser
// (invariants_browser.py --parity-run: the game page itself), and compares them bit for bit: the ball state
// (x, y, vx, vy) after every frame, every teleport record (step, from, to, kind, s, d, before, after) and the
// portalState counters (steps, rimHits, hostHits, blockedExits).
//
//   node tests/physics/portal_parity.mjs [--out FILE] [--timing FILE] [--seed S] [--per-kind N] [--frames F]
//                                        [--scenes FILE] [--browser FILE] [--node-only] [--math N | --no-math]
//
// --scenes: use this exported scenes file instead of exporting; --browser: reuse a --parity-run output instead of
// running the browser; --node-only: only the node run (timing). Exit 0 when every scene matches, 1 otherwise.
// Before comparing, the comparator is checked on a copy of scene 0's node result with one flipped bit in one frame
// (it must report exactly that frame). --fresh N (default 20): the first N scenes are re-run in fresh harness
// scopes and must give the same bits as the reused scope. Math check (--math N, default 50000 args per range; --no-math skips it): the
// harness's portalMath (glibc sin / cos port) against the page's Math on PortalParity.mathSample's arguments, and
// node's own Math against the page (informational: shows why the port is needed).
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { ROOT, STEPS_PER_FRAME, makePortalWorld, portalMath } from './harness.mjs'

const args = process.argv.slice(2)
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d }
const flag = (k) => args.includes(k)
const OUT = opt('--out', null), TIMING = opt('--timing', null)
const SEED = +opt('--seed', 1), PER_KIND = +opt('--per-kind', 50), FRAMES = +opt('--frames', 300)
const PY = path.join(ROOT, 'tests', 'physics', 'invariants_browser.py')

const core = new Function(fs.readFileSync(path.join(ROOT, 'tests', 'physics', 'portal_parity_core.js'), 'utf8') + '\nreturn PortalParity')()

function exportScenes()
{
    const f = opt('--scenes', null)
    if (f)
        return JSON.parse(fs.readFileSync(f, 'utf8'))
    return JSON.parse(execFileSync('python3', [PY, '--parity-export', String(SEED), '--cases-per-kind', String(PER_KIND)],
        { maxBuffer: 1 << 30, encoding: 'utf8' }))
}

function runNode(scenes)
{
    const t0 = process.hrtime.bigint()
    const res = scenes.map(sc =>
    {
        const W = makePortalWorld(sc.cfg)
        return Object.assign({ id: sc.id }, core.run(W.gamePhysics, W.ball, W.state, FRAMES, STEPS_PER_FRAME))
    })
    return { res, seconds: Number(process.hrtime.bigint() - t0) / 1e9 }
}

// the first n scenes again, each in a fresh harness scope (makePortalWorld fresh: true): must equal the reused-scope bits
function freshCheck(res, scenes, n)
{
    let diff = 0
    for (let i = 0; i < Math.min(n, scenes.length); ++i)
    {
        const W = makePortalWorld(scenes[i].cfg, { fresh: true })
        const r = core.run(W.gamePhysics, W.ball, W.state, FRAMES, STEPS_PER_FRAME)
        if (r.frames !== res[i].frames || r.teleports.join() !== res[i].teleports.join() || r.steps !== res[i].steps ||
            r.rimHits !== res[i].rimHits || r.hostHits !== res[i].hostHits || r.blockedExits !== res[i].blockedExits)
            ++diff
    }
    return { scenes: Math.min(n, scenes.length), differing: diff, ok: diff === 0 }
}

function runBrowser(scenesFile)
{
    const f = opt('--browser', null)
    if (f)
        return { data: JSON.parse(fs.readFileSync(f, 'utf8')), wall: null }
    const t0 = process.hrtime.bigint()
    const data = JSON.parse(execFileSync('python3', [PY, '--parity-run', scenesFile, '--frames', String(FRAMES)],
        { maxBuffer: 1 << 30, encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] }))
    return { data, wall: Number(process.hrtime.bigint() - t0) / 1e9 }
}

const unhex = (h) => { const u = new Uint8Array(h.length / 2); for (let i = 0; i < u.length; ++i) u[i] = parseInt(h.substr(2 * i, 2), 16); return Array.from(new Float64Array(u.buffer)) }

// first differing frame (index) of two hex frame strings, -1 if identical; each frame is 4 doubles = 64 hex chars
function firstFrameDiff(a, b)
{
    if (a === b)
        return -1
    const n = Math.min(a.length, b.length)
    for (let i = 0; i < n; i += 64)
        if (a.substr(i, 64) !== b.substr(i, 64))
            return i / 64
    return n / 64
}

function compare(n, b)
{
    const out = { id: n.id, frameMismatch: 0, firstFrame: -1, teleportsNode: n.teleports.length, teleportsBrowser: b.teleports.length,
                  teleportRecordsEqual: true, countersEqual: true }
    const fd = firstFrameDiff(n.frames, b.frames)
    if (fd >= 0)
    {
        for (let i = 0; i < Math.max(n.frames.length, b.frames.length); i += 64)
            if (n.frames.substr(i, 64) !== b.frames.substr(i, 64))
                ++out.frameMismatch
        out.firstFrame = fd
        const st = (h) => h.length >= 64 * (fd + 1) ? unhex(h.substr(64 * fd, 64)) : null
        out.firstDiff = { frame: fd + 1, node: st(n.frames), browser: st(b.frames) }
    }
    for (let i = 0; i < Math.max(n.teleports.length, b.teleports.length); ++i)
        if (n.teleports[i] !== b.teleports[i])
        {
            out.teleportRecordsEqual = false
            out.firstTeleportDiff = { index: i, node: n.teleports[i] || null, browser: b.teleports[i] || null }
            break
        }
    for (const k of ['steps', 'rimHits', 'hostHits', 'blockedExits'])
        if (n[k] !== b[k])
        {
            out.countersEqual = false
            out[k] = [n[k], b[k]]
        }
    out.ok = out.frameMismatch === 0 && out.teleportsNode === out.teleportsBrowser && out.teleportRecordsEqual && out.countersEqual
    return out
}

function mathCheck(n)
{
    const t0 = process.hrtime.bigint()
    const br = JSON.parse(execFileSync('python3', [PY, '--math-check', String(n)], { maxBuffer: 1 << 30, encoding: 'utf8' }))
    const mine = core.mathSample(portalMath, n), raw = core.mathSample(Math, n)
    const cnt = (a, b) => { let d = 0; for (let i = 0; i < a.length; i += 16) if (a.substr(i, 16) !== b.substr(i, 16)) ++d; return d }
    const out = { argsPerFn: br.n, browserVersion: br.browserVersion, portalMathDiffs: {}, nodeMathDiffs: {} }
    for (const k of ['sin', 'cos', 'atan2', 'hypot', 'pow2', 'sqrt'])
    {
        out.portalMathDiffs[k] = cnt(mine[k], br[k])
        out.nodeMathDiffs[k] = cnt(raw[k], br[k])
    }
    out.ok = mine.n === br.n && Object.values(out.portalMathDiffs).every(v => v === 0)
    out.seconds = +(Number(process.hrtime.bigint() - t0) / 1e9).toFixed(3)
    return out
}

let mathRes = null
if (!flag('--no-math'))
{
    mathRes = mathCheck(+opt('--math', 50000))
    console.error('math check: ' + JSON.stringify(mathRes))
}

const sceneData = exportScenes()
const scenes = sceneData.scenes
console.error(`portal parity: ${scenes.length} scenes x ${FRAMES} frames x ${STEPS_PER_FRAME} steps`)
const node = runNode(scenes)
console.error(`node: ${node.seconds.toFixed(2)} s`)

const fresh = freshCheck(node.res, scenes, +opt('--fresh', 20))
console.error('fresh-scope check: ' + JSON.stringify(fresh))

// comparator self-check: one flipped bit in frame 7 of scene 0 must be reported as exactly that frame
const flip = Object.assign({}, node.res[0])
const pos = 64 * 7 + 5
flip.frames = flip.frames.substr(0, pos) + (flip.frames[pos] === '0' ? '1' : '0') + flip.frames.substr(pos + 1)
const sc = compare(node.res[0], flip)
const selftest = { flippedFrame: 7, reportedFrame: sc.firstFrame, mismatchFrames: sc.frameMismatch, ok: sc.firstFrame === 7 && sc.frameMismatch === 1 && !sc.ok }
if (!selftest.ok)
{
    console.error('comparator selftest FAILED', JSON.stringify(selftest))
    process.exit(2)
}

let summary = { task: 'TASK-268', seed: sceneData.seed, scenes: scenes.length, frames: FRAMES, stepsPerFrame: STEPS_PER_FRAME,
                kinds: scenes.reduce((a, s) => (a[s.kind] = (a[s.kind] || 0) + 1, a), {}), selftest, math: mathRes, freshScope: fresh,
                nodeSeconds: +node.seconds.toFixed(3), nodeTeleports: node.res.reduce((a, r) => a + r.teleports.length, 0) }
let exitCode = (mathRes && !mathRes.ok) || !fresh.ok ? 1 : 0
if (flag('--node-only'))
    summary.nodeOnly = true
else
{
    let scenesFile = opt('--scenes', null)
    if (!scenesFile)
    {
        scenesFile = path.join(fs.mkdtempSync('/tmp/portal_parity_'), 'scenes.json')
        fs.writeFileSync(scenesFile, JSON.stringify(sceneData))
    }
    const br = runBrowser(scenesFile)
    console.error(`browser: ${br.data.seconds.toFixed(2)} s in page` + (br.wall ? `, ${br.wall.toFixed(2)} s wall` : ''))
    const byId = new Map(br.data.scenes.map(r => [r.id, r]))
    const rows = node.res.map(n => byId.has(n.id) ? compare(n, byId.get(n.id)) : { id: n.id, ok: false, missing: 'browser' })
    const bad = rows.filter(r => !r.ok)
    summary = Object.assign(summary, {
        browserSeconds: +br.data.seconds.toFixed(3), browserWallSeconds: br.wall === null ? null : +br.wall.toFixed(3),
        browserTeleports: br.data.scenes.reduce((a, r) => a + r.teleports.length, 0),
        pageErrors: br.data.pageErrors,
        comparedScenes: rows.length, mismatchingScenes: bad.length,
        mismatchingFrames: rows.reduce((a, r) => a + (r.frameMismatch || 0), 0),
        teleportCountDiffScenes: rows.filter(r => r.teleportsNode !== r.teleportsBrowser).length,
        teleportRecordDiffScenes: rows.filter(r => r.teleportRecordsEqual === false).length,
        counterDiffScenes: rows.filter(r => r.countersEqual === false).length,
        firstMismatch: bad[0] || null,
        perScene: rows.map(r => [r.id, r.teleportsNode, r.teleportsBrowser, r.frameMismatch, r.ok ? 1 : 0]),
    })
    if (bad.length || br.data.pageErrors.length)
        exitCode = 1
}
summary.pass = exitCode === 0
console.log(`portal parity: scenes ${summary.scenes}, mismatching frames ${summary.mismatchingFrames}, ` +
    `mismatching scenes ${summary.mismatchingScenes}, teleports node ${summary.nodeTeleports} browser ${summary.browserTeleports}, pass ${summary.pass}`)
if (OUT)
    fs.writeFileSync(OUT, JSON.stringify(summary))
if (TIMING)
    fs.writeFileSync(TIMING, JSON.stringify({ task: 'TASK-268', scenes: summary.scenes, frames: FRAMES,
        nodeSeconds: summary.nodeSeconds, browserInPageSeconds: summary.browserSeconds, browserWallSeconds: summary.browserWallSeconds,
        note: 'node = makePortalWorld runs of all scenes; browser in-page = page.evaluate loop; browser wall = python --parity-run process incl. chromium start' }))
process.exit(exitCode)
