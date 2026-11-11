'use strict'
// Hand-drawn pen helpers for the "61 Noir" pad style (ported from artifacts/concepts/src/scene.js).
// Purely visual. Callers seed the rng from stable geometry so strokes do not "boil" between frames.

// Park-Miller generator, seed in 1..2^31-2
function sketchRng(seed)
{
    seed = seed % 2147483647
    if (seed <= 0) seed += 2147483646
    return () => (seed = (seed * 16807) % 2147483647) / 2147483647
}
// Deterministic seed from a list of numbers (e.g. a line's coordinates)
function sketchSeed(values)
{
    let h = 2166136261
    for (let i = 0; i < values.length; ++i)
        h = Math.imul(h ^ (Math.round(values[i] * 10) | 0), 16777619)
    return (h >>> 0) % 2147483646 + 1
}
// Jittered multi-pass stroke
function handLine(g, R, x1, y1, x2, y2, color, w, passes = 2, jit = 1.5, over = 5)
{
    g.save(); g.strokeStyle = color; g.lineCap = 'round'; g.lineJoin = 'round'
    const a = Math.atan2(y2 - y1, x2 - x1), alpha = g.globalAlpha
    for (let p = 0; p < passes; p++)
    {
        g.globalAlpha = alpha * (0.6 + R() * 0.35); g.lineWidth = w * (0.75 + R() * 0.4); g.beginPath()
        const sx = x1 - Math.cos(a) * over * R(), sy = y1 - Math.sin(a) * over * R()
        const ex = x2 + Math.cos(a) * over * R(), ey = y2 + Math.sin(a) * over * R()
        const n = Math.max(3, Math.round(Math.hypot(ex - sx, ey - sy) / 25))
        for (let i = 0; i <= n; i++) { const t = i / n; g.lineTo(sx + (ex - sx) * t + (R() - .5) * jit, sy + (ey - sy) * t + (R() - .5) * jit) }
        g.stroke()
    }
    g.restore()
}
// Slightly wobbly, slightly over-closed circle
function handCircle(g, R, x, y, r, color, w, loops = 1.15)
{
    g.save(); g.strokeStyle = color; g.lineWidth = w; g.lineCap = 'round'; g.beginPath()
    const s = R() * 6.28
    for (let t = 0; t <= 6.28 * loops; t += 0.15) { const rr = r * (1 + (R() - .5) * 0.08); g.lineTo(x + Math.cos(s + t) * rr, y + Math.sin(s + t) * rr) }
    g.stroke(); g.restore()
}
// Hatch a clipped region with parallel strokes at angle `ang`
function hatch(g, clipFn, bx, by, bw, bh, ang, gap, color, w, alpha = 1)
{
    g.save(); clipFn(); g.clip(); g.strokeStyle = color; g.lineWidth = w; g.globalAlpha = alpha; g.beginPath()
    const cx = bx + bw / 2, cy = by + bh / 2, L = Math.hypot(bw, bh), dx = Math.cos(ang), dy = Math.sin(ang)
    for (let d = -L / 2; d < L / 2; d += gap) { const px = cx - dy * d, py = cy + dx * d; g.moveTo(px - dx * L, py - dy * L); g.lineTo(px + dx * L, py + dy * L) }
    g.stroke(); g.restore()
}
function arrowHead(g, x, y, ang, s, color)
{
    g.save(); g.fillStyle = color; g.translate(x, y); g.rotate(ang); g.beginPath()
    g.moveTo(0, 0); g.lineTo(-s, -s * .5); g.lineTo(-s, s * .5); g.closePath(); g.fill(); g.restore()
}
