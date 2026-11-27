# Ball physics

How the ball collides with lines and portals (js/ball.js, js/portal.js), the invariants the tests check,
and how to run the physics test suites. Background: TASK-197 (edge-case suite), TASK-198 (invariant
checker), TASK-199 (contact model), TASK-200 (ghost vertices), TASK-201 (portals), TASK-202..212 (level
gates re-proved under this model), TASK-213 (final regression).

## Units and stepping

- The game runs 500 physics steps per frame at 60 fps. Per step: `ball.physics()` (gravity, then line
  contacts), `ball.move()` (x += v), then `portalStep()`.
- Gravity is g = 0.001/500 px/step² (1800 px/s²). The ball radius is 10 px.
- The integrator is `v += g; x += v`. Its exact free-flight invariant is
  E = |v|²/2 + g·vy/2 + g·(H − y), with H = 800. Plain KE + PE drifts by g·vy/2 per step, and that drift
  would make every floor bounce look like it gains energy.

## Contact model (Ball.contactCollision): elastic, energy-conserving (TASK-270)

The rule (the user's, TASK-266..273): without portals the ball neither loses nor gains energy. There is no
resting contact and no restitution threshold: a ball dropped on a floor bounces back to the height it fell
from forever, and a ball in a V rocks in it forever. (Before TASK-270, REST_SPEED = 0.0083 px/step turned every
slower approach into a resting contact that zeroed the normal speed; that lost energy at every landing and is gone,
together with the 'normal force' v·n = −g·n and the wedge solve.)

Every line is a segment. Wall-portal host lines are split into their solid pieces (see "Portals" below).

1. **Closest point.** For each segment take the closest point q on it, end points included, and the
   normal n = (c − q)/|c − q|. It is a contact when |c − q| < R + CONTACT_SLOP (1e-9 px), so a ball lying
   exactly on a line stays in contact. Line ends are not a special case: an end hit reflects about the true
   contact normal (a graze over a free end deflects slightly, it does not reverse).
2. **Velocity: elastic reflection.** Contacts come from the position at the start of the step, so the normals
   are fixed. Every approaching contact (v·n < 0) reflects, v' = v − 2(v·n)n (tangential part kept), deepest
   first, re-tested after each reflection, up to CONTACT_ITERATIONS = 16 (a V reflects off its walls in turn
   until the ball leaves both). If the iterations run out with the ball still approaching, the approaching
   parts are dropped (step 4 gives the energy back). Moving away (v·n ≥ 0): untouched. Before TASK-199 a ball
   overlapping an end while moving away flipped its velocity every step and froze (livelock).
3. **Position: push-out.** The deepest overlap is pushed out to exactly R along its normal, then re-tested, up
   to PUSH_ITERATIONS = 4 times. Two overlapping lines are solved together (p' = p + a·n1 + b·n2). A contact
   the ball did not approach at the step start and whose overlap this step's own move clears is not pushed out
   (`Ball.clearedByMove`, TASK-271: a ball grazing past a line end).
4. **Energy: exact.** With E = |v|²/2 + g·vy/2 − g·y (the integrator invariant), the reflection changes the
   g·vy/2 term and a push-out changes the height. After steps 2-3, `Ball.setEnergy(E0, n)` sets the outgoing
   normal speed along the last reflected normal (else the last push-out normal) to the root w ≥ 0 that makes
   E equal E0 again: two-sided, it removes a gain and restores a loss. If a downward push-out would need a
   normal speed larger than one contact plus gravity can explain (a line end), the ball is pushed out slightly
   less instead (TASK-271). Only a start state that is not reachable (a ball spawned inside a line) can stay
   above E0, then its velocity is scaled towards 0.
5. **Floors and slopes.** A ball on a floor does a period-2 micro-bounce (normal speed 0 ↔ g, ~2e-6 px
   amplitude); a rolling ball makes gravity-sized elastic micro-bounces and its speed after a drop dh is
   sqrt(2·g·dh) (tests/physics/rolling.mjs, 1e-6 relative). Rolling metrics: flat rest jitter / sink /
   max |vy| are 2e-6 px (re-recorded in rolling_accepted.json by TASK-273; 0 under the old resting contact).
6. **Deepest first** in both phases, so the slope-to-floor joint is order-independent.
7. **Ghost vertices (TASK-200).** Line ends within CHAIN_JOIN = 5 px (the editor's snap radius) form a
   chain. A contact whose closest point is a joined end V is ignored when the centre projects into the
   joined segment past V (its normal is outside the joint's cone), and that segment is itself a contact
   at least as close as V. This is the Box2D chain rule. A ball sliding over a seam or into a concave joint
   never gets an internal normal (no seam kick). A V that sticks out deeper than the joined face is a real
   step and is kept.

Portals are excluded from conservation: a teleport keeps speed (rule T) but changes height. Every other step,
contact or free, keeps E to 1e-9·E_ref (tests/physics/energy.mjs).

## Portals and the contact model (TASK-201)

- A wall portal's host line takes part as solid pieces (`portalHostSegs`):
  - with the ball centre in front (d > 0), only the pieces outside the opening;
  - while the ball moves away from that front, only the host line's real ends;
  - from behind, the whole line, because walls block from behind.
- Capture is unchanged from TASK-074/173 (`portalCaptureZone`). A ball being captured (front, v·n < 0)
  ignores a host-piece contact within h + R of the portal centre along the line. It sinks in until it
  touches the opening and is then teleported. Other host contacts resolve like any line.
- **Teleport rule.** A teleport preserves speed: |v| after `portalStep` equals |v| before it (1e-9
  relative). The exit keeps the entry depth d < R in front of the exit plane.
- **Exit grace.** The portal the ball just left cannot capture it by touch again until the centre is more
  than R from that opening. This prevents a 2-step ping-pong for exits with almost zero normal speed.
- **Refused teleport.** When a line blocks the exit, the ball bounces off the entry plane (the TASK-176
  mirror for |s| ≤ h) as a contact at the step start, with E set back to E0 by `Ball.setEnergy` (TASK-271).
- **Exit push-out (TASK-271).** In a teleport step an exit that overlaps its rim (entry depth d < R) is pushed
  out to R, velocity kept (rule T).
- Rims (c ± h·t) are point colliders for balls that are not being captured.

## Invariants (tests/physics/invariants_core.js)

The checker is fed every step and does not sample.

- **I1, no stuck (texture stuck).**
  - (a) Depth: the centre more than 0.5 px inside a solid line for more than 2 consecutive steps.
  - (b) Livelock: 20 or more velocity sign flips (both speeds ≥ 1e-4 px/step) within 200 steps, with the
    centre inside a 0.5 px box.
- **I2, plausible velocity.**
  - Without contact, the change is exactly the gravity step (vx1 === vx0, vy1 === vy0 + g).
  - With contact, the impulse J = Δv − g must be explained by one touched normal: no tangential part, |vn|
    does not grow beyond |vn0| + |g·n|, the ball leaves the line, and a ball already moving away is left
    unchanged. Two touched normals may also explain it as a corner cone (a·n1 + b·n2, a, b ≥ 0).
- **I3, energy.** On a contact step, E1 − E0 ≤ 1e-6·|E0|, with E the integrator invariant above.
- **T, teleport.** Teleport steps are exempt from I2/I3; |v| is preserved within 1e-9 relative.

In browser mode (tests/physics/invariants_browser.py), the capture zone is computed independently from the
portal geometry. Host contacts covered by a capture are not contacts for I2/I3 and do not count for I1
depth.

## Running the suites

**Fast physics checks: run before every physics commit.**

```
tests/physics/run_fast.sh [outdir]      # ~1 min on 8 cores, node only, exit 0 = all four suites pass
```

It runs tests/physics/energy.mjs, stuck.mjs, portal_fast.mjs and edge_cases.mjs:

- **energy** (no portals): on every step, contact or free, |E1 − E0| ≤ 1e-9·E_ref, and per scene
  |E_end − E_start| ≤ 1e-7·E_ref, E_ref = g·H + max |v|²/2 over the scene. Losses and gains are counted
  separately, so a damping bug and a pumping bug both fail.
- **stuck** ("not stuck in textures", no portals): (a) depth, the centre more than 0.5 px inside a line on two
  consecutive states; (b) tunnelling, the centre crossing a segment's interior between two steps; (c) livelock,
  a 1 s window inside a 2 px box while moving; (d) freeze, the same position for 60+ frames while overlapping a line.
- **portal_fast**: the stuck checks after portal interactions (post-teleport embed, rim trap), rule T on every
  teleport, and two-sided energy on every non-teleport step.
- **edge_cases**: graze, spike, joint, seam, v_corner (rocks in the V for 10 s, energy 1e-9/1e-7), ...

It and prints one summary line per suite (`<suite> PASS|FAIL exit=N seconds=S <verdict>`, failing
scenes listed under it), then `RUN_FAST PASS` or `RUN_FAST FAIL: <suites>`. Per-suite logs and JSON are kept
in `outdir` when given. tests/regression/run_checks.sh runs it in both preview and full mode.

```
node tests/physics/edge_cases.mjs [--out FILE] [--only graze,spike,...]     # ~15 s, exit 0 = all pass
node tests/physics/rolling.mjs --out FILE                                    # deterministic metrics, 1 line JSON
node tests/physics/invariants.mjs --selftest
node tests/physics/invariants.mjs --fuzz 1-5 --chains 1-5 [--scenes N] --out FILE   # headless, ~5 min
node tests/physics/invariants.mjs --levels [--level-list 1,2] --out FILE            # every shoot levelNN in the game
node tests/physics/invariants.mjs --browser --portal-fuzz 1-3 [--portal-cases N] --out FILE
```

- **edge_cases** cases: graze, spike, moving_away, joint, seam, v_corner, shelf_pocket, head_on,
  slope_seam. Every expectation is physical (reflection about the contact normal, no energy gain, no
  livelock), never taken from the current behaviour.
- **rolling**: compare against the accepted values with the TASK-199 rule. A metric passes when it is
  within [min − tol, max + tol], tol = max(2·range, 1 % of |value|). The accepted values are committed in
  tests/physics/rolling_accepted.json; run `python3 tests/physics/rolling_compare.py [--out FILE] r1.json r2.json
  r3.json` on three rolling.mjs outputs (exit 0 = pass, 1 = a metric is outside).
- **invariants**: exit 1 on any I1/I2/I3/T violation. The output JSON lists counts per kind and the first
  examples.
- Shoot win shortcuts put the ball on the flag's pennant edge, not on the flag origin. The origin lies on the floor
  line, and push-out moves a ball placed there out of the floor and away from the flag.
- The full regression (shoot, portal sim/fuzz/rimtrap/embed, preview/trail/speed/map checks, telemetry
  sequences, incl. telemetry_first30 since TASK-242) is `tests/regression/run_checks.sh <preview|full> <outdir>` (preview ~3.5 min, full ~17 min). It writes
  <outdir>/regression.log, ending with `failed rows: N [...]` and `ALL PASS` when N = 0 (exit 1 otherwise).
- **portal_parity** (`node tests/physics/portal_parity.mjs [--per-kind N] [--math N] [--out FILE]`, ~75 s idle):
  the only check that the tests/physics/harness.mjs copy of the game physics (used by run_fast and the node suites
  above) matches the browser bit for bit. It runs 4 × 50 fuzz.py portal scenes in node and in the game page and
  compares every frame, teleport and portalState counter, and checks the harness's glibc sin/cos port
  (tests/physics/glibc_sincos.js; node's Math.sin/cos differ from Chromium's in the last bit) against the page's
  Math. Exit 0 = every scene matches and the math check is ok. tests/regression/run_checks.sh runs it in both modes
  (preview `--per-kind 10 --math 5000`) and assemble.py's `portal_parity` row needs exit 0, `mismatching scenes 0
  ... pass true` and a math check with `"ok":true`.
- Platform / analytics / stats rows (TASK-280, both run_checks.sh modes): `backends`
  (`tests/platform/test_backends.py --out DIR`, exit 0 and `OK: 5 backends`), `analytics`
  (`tests/platform/test_analytics.py --backend none --out DIR`, no network: exit 0, a `none ... PASS` line and a
  final `OK`) and `stats_fixture` (`tools/stats_report.py --root tests/stats/fixture` then
  `tests/stats/check_fixture.py`, exit 0 and `"equal":true`). Both platform tests require `--out` (no default into
  ./artifacts); the runner writes everything under <outdir>.
- rimtrap.py and embed.py gate against pre-TASK-201 baselines plus the hash-pinned allowlists in
  tests/portal/allow/. After a physics change, never re-record a baseline from the tree under test.
  Instead, replay the changed cases with tests/portal/baseline_diverge.py against the pre-change tree.
- trail_speed needs a physics-matched base: `git archive 7bf1d25` + fonts/ + img/ + this tree's js/ball.js,
  js/portal.js and js/levels.js (the levels changed in TASK-202..212).
