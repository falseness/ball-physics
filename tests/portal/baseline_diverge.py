#!/usr/bin/env python3
"""Where does each changed case of rimtrap.py / embed.py first diverge from the pre-change code? (TASK-201)

  python3 tests/portal/baseline_diverge.py --suite rimtrap|embed --base BASE.json --new NEW.json --head-root DIR \
      --out REPORT.json [--allowlist-out tests/portal/allow/SUITE_taskNNN.json] [--jobs 8]

BASE = the suite's output recorded from the pre-change tree (rimtrap.json / embed.json), NEW = its output from this
tree, DIR = the pre-change tree (e.g. git archive <commit> | tar -x -C DIR; cp -r fonts img DIR).

For every case whose outcome differs between BASE (recorded from the HEAD 4deacfa tree) and NEW (this tree), the case
is replayed in both trees (HEAD tree = --head-root, new tree = this repo) with the game's own gamePhysics() parts:
  pass 1: state + portal counters at the end of every frame (500 steps) -> first frame F where they differ;
  pass 2: inside frame F, every step: state before, after ball.physics() + ball.move() ('mid', before portalStep())
          and after portalStep() -> first step k whose result differs.
Given an identical state before step k:
  phase 'physics' : the trees already differ at 'mid' (the ball's contact resolution / integration),
  phase 'portal'  : 'mid' is identical and only portalStep() differs (a teleport / rim / blocked-exit rule change).
hostDist / lineDist: distance of the centre (before step k) to the nearest wall-portal host line / other line,
minus the radius (<= 1e-6: in contact).
A case is EXPLAINED (allowlist) when phase == 'physics' and hostDist <= 1e-6 (the step resolves a contact with a
wall-portal host line, which TASK-201 moved from the old reflect-on-overlap path to the contact model) and the
replays reproduce both recorded outcomes ('host-contact-physics'), or when phase == 'portal' and portalStep() made the
same decisions in both trees (same counters) and refused a teleport there, with the same position after it and
velocities that differ only along a portal normal with no more energy ('blocked-bounce-energy-cap': TASK-201 caps the
refused-exit bounce with the contact model's energy rule, Ball.limitEnergy). Everything else is listed as unexplained
(exit 1, and it is never written to the allowlist). --recheck REPORT replays only REPORT's unexplained cases.
"""
import argparse, json, os, sys, hashlib
from multiprocessing import Pool
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'tests', 'portal')); sys.path.insert(0, os.path.join(REPO, 'tests', 'visual'))
import rimtrap, embed, baseline_allow, subprocess
from sim import open_page

JS = r"""(o) => {
  window.__portalTest.setup(o.cfg); physics = false
  const P = currentPortals() || [], R = ball.radius
  const host = new Set(P.map(p => p.line).filter(k => typeof k == 'number'))
  const C = () => [portalState.teleports.length, portalState.hostHits, portalState.rimHits, portalState.blockedExits]
  const S = () => [ball.posX, ball.posY, ball.speedX, ball.speedY]
  const dist = (x, y, s) => { const dx = s.posX2 - s.posX, dy = s.posY2 - s.posY, L2 = dx*dx + dy*dy
    let t = L2 > 0 ? ((x - s.posX) * dx + (y - s.posY) * dy) / L2 : 0; t = Math.max(0, Math.min(1, t))
    return Math.hypot(x - s.posX - t * dx, y - s.posY - t * dy) }
  const near = () => { let h = Infinity, o = Infinity
    lines.forEach((l, k) => { const d = dist(ball.posX, ball.posY, l) - R; if (host.has(k)) h = Math.min(h, d); else o = Math.min(o, d) })
    return [h, o] }
  const out = []
  for (let f = 1; f <= o.frames; ++f) {
    for (let i = 0; i < 500; ++i) {
      if (o.frame === f) {
        const s0 = S(), nr = near(), c0 = C()
        ball.physics(); ball.move(); const mid = S()
        portalStep(); out.push([i, s0, mid, S(), C(), nr, c0, P.map(p => { const f = portalFrame(p); return [f.nx, f.ny] }), gravitationalAcceleration])
      } else gamePhysics()
      if (!ball.onMap()) { if (!o.frame) out.push(S().concat(C())); return {out, offmap: f} }
    }
    if (!o.frame) out.push(S().concat(C()))
    if (o.frame === f) return {out}
  }
  return {out}
}"""

def cfg_for(suite, key):
    if suite == 'rimtrap':
        o, s, a, sp = key
        return rimtrap.case_cfg(o, rimtrap.release(o, 'front', s, a, rimtrap.SPEEDS[sp]))
    k, s, a = key.split('|'); geo = embed.geometries()
    return embed.opts_for((k, int(s[1:]), int(a[1:])), geo)['setup']['cfg']

def rd(v): return round(v * 1e6) / 1e6


def energy_cap(x, y):
    """Step records x (pre-change tree) and y (this tree) with the same state before and after the move: True when
    portalStep() made the same decisions in both (counters before and after equal) and refused a teleport in this step
    (blockedExits + 1), the positions after it are equal and the velocities differ only along one portal normal, the
    new one with no more energy E = |v|^2/2 + g vy/2 - g y: the refused-exit bounce got the contact model's energy cap
    (Ball.limitEnergy, TASK-201) and nothing else changed."""
    if x[6] != y[6] or x[4] != y[4] or x[4][3] != x[6][3] + 1 or x[3][:2] != y[3][:2]:
        return False
    g = x[8]
    E = lambda st: 0.5 * (st[2] ** 2 + st[3] ** 2) + 0.5 * g * st[3] - g * st[1]
    dvx, dvy = y[3][2] - x[3][2], y[3][3] - x[3][3]
    sp = max(abs(x[3][2]) + abs(x[3][3]), 1e-300)
    along = any(abs(dvx * n[1] - dvy * n[0]) <= 1e-12 * sp for n in x[7])
    return along and E(y[3]) <= E(x[3])

def worker(job):
    suite, keys, head_root = job
    from playwright.sync_api import sync_playwright
    res = []
    with sync_playwright() as p:
        bh, ph, eh = open_page(p, head_root)
        bn, pn, en = open_page(p, REPO)
        for key in keys:
            cfg = cfg_for(suite, key)
            fh = ph.evaluate(JS, {'cfg': cfg, 'frames': 120, 'frame': 0})['out']
            fn = pn.evaluate(JS, {'cfg': cfg, 'frames': 120, 'frame': 0})['out']
            F = next((i + 1 for i, (x, y) in enumerate(zip(fh, fn)) if x != y), None)
            if F is None and len(fh) != len(fn):
                F = min(len(fh), len(fn)) + 1
            r = {'key': key, 'frame': F, 'end': [[rd(v) for v in fh[-1][:4]], [rd(v) for v in fn[-1][:4]]]}
            if F is not None:
                sh = ph.evaluate(JS, {'cfg': cfg, 'frames': 120, 'frame': F})['out']
                sn = pn.evaluate(JS, {'cfg': cfg, 'frames': 120, 'frame': F})['out']
                k = next((j for j, (x, y) in enumerate(zip(sh, sn)) if x[3] != y[3] or x[4] != y[4]), None)
                if k is None:
                    r['phase'] = 'none'
                else:
                    x, y = sh[k], sn[k]
                    r.update(step=x[0], same_before=x[1] == y[1], phase='physics' if x[2] != y[2] else 'portal',
                             hostDist=x[5][0], lineDist=x[5][1], counters=[x[4], y[4]], before=x[1], mid=[x[2], y[2]], after=[x[3], y[3]],
                             energyCap=energy_cap(x, y))
            res.append(r)
        bh.close(); bn.close()
    return res

def write_allowlist(a, cases, sha):
    if a.allowlist_out:
        git = lambda *c: subprocess.run(['git'] + list(c), cwd=REPO, capture_output=True, text=True).stdout.strip()
        al = {'suite': a.suite, 'baseline': os.path.relpath(a.base, REPO), 'baselineSha256': sha(a.base),
              'tree': {'head': git('rev-parse', 'HEAD'), 'ball.js': sha(os.path.join(REPO, 'js', 'ball.js'))[:16],
                       'portal.js': sha(os.path.join(REPO, 'js', 'portal.js'))[:16]},
              'preTree': os.path.relpath(a.head_root, REPO), 'report': os.path.relpath(a.out, REPO),
              'why': {'blocked-bounce-energy-cap': 'first divergent step: same state before it and after the move, '
                      'portalStep() refused a teleport in both trees with the same counters, the same position after it and '
                      'velocities that differ only along a portal normal with no more energy: the refused-exit bounce is capped '
                      'by the contact model energy rule (Ball.limitEnergy) and nothing else changed',
                      'host-contact-physics': 'first divergent step: same state before it, ball.physics()/move() differ '
                      '(portalStep() not involved), the ball within its radius of a wall-portal host line: the host line '
                      'is resolved by the ball contact model (TASK-199 rules) instead of the old reflect-on-overlap '
                      'portalHostCollision'},
              'cases': {k: [baseline_allow.outcome_hash(e['base']), baseline_allow.outcome_hash(e['new']), e['why'],
                            e['frame'], e['step']] for k, e in sorted(cases.items()) if e['why'] != 'UNEXPLAINED'}}
        os.makedirs(os.path.dirname(os.path.abspath(a.allowlist_out)), exist_ok=True)
        with open(a.allowlist_out, 'w') as fh:
            json.dump(al, fh, separators=(',', ':'))
            fh.write('\n')


def outcomes(suite, path):
    d = json.load(open(path))
    if suite == 'rimtrap':
        return {tuple(k): o for k, o in zip(d['front']['keys'], d['front']['outcomes'])}
    return d['outcomes']

def main():
    ap = argparse.ArgumentParser()
    for x in ('--suite', '--base', '--new', '--head-root', '--out'): ap.add_argument(x, required=True)
    ap.add_argument('--jobs', type=int, default=8); ap.add_argument('--allowlist-out', default=None)
    ap.add_argument('--recheck', default=None, help='a REPORT.json of the same --base / --new: replay only its UNEXPLAINED '
                    'cases (the others keep their class) and write the merged report to --out')
    ap.add_argument('--from-report', default=None, help='reuse a REPORT.json of the same --base / --new (sha256 checked) instead of replaying'); ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
    if a.from_report:
        # the report must cover exactly the changed cases of --base -> --new with the same outcomes (--base may be
        # another recording of the same pre-change code, e.g. artifacts/TASK-163/baseline.json for rimtrap)
        doc = json.load(open(a.from_report))
        B, N = outcomes(a.suite, a.base), outcomes(a.suite, a.new)
        ks = lambda k: '|'.join(map(str, k)) if a.suite == 'rimtrap' else k
        changed = {ks(k): (B[k], N[k]) for k in N if k in B and B[k] != N[k]}
        bad = [k for k in set(changed) | set(doc['cases']) if k not in changed or k not in doc['cases'] or
               [doc['cases'][k]['base'], doc['cases'][k]['new']] != list(changed[k])]
        if doc['suite'] != a.suite or bad:
            raise SystemExit('report %s does not match %s -> %s: %d cases differ, e.g. %s' % (a.from_report, a.base, a.new, len(bad), bad[:3]))
        a.out = a.from_report
        write_allowlist(a, doc['cases'], sha)
        print('suite=%s changed=%d classes=%s (from report)' % (a.suite, doc['changed'], doc['classes']))
        return 1 if doc['classes'].get('UNEXPLAINED') else 0
    B, N = outcomes(a.suite, a.base), outcomes(a.suite, a.new)
    keys = [k for k in N if k in B and B[k] != N[k]]
    prev = None
    if a.recheck:
        prev = json.load(open(a.recheck))
        if prev['baseSha256'] != sha(a.base) or prev['newSha256'] != sha(a.new) or prev['changed'] != len(keys):
            raise SystemExit('report %s is for other inputs' % a.recheck)
        keys = [k for k in keys if prev['cases'][('|'.join(map(str, k)) if a.suite == 'rimtrap' else k)]['why'] == 'UNEXPLAINED']
    if a.limit: keys = keys[:a.limit]
    jobs = [(a.suite, [list(k) if isinstance(k, tuple) else k for k in keys[i::a.jobs]], os.path.abspath(a.head_root)) for i in range(a.jobs)]
    with Pool(a.jobs) as pool:
        res = [r for part in pool.map(worker, jobs) for r in part]
    cases, unexplained, phases = {}, [], {}
    if prev:
        for k, e in prev['cases'].items():
            if e['why'] != 'UNEXPLAINED':
                cases[k] = e
                phases[e['why']] = phases.get(e['why'], 0) + 1
    for r in res:
        key = tuple(r['key']) if a.suite == 'rimtrap' else r['key']
        b, n = B[key], N[key]
        # the replays must reproduce the recorded end states (rimtrap: state at frame 120 / off map; embed: state120)
        rb, rn = (b[2], n[2]) if a.suite == 'rimtrap' else (b['state120'], n['state120'])
        repro = r['end'][0] == rb and r['end'][1] == rn
        hc = repro and r.get('phase') == 'physics' and r.get('same_before') and r['hostDist'] <= 1e-6
        ec = repro and r.get('phase') == 'portal' and r.get('same_before') and r.get('energyCap')
        ok = hc or ec
        why = 'host-contact-physics' if hc else 'blocked-bounce-energy-cap' if ec else 'UNEXPLAINED'
        phases[why] = phases.get(why, 0) + 1
        ent = {'base': b, 'new': n, 'frame': r['frame'], 'step': r.get('step'), 'phase': r.get('phase'), 'hostDist': r.get('hostDist'),
               'lineDist': r.get('lineDist'), 'why': why}
        if not repro: ent['replayEnd'] = r['end']
        sk = '|'.join(map(str, key)) if a.suite == 'rimtrap' else key
        cases[sk] = ent
        if not ok: unexplained.append(dict(ent, key=sk, detail={k: r.get(k) for k in ('before', 'mid', 'after', 'counters')}))
    doc = {'suite': a.suite, 'base': os.path.relpath(a.base, REPO), 'baseSha256': sha(a.base), 'new': os.path.relpath(a.new, REPO),
           'newSha256': sha(a.new), 'headRoot': os.path.relpath(a.head_root, REPO), 'changed': len(cases),
           'recheckOf': os.path.relpath(a.recheck, REPO) if a.recheck else None, 'replayed': len(keys), 'classes': phases,
           'unexplained': unexplained[:200], 'cases': cases}
    json.dump(doc, open(a.out, 'w'), separators=(',', ':'))
    write_allowlist(a, cases, sha)
    print('suite=%s changed=%d replayed=%d classes=%s unexplained=%d' % (a.suite, len(cases), len(keys), phases, len(unexplained)))
    return 1 if unexplained else 0

if __name__ == '__main__':
    sys.exit(main())
