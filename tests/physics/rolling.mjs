// Rolling baseline metrics, headless (TASK-197): the real js/ball.js stepped like the game
// (tests/physics/harness.mjs). Prints one compact JSON line {head, metrics: {name: number}}; --out FILE also writes it.
//   slope<deg>_speed_px_s   speed after 1 s from rest on a 10/20/30/45 degree line (frictionless ideal: g*sin(deg)*1 s)
//   slope<deg>_ratio        that speed / the ideal
//   slope<deg>_sink_px      deepest penetration (radius - distance to the line) during that second
//   slope<deg>_lift_px      largest gap (distance to the line - radius) during that second (hops)
//   flat_rest_jitter_px     range of y over 0.5..2 s for a ball placed on a flat floor (tangent, v = 0)
//   flat_rest_max_abs_vy    largest |vy| (px/step) over the same window
//   flat_sunk_jitter_px / flat_sunk_sink_px / flat_sunk_end_sink_px   the same ball placed 0.5 px into the floor
//   flat_roll_jitter_px / flat_roll_sink_px   rolling at 0.02 px/step (600 px/s) along the floor for 1 s
import fs from 'node:fs'
import { execSync } from 'node:child_process'
import * as h from './harness.mjs'

const { R, G, FPS, STEPS_PER_SECOND } = h
const gPxS2 = G * STEPS_PER_SECOND * STEPS_PER_SECOND
const m = {}
const r = (v, d = 9) => h.round(v, d)

for (const deg of [10, 20, 30, 45])
{
    const a = deg * Math.PI / 180, L = 1500
    const seg = [100, 100, 100 + L * Math.cos(a), 100 + L * Math.sin(a)]
    const w = h.makeWorld([seg])
    const [x, y] = h.restingOn(seg, 0.02), b = w.ball(x, y, 0, 0)
    let sink = 0, lift = 0
    h.runFrames(w, b, FPS, (bb) =>
    {
        const d = h.distToSegments(bb.posX, bb.posY, [seg])
        sink = Math.max(sink, R - d); lift = Math.max(lift, d - R)
    })
    const sp = Math.hypot(b.speedX, b.speedY) * STEPS_PER_SECOND, ideal = gPxS2 * Math.sin(a)
    m[`slope${deg}_speed_px_s`] = r(sp, 4)
    m[`slope${deg}_ratio`] = r(sp / ideal, 6)
    m[`slope${deg}_sink_px`] = r(sink, 6)
    m[`slope${deg}_lift_px`] = r(lift, 6)
}

function flat(y0, vx, seconds, from)
{
    const seg = [100, 300, 1200, 300], w = h.makeWorld([seg]), b = w.ball(300, y0, vx, 0)
    let s0 = from * STEPS_PER_SECOND, yMin = Infinity, yMax = -Infinity, vyMax = 0, sink = 0
    h.runFrames(w, b, Math.round(seconds * FPS), (bb, s) =>
    {
        if (s < s0) return
        yMin = Math.min(yMin, bb.posY); yMax = Math.max(yMax, bb.posY)
        vyMax = Math.max(vyMax, Math.abs(bb.speedY))
        sink = Math.max(sink, R - (300 - bb.posY))
    })
    return { jitter: yMax - yMin, vyMax, sink, endSink: R - (300 - b.posY) }
}
const rest = flat(300 - R, 0, 2, 0.5)
m.flat_rest_jitter_px = r(rest.jitter); m.flat_rest_max_abs_vy = r(rest.vyMax); m.flat_rest_sink_px = r(rest.sink)
const sunk = flat(300 - R + 0.5, 0, 2, 0.5)
m.flat_sunk_jitter_px = r(sunk.jitter); m.flat_sunk_sink_px = r(sunk.sink); m.flat_sunk_end_sink_px = r(sunk.endSink)
const roll = flat(300 - R, 0.02, 1, 0)
m.flat_roll_jitter_px = r(roll.jitter); m.flat_roll_sink_px = r(roll.sink); m.flat_roll_max_abs_vy = r(roll.vyMax)

let head = null
try { head = execSync('git rev-parse --short HEAD', { cwd: h.ROOT }).toString().trim() } catch (e) { }
const out = JSON.stringify({ head, g_px_s2: gPxS2, radius: R, metrics: m })
const i = process.argv.indexOf('--out')
if (i >= 0) fs.writeFileSync(process.argv[i + 1], out + '\n')
console.log(out)
