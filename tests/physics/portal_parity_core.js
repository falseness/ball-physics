// TASK-268: one portal scene run, shared by node (tests/physics/portal_parity.mjs, harness makePortalWorld) and the
// browser (tests/physics/invariants_browser.py --parity-run). step(): one gamePhysics(); ball(): the ball;
// state(): portalState. Records the ball after every frame (x, y, vx, vy) and every teleport record as IEEE-754
// bits (hex), so the comparison is bit for bit.
var PortalParity = {
    hex: function (nums)
    {
        const f = new Float64Array(nums), u = new Uint8Array(f.buffer)
        let s = ''
        for (let i = 0; i < u.length; ++i)
            s += (u[i] < 16 ? '0' : '') + u[i].toString(16)
        return s
    },
    run: function (step, ball, state, frames, per)
    {
        const F = new Float64Array(frames * 4)
        for (let i = 0; i < frames; ++i)
        {
            for (let k = 0; k < per; ++k)
                step()
            const b = ball()
            F[4 * i] = b.posX; F[4 * i + 1] = b.posY; F[4 * i + 2] = b.speedX; F[4 * i + 3] = b.speedY
        }
        const S = state()
        const tp = S.teleports.map(t => [t.step, t.from, t.to, t.kind, PortalParity.hex([t.s, t.d].concat(t.before, t.after))].join('|'))
        return {
            frames: PortalParity.hex(Array.from(F)), teleports: tp, steps: S.steps,
            rimHits: S.rimHits, hostHits: S.hostHits, blockedExits: S.blockedExits
        }
    },
    // Math functions the physics calls, on n deterministic arguments per range (LCG): angles |x| < 10 (portal angles and
    // their differences), |x| < 1e4, |x| < 1e7, small |x| < 2^-20, and unit-vector atan2 / hypot / pow(x, 2) arguments.
    // M: the Math object to test. Returns {fn: hex of all results}.
    mathSample: function (M, n)
    {
        let s = 0x2680
        const rnd = () => { s = (Math.imul(s, 1103515245) + 12345) >>> 0; return s / 4294967296 }
        const ranges = [10, 1e4, 1e7, Math.pow(2, -20)]
        const xs = []
        for (const R of ranges)
            for (let i = 0; i < n; ++i)
                xs.push((rnd() * 2 - 1) * R)
        // exact multiples of pi/4 and the rotation angles of axis-aligned portal pairs
        for (let k = -16; k <= 16; ++k)
            xs.push(k * Math.PI / 4, k * Math.PI / 2 + Math.PI, -k * Math.PI / 2 - Math.PI / 2 + Math.PI)
        const ys = xs.map(() => (rnd() * 2 - 1) * 10)
        const out = {}
        out.sin = PortalParity.hex(xs.map(x => M.sin(x)))
        out.cos = PortalParity.hex(xs.map(x => M.cos(x)))
        out.atan2 = PortalParity.hex(xs.map((x, i) => M.atan2(ys[i], x)))
        out.hypot = PortalParity.hex(xs.map((x, i) => M.hypot(ys[i], x)))
        out.pow2 = PortalParity.hex(xs.map(x => M.pow(x, 2)))
        out.sqrt = PortalParity.hex(xs.map(x => M.sqrt(Math.abs(x))))
        out.n = xs.length
        return out
    }
}
