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

## Contact model (Ball.contactCollision)

Every line is a segment. Wall-portal host lines are split into their solid pieces (see "Portals" below).

1. **Closest point.** For each segment take the closest point q on it, end points included, and the
   normal n = (c − q)/|c − q|. It is a contact when |c − q| < R + CONTACT_SLOP (1e-9 px), so a ball lying
   exactly on a line stays in contact. Line ends are therefore not a special case: an end hit reflects
   about the true contact normal (a graze over a free end deflects slightly, it does not reverse).
2. **Approach test, velocity phase.** Contacts come from the position at the start of the step, so the
   normals are fixed. They are resolved deepest first and re-tested after each resolution, for up to
   CONTACT_ITERATIONS = 4 iterations:
   - approaching (v·n < −REST_SPEED): reflect, v' = v − 2(v·n)n. Each line reflects at most once per step;
   - resting (−REST_SPEED ≤ v·n ≤ 0, or a line that already reflected this step): v·n is set to −g·n
     when gravity points into the line, else to 0. After gravity the ball then neither sinks nor hops, so
     rolling is exact. If this pushes v back into the previously resolved line (a wedge), both lines are
     solved together: v' = v + a·n1 + b·n2 with a, b ≥ 0;
   - moving away (v·n > 0): left untouched. Before TASK-199 a ball overlapping an end while moving away
     flipped its velocity every step and froze (livelock).
   - REST_SPEED = 0.0083 px/step (~250 px/s, the normal speed after a ~17 px drop). This is a restitution
     velocity threshold, as in Box2D. The window that works is narrow: at least 0.008, so a ball sliding into
     a 90° V settles, and below 0.0087, so the slowest graze (d = 9) still reflects.
3. **Push-out, position phase.** The deepest overlap is pushed out to exactly R along its normal, then
   re-tested, up to 4 times. Two overlapping lines are solved together (p' = p + a·n1 + b·n2), otherwise
   a ball in an acute wedge would creep out over many steps and gain potential energy.
4. **Deepest first** in both phases. This made the slope-to-floor joint order-independent: before, two
   segment reflections in one step threw the ball back up the slope.
5. **Energy.** A contact never adds energy. If E grew after a velocity change (the reflection changes
   g·vy/2; push-out changes g·y), the outgoing normal speed along the last resolved normal is lowered until
   E = E0 (`Ball.limitEnergy`). This is not applied when only the position changed.
6. **Resting contacts.** A ball on a floor or slope sits at distance R exactly (sink ~2e-6 px), with no
   rest jitter. On a slope its speed after 1 s is g·sin(θ)·1 s (tests/physics/rolling.mjs, ratio 1).
7. **Ghost vertices (TASK-200).** Line ends within CHAIN_JOIN = 5 px (the editor's snap radius) form a
   chain. A contact whose closest point is a joined end V is ignored when the centre projects into the
   joined segment past V (its normal is outside the joint's cone), and that segment is itself a contact
   at least as close as V. This is the Box2D chain rule. A ball sliding over a seam or into a concave joint
   never gets an internal normal (no seam kick). A V that sticks out deeper than the joined face is a real
   step and is kept.

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
  mirror for |s| ≤ h), with its energy capped by `Ball.limitEnergy`.
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
- rimtrap.py and embed.py gate against pre-TASK-201 baselines plus the hash-pinned allowlists in
  tests/portal/allow/. After a physics change, never re-record a baseline from the tree under test.
  Instead, replay the changed cases with tests/portal/baseline_diverge.py against the pre-change tree.
- trail_speed needs a physics-matched base: `git archive 7bf1d25` + fonts/ + img/ + this tree's js/ball.js,
  js/portal.js and js/levels.js (the levels changed in TASK-202..212).
