#!/usr/bin/env python3
"""Visual test harness for Ball physics.

Opens index.html via file:// in a Chromium viewport (default 1280x800, see
--viewport) and runs named scenarios. Each scenario starts from a fresh page load.
Scenario coordinates are logical game coordinates (GAME_W x GAME_H = 1280x800);
click()/move() convert them to client coordinates through the letterboxed
canvas' getBoundingClientRect(), so every scenario runs unchanged at any
viewport (identity at 1280x800).

Usage:
  python3 tests/visual/shoot.py --task TASK-NNN [--scenarios a,b,...] [--eval JS] [--viewport WxH] [--dpr N]

Writes artifacts/TASK-NNN/<scenario>.png and artifacts/TASK-NNN/run.json.
--eval JS is evaluated after the scenario actions (before the state snapshot
and the screenshot); its JSON-serialisable result is stored under "eval".
Exit code is non-zero if any scenario throws or logs a console error.
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URL = 'file://' + os.path.join(ROOT, 'index.html')
VIEWPORT = {'width': 1280, 'height': 800}

STATE_JS = """() => ({thisLevel, physics, drawMenu, levelCompletedWindow, linesK,
    nLines: lines.length, ball: [ball.posX, ball.posY]})"""

# Candidate segments for the 'placed' scenario; the first is the ticket's
# default, the rest are fallbacks if the game rejects a placement.
SEGMENTS = [
    ((430, 432), (650, 488)),
    ((500, 600), (750, 650)),
    ((600, 200), (850, 260)),
    ((150, 650), (400, 700)),
]


def frames(page, n=2):
    page.evaluate("n => new Promise(r => { const f = k => k <= 0 ? r() : requestAnimationFrame(() => f(k - 1)); f(n) })", n)


TO_CLIENT_JS = """([x, y]) => { const r = canvas.getBoundingClientRect();
    return [Math.round(r.left + x * r.width / GAME_W), Math.round(r.top + y * r.height / GAME_H)] }"""


def to_client(page, x, y):
    """Logical game coordinates -> client (CSS) coordinates of the scaled canvas, rounded to whole
    pixels (MouseEvent.clientX/Y are integers; rounding keeps the error <= 0.5 client px)."""
    return page.evaluate(TO_CLIENT_JS, [x, y])


def click(page, x, y):
    cx, cy = to_client(page, x, y)
    page.mouse.click(cx, cy)
    frames(page)


def move(page, x, y):
    cx, cy = to_client(page, x, y)
    page.mouse.move(cx, cy)


def sc_start(page, info):
    frames(page)


def sc_level3(page, info):
    page.evaluate("() => { thisLevel = 2; levelChoosed(2) }")
    frames(page)


def sc_drawing(page, info):
    sc_level3(page, info)
    (x1, y1), (x2, y2) = SEGMENTS[0]
    click(page, x1, y1)
    move(page, x2, y2)
    frames(page)
    info['segment'] = [x1, y1, x2, y2]


def sc_placed(page, info):
    sc_level3(page, info)
    before = page.evaluate("lines.length")
    for (x1, y1), (x2, y2) in SEGMENTS:
        click(page, x1, y1)
        move(page, x2, y2)
        frames(page)
        click(page, x2, y2)
        if page.evaluate("lines.length") == before + 1 and not page.evaluate("!!line"):
            info['segment'] = [x1, y1, x2, y2]
            return
        info.setdefault('rejected', []).append([x1, y1, x2, y2])
        # Reset the level so the next attempt starts clean.
        page.evaluate("() => { line = false; levelChoosed(thisLevel) }")
        frames(page)
    raise RuntimeError('no segment could be placed')


def sc_running(page, info):
    sc_placed(page, info)
    x, y = page.evaluate("[menuIconRect[0][0] - 73 + 31, menuIconRect[0][1] + 31]")
    click(page, x, y)
    page.wait_for_timeout(1000)


def sc_menu(page, info):
    frames(page)
    x, y = page.evaluate("[menuIconRect[0][0] + 31, menuIconRect[0][1] + 31]")
    click(page, x, y)


def open_menu(page):
    x, y = page.evaluate("[menuIconRect[0][0] + 31, menuIconRect[0][1] + 31]")
    click(page, x, y)


def sc_menu_restart(page, info):
    # Place a line on level3 first so the restart has something to reset.
    sc_placed(page, info)
    open_menu(page)
    info['before'] = page.evaluate("({thisLevel, linesK, drawMenu, nLines: lines.length})")
    # Centre of the 'restart' button rect, from the same expressions the click handler uses (i = 1).
    x, y = page.evaluate("""[menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2,
        menuCoords[1] + 300 + 1 * 85 + menuTextRect[1] / 2]""")
    info['click'] = [x, y]
    click(page, x, y)


def sc_menu_level(page, info):
    frames(page)
    # Every level is open from the start (js/levels.js), so level 2's square is clickable as is.
    open_menu(page)
    info['before'] = page.evaluate("({thisLevel, drawMenu})")
    # Centre of level square 2 (i = 1), same expressions as levelsRectCollision().
    x, y = page.evaluate("""[menuCoords[0] + rectMarginLeft + (rectMarginLeft + rectSize) * 1 + rectSize / 2,
        menuCoords[1] + rectMarginTop + rectSize / 2]""")
    info['click'] = [x, y]
    click(page, x, y)


def sc_complete(page, info):
    frames(page)
    page.evaluate("() => { levelCompletedWindow = true }")
    frames(page)


def sc_complete_next(page, info):
    # Level index 0 with the level-complete window open, then click the centre of the
    # 'next level' rect, from the same expressions the click handler uses (blocks[1]).
    sc_complete(page, info)
    info['before'] = page.evaluate("({thisLevel, levelCompletedWindow})")
    x, y = page.evaluate("""[menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2,
        menuCoords[1] + blocks[1] + menuTextRect[1] / 2]""")
    info['click'] = [x, y]
    click(page, x, y)


def sc_complete_last(page, info):
    # Last level: the window shows 'Thanks for playing!' instead of the next-level button.
    frames(page)
    page.evaluate("() => { thisLevel = levels.length - 1; levelChoosed(thisLevel); levelCompletedWindow = true }")
    frames(page)


def sc_resized(page, info):
    # Start screen, then grow the window; fitCanvas() re-fits the letterboxed canvas.
    frames(page)
    page.set_viewport_size({'width': 1600, 'height': 1000})
    frames(page, 3)
    info['viewport'] = [1600, 1000]
    info['canvasRect'] = page.evaluate(
        "() => { const r = canvas.getBoundingClientRect(); return [r.left, r.top, r.width, r.height] }")


def sc_editor(page, info):
    # Pause menu -> 'editor' button -> toolbar 'exit', all real clicks.
    frames(page)
    open_menu(page)
    x, y = page.evaluate("(() => { const r = editorButtonRect(); return [r[0] + r[2] / 2, r[1] + r[3] / 2] })()")
    click(page, x, y)
    info['opened'] = page.evaluate("({editorMode, drawMenu})")
    if info['opened']['editorMode'] is not True:
        raise RuntimeError('editor button did not open the editor: %s' % info['opened'])
    x, y = page.evaluate("(() => { const b = EDITOR_BUTTONS.find(b => b.id == 'exit'); return [b.x + b.w / 2, b.y + b.h / 2] })()")
    click(page, x, y)
    info['exited'] = page.evaluate("({editorMode, drawMenu})")
    if info['exited'] != {'editorMode': False, 'drawMenu': False}:
        raise RuntimeError('toolbar exit did not close the editor: %s' % info['exited'])


TRAIL_COUNTER_JS = """() => { window.__trailPhysFrames = 0; window.__trailFrame0 = trailFrame;
    const g = gameMechanics;
    gameMechanics = function() { if (physics && !editorMode) ++window.__trailPhysFrames; return g() } }"""

TRAIL_STOP_JS = """() => { physics = false; const s = trailSamples();
    return {physicsFrames: window.__trailPhysFrames, trailFrameDelta: trailFrame - window.__trailFrame0,
        trailSamples: s.length, trailFinite: s.every(p => Number.isFinite(p.x) && Number.isFinite(p.y)),
        trailFrame: trailFrame, trailMax: TRAIL_MAX} }"""


def sc_trail(page, info):
    # Exact trail rule: one sample per frame while physics is on, none while it is off.
    # An in-page wrapper on the global gameMechanics counts the frames that run with physics on;
    # physics is stopped in the same evaluate that reads the counter, so no frame slips in between.
    sc_placed(page, info)
    page.evaluate(TRAIL_COUNTER_JS)
    x, y = page.evaluate("[menuIconRect[0][0] - 73 + 31, menuIconRect[0][1] + 31]")
    click(page, x, y)
    page.wait_for_timeout(1000)
    t = page.evaluate(TRAIL_STOP_JS)
    frames(page, 10)
    p = page.evaluate("() => ({trailFrame: trailFrame, trailSamples: trailSamples().length})")
    paused = (p['trailFrame'] - t['trailFrame']) + abs(p['trailSamples'] - t['trailSamples'])
    for k in ('physicsFrames', 'trailFrameDelta', 'trailSamples', 'trailFinite'):
        info[k] = t[k]
    info['pausedDelta'] = paused
    bad = []
    if t['physicsFrames'] < 10:
        bad.append('too few physics frames')
    if t['trailFrameDelta'] != t['physicsFrames']:
        bad.append('trailFrame delta != physics frames')
    if t['trailSamples'] != min(t['physicsFrames'], t['trailMax']):
        bad.append('samples != min(physics frames, TRAIL_MAX)')
    if not t['trailFinite']:
        bad.append('non-finite sample')
    if paused:
        bad.append('trail recorded while physics is off')
    if bad:
        raise RuntimeError('trail check failed (%s): %s paused=%s' % ('; '.join(bad), t, p))


def sc_touch_line(page, info):
    # Tap-tap line on a touch page (TASK-021 path): tap the segment start, then its end.
    sc_level3(page, info)
    before = page.evaluate("lines.length")
    (x1, y1), (x2, y2) = SEGMENTS[0]
    page.touchscreen.tap(*to_client(page, x1, y1))
    frames(page)
    page.touchscreen.tap(*to_client(page, x2, y2))
    frames(page)
    after = page.evaluate("({n: lines.length, linesK})")
    info['touch'] = {'before': before, 'after': after['n'], 'linesK': after['linesK']}
    if after['n'] != before + 1 or after['linesK'] != 1:
        raise RuntimeError('tap-tap did not place one line: %s' % info['touch'])


# Level 11 reference solution (TASK-068): one player line from LEVEL11_LINE[0] to [1]. The ball
# rolls off its lower end onto portal A (floor y = 600, front up), leaves B (wall x = 1040, front +x)
# into the flag pocket. Searched headlessly; 80 of 81 lines with each end moved by -4/0/+4 px also win.
LEVEL11_LINE = ((100, 180), (580, 450))
LEVEL11_MAX_FRAMES = 3000

# Level 12 'understanding portals' reference solution (TASK-073): one player line (lineK 1), a
# deflector above pad A (raised to y = 310 by TASK-073). The ball drops into portal B (pad y = 510),
# leaves portal A moving up, bounces off the line up-left and flies into the flag (1 B -> A teleport,
# completed on physics frame ~70). Searched headlessly with in-page stepped frames; 14 of 81 lines with
# each coordinate moved by -3/0/+3 px also win, so keep these exact integer coordinates.
LEVEL12_LINE = ((312, 214), (388, 240))
LEVEL12_MAX_FRAMES = 3000

# Level 13 'accelerator' reference solution (TASK-074; was TASK-071's (394,678)-(710,752) + (663,202)-(594,249),
# which stopped winning once portal edges capture by touch): two player lines (lineK 4). The ramp under
# the ball rolls it right onto floor portal A; it loops A -> B (shelf underside) twice, gaining speed,
# and the second line (589,381)-(712,393), left of the shelf, kicks it up-left into the flag (completed
# on physics frame 262). Searched headlessly with in-page stepped frames (artifacts/TASK-074/design.md);
# 14 of 17 single-coordinate +-3 px variants also win, but keep these exact integer coordinates.
LEVEL13_LINES = (((381, 679), (696, 744)), ((589, 381), (712, 393)))
LEVEL13_MAX_FRAMES = 3000

# Level 14 (index 13) solution: one long ramp under the ball. The ball rolls down it into portal A, comes out of B
# 152 px higher still moving right, lands on the ramp again, and after the second A -> B teleport it has enough
# speed to clear wall A and hit the flag (won on physics frame 441). Searched headlessly with in-page stepped
# frames (artifacts/TASK-077/design.md); 11 of 24 single-coordinate +-1..3 px variants also win, keep these exact
# integer coordinates.
LEVEL14_LINE = ((183, 580), (779, 608))
LEVEL14_MAX_FRAMES = 3000

# Level 15 (index 14) solution: one short ramp under the ball rising to the right. The ball lands on it, rolls
# down-left, flies into portal B (an upright pad at the bottom left facing right, TASK-099) and comes out of A on
# the wall's right face rising to the right, straight into the flag (won on physics frame 83). Found by a lattice
# search with in-page stepped frames (artifacts/TASK-099/design.md); all 8 single-coordinate +-3 px variants also win.
LEVEL15_LINE = ((460, 580), (620, 380))
LEVEL15_MAX_FRAMES = 3000

# Level 16 (index 15) solution: one line under the ball sloping down to the left, ending just above portal B.
# The ball rolls down it into B (on the short wall at the bottom left, facing right), comes out of A (the floor pad,
# facing up) moving up-left, bounces off the right face of the tall wall x=312, flies right onto the sloped ramp and
# bounces straight up into the flag (won on physics frame 147). Found by a focused lattice + dense local search with
# in-page stepped frames (artifacts/TASK-100/search.log); the layout is unchanged. Keep these exact integer coordinates.
LEVEL16_LINE = ((96, 636), (299, 346))
LEVEL16_MAX_FRAMES = 3000

# Level 17 (index 16) solution: one long ramp under the ball sloping down to the right towards portal A (on the outer,
# left face of the flag box wall x=1091). The ball rolls off its low end into A, comes out of B (the pad on the left,
# facing up) 220 px higher, arcs over the wall x=308, bounces on the ramp and the box wall, rises through the gap above
# the box wall (y < 245) and drops onto the flag (won on physics frame 273, one A->B teleport). Found by a lattice
# search with in-page stepped frames (artifacts/TASK-101/search.log); the layout is unchanged. 6 of the 8
# single-coordinate +-2 px variants also win. Keep these exact integer coordinates.
LEVEL17_LINE = ((320, 280), (1060, 620))
LEVEL17_MAX_FRAMES = 3000

# Counts game frames that run physics and remembers the frame on which the level was completed.
LEVEL11_COUNTER_JS = """() => { window.__l11Frames = 0; window.__l11Win = null;
    const g = gameMechanics;
    gameMechanics = function() { const on = physics && !editorMode; const r = g();
        if (on) { ++window.__l11Frames;
            if (levelCompletedWindow && window.__l11Win === null) window.__l11Win = window.__l11Frames }
        return r } }"""


def play_solution(page, info, index, segments, max_frames, key, via=('A', 'B')):
    # Pause menu -> level square index + 1, real clicks; then play the solution with real mouse
    # input: draw each line (click, move, click), press start (unless the last allowed line already
    # started physics), and wait until the level is completed
    # (at most max_frames physics frames) with at least one via[0] -> via[1] teleport.
    frames(page)
    open_menu(page)
    x, y = page.evaluate("i => { const r = levelRectXY(i); return [r[0] + rectSize / 2, r[1] + rectSize / 2] }", index)
    click(page, x, y)
    st = page.evaluate("({thisLevel, drawMenu, portals: (curLevel().portals || []).length})")
    info[key] = st
    if st != {'thisLevel': index, 'drawMenu': False, 'portals': 2}:
        raise RuntimeError('%s not loaded: %s' % (key, st))
    n0 = page.evaluate("lines.length")
    # installed before drawing: physics is off until the start (or the last allowed line), so the
    # counter starts with the first physics frame either way
    page.evaluate(LEVEL11_COUNTER_JS)
    for (x1, y1), (x2, y2) in segments:
        click(page, x1, y1)
        move(page, x2, y2)
        frames(page)
        click(page, x2, y2)
    drawn = page.evaluate("""n0 => ({added: lines.length - n0, linesK, lineK: curLevel().lineK, pending: !!line,
        physics, lines: lines.slice(n0).map(l => [l.posX, l.posY, l.posX2, l.posY2])})""", n0)
    if len(segments) == 1:  # level 11 record shape (TASK-068)
        drawn['line'] = drawn['lines'][0]
    info['drawn'] = drawn
    want = [[x1, y1, x2, y2] for (x1, y1), (x2, y2) in segments]
    off = drawn['added'] != len(segments) or any(abs(a - b) > 1 for l, w in zip(drawn['lines'], want) for a, b in zip(l, w))
    # placing the last allowed line starts physics by itself (index.html click handler)
    auto = drawn['linesK'] >= drawn['lineK']
    if off or drawn['pending'] or drawn['physics'] != auto:
        raise RuntimeError('solution lines not placed: %s' % drawn)
    if auto:  # already running; the start button would pause it
        info['autoStarted'] = page.evaluate("({physics, levelStarted})")
    else:
        x, y = page.evaluate("[menuIconRect[0][0] - 73 + 31, menuIconRect[0][1] + 31]")
        click(page, x, y)
        info['startPressed'] = page.evaluate("({physics, levelStarted})")
    page.wait_for_function("levelCompletedWindow || window.__l11Frames >= %d" % max_frames,
                           timeout=180000, polling=100)
    r = page.evaluate("""i => ({levelCompleted: levelCompletedWindow, winFrame: window.__l11Win,
        frames: window.__l11Frames, unlock: levels[i].unlock, ball: [ball.posX, ball.posY],
        teleports: portalState.teleports.map(t => ({step: t.step, from: t.from, to: t.to,
            before: t.before, after: t.after}))})""", index)
    info['play'] = r
    ab = [t for t in r['teleports'] if t['from'] == via[0] and t['to'] == via[1]]
    if not (r['levelCompleted'] and r['winFrame'] is not None and r['winFrame'] <= max_frames and ab):
        raise RuntimeError('%s not won with a %s->%s teleport: %s' % (key, via[0], via[1], {k: r[k] for k in (
            'levelCompleted', 'winFrame', 'frames', 'ball')}))
    # a fresh draw after the win so the screenshot shows the completed-level panel
    frames(page)


def sc_level11(page, info):
    play_solution(page, info, 10, [LEVEL11_LINE], LEVEL11_MAX_FRAMES, 'level11')


def sc_level12(page, info):
    play_solution(page, info, 11, [LEVEL12_LINE], LEVEL12_MAX_FRAMES, 'level12', via=('B', 'A'))


def sc_level13(page, info):
    play_solution(page, info, 12, LEVEL13_LINES, LEVEL13_MAX_FRAMES, 'level13')


def sc_level14(page, info):
    play_solution(page, info, 13, [LEVEL14_LINE], LEVEL14_MAX_FRAMES, 'level14')


def sc_level15(page, info):
    play_solution(page, info, 14, [LEVEL15_LINE], LEVEL15_MAX_FRAMES, 'level15', via=('B', 'A'))


def sc_level16(page, info):
    play_solution(page, info, 15, [LEVEL16_LINE], LEVEL16_MAX_FRAMES, 'level16', via=('B', 'A'))


def sc_level17(page, info):
    play_solution(page, info, 16, [LEVEL17_LINE], LEVEL17_MAX_FRAMES, 'level17')


SCENARIOS = {
    'start': sc_start,
    'level3': sc_level3,
    'drawing': sc_drawing,
    'placed': sc_placed,
    'running': sc_running,
    'menu': sc_menu,
    'complete': sc_complete,
    'menu_restart': sc_menu_restart,
    'menu_level': sc_menu_level,
    'complete_next': sc_complete_next,
    'complete_last': sc_complete_last,
    'resized': sc_resized,
    'editor': sc_editor,
    'trail': sc_trail,
    'touch_line': sc_touch_line,
    'level11': sc_level11,
    'level12': sc_level12,
    'level13': sc_level13,
    'level14': sc_level14,
    'level15': sc_level15,
    'level16': sc_level16,
    'level17': sc_level17,
}

# Extra browser.new_page() options per scenario (the viewport stays the default/--viewport one).
PAGE_OPTIONS = {
    'touch_line': {'has_touch': True},
}


def run_scenario(browser, name, out_dir, eval_js, viewport=VIEWPORT, dpr=1):
    errors = []
    info = {}
    page = browser.new_page(viewport=viewport, device_scale_factor=dpr, **PAGE_OPTIONS.get(name, {}))
    page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
    entry = {'errors': errors}
    try:
        page.goto(URL)
        page.wait_for_load_state('load')
        frames(page)
        SCENARIOS[name](page, info)
        if eval_js:
            entry['eval'] = page.evaluate(
                "async js => JSON.parse(JSON.stringify(await (0, eval)(js)) ?? 'null')", eval_js)
            frames(page)
        entry['state'] = page.evaluate(STATE_JS)
        page.screenshot(path=os.path.join(out_dir, name + '.png'))
    except Exception as e:  # recorded as an error -> non-zero exit
        errors.append('exception: %s: %s' % (type(e).__name__, str(e).splitlines()[0] if str(e) else ''))
    finally:
        page.close()
    entry.update(info)
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--scenarios', default=','.join(SCENARIOS), help='default: every scenario')
    ap.add_argument('--eval', dest='eval_js')
    ap.add_argument('--viewport', default='%dx%d' % (VIEWPORT['width'], VIEWPORT['height']),
                    help='browser viewport WxH (default 1280x800)')
    ap.add_argument('--dpr', type=float, default=1, help='device_scale_factor (default 1)')
    args = ap.parse_args()
    vw, vh = (int(v) for v in args.viewport.lower().split('x'))
    viewport = {'width': vw, 'height': vh}

    names = [s.strip() for s in args.scenarios.split(',') if s.strip()]
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        print('unknown scenarios: %s (known: %s)' % (unknown, ','.join(SCENARIOS)))
        return 2

    out_dir = os.path.join(ROOT, 'artifacts', args.task)
    os.makedirs(out_dir, exist_ok=True)

    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in names:
            entry = run_scenario(browser, name, out_dir, args.eval_js, viewport, args.dpr)
            result[name] = entry
            print('%-9s errors=%d state=%s%s' % (
                name, len(entry['errors']), json.dumps(entry.get('state'), separators=(',', ':')),
                (' eval=' + json.dumps(entry['eval'], separators=(',', ':'))[:300]) if 'eval' in entry else ''))
            for e in entry['errors']:
                print('   ', e)
        browser.close()

    with open(os.path.join(out_dir, 'run.json'), 'w') as f:
        json.dump(result, f, separators=(',', ':'))

    failed = [n for n, e in result.items() if e['errors']]
    print('FAILED: ' + ','.join(failed) if failed else 'OK: %d scenarios' % len(result))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
