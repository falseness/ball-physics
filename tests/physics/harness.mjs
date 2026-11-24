// Headless physics harness (TASK-197): loads the real js/sprite.js and js/ball.js into a vm context with
// stubs for the game globals they read (lines, gravitationalAcceleration, portalHosts, portalCaptureZone)
// and steps a ball exactly like index.html gamePhysics(): ball.physics() then ball.move(), 500 steps per frame.
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
export const STEPS_PER_FRAME = 500          // index.html cyclesPerTact
export const FPS = 60
export const STEPS_PER_SECOND = STEPS_PER_FRAME * FPS
export const G = 0.001 / STEPS_PER_FRAME    // index.html gravitationalAcceleration (px/step^2)
export const R = 10                         // index.html new Ball(10, ...)

// Fresh context per world so no state leaks between cases.
export function makeWorld(segments, opts = {})
{
    const ctx = vm.createContext({
        Math, console,
        lines: [],
        gravitationalAcceleration: opts.g === undefined ? G : opts.g,
        portalHosts: () => null,
        portalCaptureZone: () => false,
        portalHostCollision: () => { throw new Error('no portals in the physics harness') },
        GAME_W: 1280, GAME_H: 800,
    })
    for (const f of ['js/sprite.js', 'js/ball.js'])
        vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx, { filename: f })
    const Ball = vm.runInContext('Ball', ctx)
    ctx.lines = segments.map(([x1, y1, x2, y2]) => ({ posX: x1, posY: y1, posX2: x2, posY2: y2 }))
    return {
        ctx, segments,
        ball(x, y, vx = 0, vy = 0, r = R) { return new Ball(r, x, y, vx, vy, '#000', 'ball') },
        step(b) { b.physics(); b.move() },
    }
}

// Geometry helpers (independent of ball.js)
export function closestOnSegment(px, py, [x1, y1, x2, y2])
{
    const dx = x2 - x1, dy = y2 - y1, L2 = dx * dx + dy * dy
    let t = L2 ? ((px - x1) * dx + (py - y1) * dy) / L2 : 0
    t = Math.max(0, Math.min(1, t))
    return [x1 + t * dx, y1 + t * dy, t]
}
export function distToSegments(px, py, segs)
{
    let best = Infinity
    for (const s of segs)
    {
        const [cx, cy] = closestOnSegment(px, py, s)
        best = Math.min(best, Math.hypot(px - cx, py - cy))
    }
    return best
}
export const deg = (a) => a * 180 / Math.PI
export function angleBetween(ax, ay, bx, by)
{
    const c = (ax * bx + ay * by) / (Math.hypot(ax, ay) * Math.hypot(bx, by))
    return deg(Math.acos(Math.max(-1, Math.min(1, c))))
}
export function reflect(vx, vy, nx, ny)
{
    const d = vx * nx + vy * ny
    return [vx - 2 * d * nx, vy - 2 * d * ny]
}
// Ball resting on segment s (upper side = the side the left-hand normal of a left-to-right segment points to, -y)
export function restingOn([x1, y1, x2, y2], t, r = R)
{
    const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy)
    let nx = dy / L, ny = -dx / L
    if (ny > 0) { nx = -nx; ny = -ny }
    return [x1 + t * dx + r * nx, y1 + t * dy + r * ny]
}
// Livelock window: a 1 s window in which the ball stays inside a 2 px box (every step's centre) while its
// mean speed stays at or above 0.002 px/step (60 px/s): kinetic energy that goes nowhere.
export const LIVELOCK_BOX_PX = 2, LIVELOCK_MEAN_SPEED = 0.002
export function livelockWindows(frames)
{
    // frames: [{x, y, meanSpeed, minX, maxX, minY, maxY}] one per frame
    const out = []
    for (let i = 0; i + FPS <= frames.length; i += FPS / 2)
    {
        let ms = 0, x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
        for (let k = i; k < i + FPS; ++k)
        {
            const f = frames[k]
            ms += f.meanSpeed
            x0 = Math.min(x0, f.minX); x1 = Math.max(x1, f.maxX); y0 = Math.min(y0, f.minY); y1 = Math.max(y1, f.maxY)
        }
        ms /= FPS
        const box = Math.max(x1 - x0, y1 - y0)
        if (box < LIVELOCK_BOX_PX && ms >= LIVELOCK_MEAN_SPEED)
            out.push({ fromFrame: i, box: +box.toFixed(4), meanSpeed: +ms.toFixed(6), x: +x0.toFixed(2), y: +y0.toFixed(2) })
    }
    return out
}
// Run n frames, returning per-frame summaries; onStep(b, stepIndex) optional (return true to stop)
export function runFrames(w, b, n, onStep)
{
    const frames = []
    let s = 0
    for (let f = 0; f < n; ++f)
    {
        let sp = 0, minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, k = 0, stop = false
        for (; k < STEPS_PER_FRAME; ++s)
        {
            w.step(b)
            ++k
            sp += Math.hypot(b.speedX, b.speedY)
            minX = Math.min(minX, b.posX); maxX = Math.max(maxX, b.posX); minY = Math.min(minY, b.posY); maxY = Math.max(maxY, b.posY)
            if (onStep && onStep(b, s)) { stop = true; break }
        }
        frames.push({ x: b.posX, y: b.posY, meanSpeed: sp / k, minX, maxX, minY, maxY })
        if (stop) break
    }
    return frames
}
export const round = (v, d = 6) => (typeof v === 'number' && isFinite(v)) ? +v.toFixed(d) : v

// Same sources and stubs as makeWorld, but js/sprite.js + js/ball.js are compiled inside one function scope
// (new Function) instead of a vm context: the game globals become closure variables, which is ~60x faster
// in node 12 (vm context globals go through interceptors). TASK-198 uses it for the fuzz runs; its
// selftest checks that it steps exactly like makeWorld.
let fastFactory = null
export function makeFastWorld(segments, opts = {})
{
    if (!fastFactory)
    {
        const src = ['js/sprite.js', 'js/ball.js'].map(f => fs.readFileSync(path.join(ROOT, f), 'utf8')).join('\n')
        fastFactory = new Function('G', `var lines = [], gravitationalAcceleration = G, GAME_W = 1280, GAME_H = 800
            function portalHosts() { return null }
            function portalCaptureZone() { return false }
            function portalHostCollision() { throw new Error('no portals in the physics harness') }
            ${src}
            return { Ball: Ball, setLines: function (l) { lines = l } }`)
    }
    const W = fastFactory(opts.g === undefined ? G : opts.g)
    W.setLines(segments.map(([x1, y1, x2, y2]) => ({ posX: x1, posY: y1, posX2: x2, posY2: y2 })))
    return {
        segments,
        ball(x, y, vx = 0, vy = 0, r = R) { return new W.Ball(r, x, y, vx, vy, '#000', 'ball') },
        step(b) { b.physics(); b.move() },
    }
}
