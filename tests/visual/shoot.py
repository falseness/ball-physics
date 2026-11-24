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
    # level 3 by source id (TASK-177: play order != definition order; levelBySrc maps srcId -> index)
    page.evaluate("() => { thisLevel = levelBySrc(3); levelChoosed(thisLevel) }")
    info['srcId'] = page.evaluate("levels[thisLevel].srcId")
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


# TASK-181: the pause menu's 'Levels' button (i = 2, same rect expressions as the click handler) opens the route map;
# a level is picked by clicking the centre of its slot hit box (routeLevelPoint -> routeSlotBox, js/routemap.js).
LEVELS_BUTTON_JS = """[menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2,
    menuCoords[1] + 300 + 2 * 85 + menuTextRect[1] / 2]"""
LEVEL_POINT_JS = "i => routeLevelPoint(levels, i)"


def open_map(page):
    # pause menu (HUD menu icon) -> 'Levels' button, real clicks
    open_menu(page)
    click(page, *page.evaluate(LEVELS_BUTTON_JS))
    if not page.evaluate("drawMap"):
        raise RuntimeError('Levels button did not open the route map')


def pick_level(page, i):
    # menu -> 'Levels' -> the level's slot on the map (real clicks); returns the clicked point. TASK-182: the first
    # click selects the level (preview card), the second click on the selected level starts it.
    open_map(page)
    pt = page.evaluate(LEVEL_POINT_JS, i)
    if pt is None:
        raise RuntimeError('level index %s has no slot on the route map' % i)
    click(page, *pt)
    if page.evaluate("mapSel") != i or not page.evaluate("drawMap"):
        raise RuntimeError('first click on level %s did not select it on the map' % i)
    click(page, *pt)
    return pt


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
    # Every level is open from the start (js/levels.js). TASK-181: menu -> 'Levels' -> route map -> level 2's slot
    # (i = 1, centre of its routeSlotBox hit box).
    open_map(page)
    info['before'] = page.evaluate("({thisLevel, drawMenu, drawMap})")
    x, y = page.evaluate(LEVEL_POINT_JS, 1)
    info['click'] = [x, y]
    click(page, x, y)  # TASK-182: the first click selects level 2 (preview card), the second click starts it
    info['selected'] = page.evaluate("({thisLevel, drawMap, mapSel, card: window.mapCard && window.mapCard.i})")
    if info['selected'] != {'thisLevel': 0, 'drawMap': True, 'mapSel': 1, 'card': 1}:
        raise RuntimeError('menu_level: first click did not select level 2: %s' % info['selected'])
    click(page, x, y)
    info['after'] = page.evaluate("({thisLevel, drawMenu, drawMap, levelCompletedWindow})")
    if info['after'] != {'thisLevel': 1, 'drawMenu': False, 'drawMap': False, 'levelCompletedWindow': False}:
        raise RuntimeError('menu_level: level 2 not started from the map: %s' % info['after'])


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


def sc_next_level_order(page, info):
    # TASK-177 play order: win level 2 (srcId 2), then click 'next level' -> the first portal level (srcId 11).
    # Menu -> level square of srcId 2 (real click); the win is real game physics: the ball is put on the flag and
    # physics is turned on, so gameMechanics' flagCollision opens the level-complete window. Then a real click
    # on the 'next level' rect (same expressions as the click handler, blocks[1]).
    frames(page)
    i2 = page.evaluate("levelBySrc(2)")
    pick_level(page, i2)
    info['level2'] = page.evaluate("({thisLevel, srcId: levels[thisLevel].srcId, drawMenu})")
    if info['level2'] != {'thisLevel': i2, 'srcId': 2, 'drawMenu': False}:
        raise RuntimeError('level 2 not loaded: %s' % info['level2'])
    page.evaluate("() => { const L = curLevel(); ball.posX = L.flagX; ball.posY = L.flagY; physics = true }")
    page.wait_for_function("levelCompletedWindow", timeout=30000, polling=50)
    info['won'] = page.evaluate("({levelCompletedWindow, thisLevel, unlock: levels[thisLevel].unlock})")
    frames(page)
    x, y = page.evaluate("""[menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2,
        menuCoords[1] + blocks[1] + menuTextRect[1] / 2]""")
    info['click'] = [x, y]
    click(page, x, y)
    frames(page)
    a = page.evaluate("""({thisLevel, srcId: levels[thisLevel].srcId, srcAt2: levels[2].srcId,
        levelCompletedWindow, portals: (curLevel().portals || []).length})""")
    info['after'] = a
    if not (a['thisLevel'] == 2 and a['srcAt2'] == 11 and a['srcId'] == 11 and not a['levelCompletedWindow']):
        raise RuntimeError('next level order wrong: %s' % a)


# TASK-178 saved progress. Each scenario also writes its own compact JSON (PROGRESS_FILES) into the task dir.
PROGRESS_FILES = {'progress_reload': 'progress_reload.json', 'progress_storage_blocked': 'progress_blocked.json',
                  'progress_garbage': 'progress_garbage.json'}
# TASK-184: 'stored' is read through the platform facade (PLATFORM.storage.getMany); 'raw' is the backend's
# localStorage value ('THROWS' when blocked; the local backend then keeps the value in memory).
PROGRESS_STATE_JS = """async () => { let raw = null; try { raw = localStorage.getItem(PROGRESS_STORE) } catch (e) { raw = 'THROWS' }
    const stored = (await PLATFORM.storage.getMany([PROGRESS_STORE]))[PROGRESS_STORE]
    return {solved: progressSolved(), stored, raw, platformId: PLATFORM.getPlatformId(), bootComplete,
        nLevels: levels.length, thisLevel, physics, drawMenu, levelCompletedWindow} }"""
# Boot (index.html) finishes asynchronously: platform init + storage reads, then the first frame
BOOT_JS = "typeof bootComplete !== 'undefined' && bootComplete"
# Every level slot (TASK-181 route map): mapClick (the click handler's map path) at its hit box centre must start it
# (TASK-182: the first click selects the level and shows its card, the second click on it starts it).
CLICKABLE_JS = """() => { const out = []; for (let i = 0; i < levels.length; ++i) {
        mapOpen(); const p = routeLevelPoint(levels, i); if (p) { mapClick(p); mapClick(p) }
        out.push({i, srcId: levels[i].srcId, clickable: !!p && thisLevel === i && !drawMap}) }
    thisLevel = 0; levelChoosed(0); return out }"""
# Overrides localStorage get/set to throw (installed before any page script runs).
# Counts game-loop frames (gameLoop re-schedules itself by name, so the wrapper sees every frame).
LOOP_COUNTER_JS = """() => { if (window.__loopFrames === undefined) { window.__loopFrames = 0; const g = gameLoop;
    gameLoop = function() { ++window.__loopFrames; return g.apply(this, arguments) } } return window.__loopFrames }"""
STORAGE_THROW_JS = """(() => { const f = () => { throw new DOMException('blocked by test', 'SecurityError') };
    Storage.prototype.getItem = f; Storage.prototype.setItem = f })()"""


def progress_out(info, name, data):
    info['progress'] = data
    with open(os.path.join(OUT_DIR, PROGRESS_FILES[name]), 'w') as f:
        json.dump(data, f, separators=(',', ':'))


def win_level_src(page, src):
    # Menu -> 'Levels' -> map slot (real clicks); real win through gameMechanics' flagCollision (ball on the flag).
    i = page.evaluate("n => levelBySrc(n)", src)
    pick_level(page, i)
    st = page.evaluate("({thisLevel, srcId: levels[thisLevel].srcId, drawMenu})")
    if st != {'thisLevel': i, 'srcId': src, 'drawMenu': False}:
        raise RuntimeError('level %s not loaded: %s' % (src, st))
    page.evaluate("() => { const L = curLevel(); ball.posX = L.flagX; ball.posY = L.flagY; physics = true }")
    page.wait_for_function("levelCompletedWindow", timeout=30000, polling=50)
    frames(page, 5)
    return page.evaluate("i => ({levelCompletedWindow, thisLevel, srcId: levels[i].srcId, unlock: levels[i].unlock})", i)


def sc_progress_reload(page, info):
    frames(page)
    before = page.evaluate(PROGRESS_STATE_JS)
    won = win_level_src(page, 1)
    afterWin = page.evaluate(PROGRESS_STATE_JS)
    page.reload()  # same page / browser context: localStorage is kept
    page.wait_for_load_state('load')
    page.wait_for_function(BOOT_JS)
    frames(page, 3)
    restored = page.evaluate(PROGRESS_STATE_JS)
    restored['completedSrcIds'] = page.evaluate("levels.filter(l => l.unlock == 2).map(l => l.srcId)")
    clickable = page.evaluate(CLICKABLE_JS)
    open_map(page)  # screenshot: route map with level 1 completed (coral) after the reload
    allClickable = all(c['clickable'] for c in clickable)
    data = {'before': before, 'won': won, 'afterWin': afterWin, 'restored': restored,
            'restoredSolved': restored['solved'], 'contains1': 1 in restored['solved'],
            'clickableCount': sum(c['clickable'] for c in clickable), 'nLevels': len(clickable),
            'allClickable': allClickable, 'clickable': clickable}
    data['pass'] = bool(before['solved'] == [] and won['levelCompletedWindow'] and won['unlock'] == 2
                        and data['contains1'] and allClickable)
    progress_out(info, 'progress_reload', data)
    if not data['pass']:
        raise RuntimeError('progress_reload failed: %s' % {k: data[k] for k in ('restoredSolved', 'allClickable')})


def sc_progress_storage_blocked(page, info):
    # the init script is installed by run_scenario (PAGE_INIT) before page.goto
    frames(page)
    probe = page.evaluate("() => { try { localStorage.getItem('x'); return 'no throw' } catch (e) { return 'throws: ' + e.name } }")
    before = page.evaluate(PROGRESS_STATE_JS)
    won = win_level_src(page, 1)
    after = page.evaluate(PROGRESS_STATE_JS)
    # still running: the game loop keeps drawing frames after the win
    page.evaluate(LOOP_COUNTER_JS)
    frames(page, 10)
    f1 = page.evaluate("window.__loopFrames")
    f0 = 0
    data = {'storageProbe': probe, 'before': before, 'won': won, 'after': after,
            'frameCount': [f0, f1], 'gameRunning': f1 > f0}
    progress_out(info, 'progress_storage_blocked', data)  # consoleErrors added by run_scenario


def sc_progress_garbage(page, info):
    frames(page)
    st = page.evaluate(PROGRESS_STATE_JS)
    page.evaluate(LOOP_COUNTER_JS)
    frames(page, 10)
    f1 = page.evaluate("window.__loopFrames")
    f0 = 0
    data = {'storedRaw': st['stored'], 'state': st, 'solvedCount': len(st['solved']),
            'completedCount': page.evaluate("levels.filter(l => l.unlock == 2).length"),
            'frameCount': [f0, f1], 'gameRunning': f1 > f0}
    progress_out(info, 'progress_garbage', data)


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

# Level 14 (srcId 14) solution: one long ramp under the ball. The ball rolls down it into portal A, comes out of B
# 152 px higher still moving right, lands on the ramp again, and after the second A -> B teleport it has enough
# speed to clear wall A and hit the flag (won on physics frame 441). Searched headlessly with in-page stepped
# frames (artifacts/TASK-077/design.md); 11 of 24 single-coordinate +-1..3 px variants also win, keep these exact
# integer coordinates.
LEVEL14_LINE = ((183, 580), (779, 608))
LEVEL14_MAX_FRAMES = 3000

# Level 15 (srcId 15) solution (layout from artifacts/new_level15.json, TASK-113): one long line under the ball
# rising to the right and crossing the wall x=633. The ball lands on it, rolls down-left into portal B (the floor pad
# facing up), comes out of A on the wall's right face and reaches the flag (won on physics frame 175, one B->A
# teleport). Found by a lattice + random search with in-page stepped frames (artifacts/TASK-114/search.log); all 8
# single-coordinate and all 8 whole-line +-2 px variants also win. Keep these exact integer coordinates.
LEVEL15_LINE = ((207, 547), (1024, 437))
LEVEL15_MAX_FRAMES = 3000

# Level 16 (srcId 16) solution: one line under the ball sloping down to the left, ending just above portal B.
# The ball rolls down it into B (on the short wall at the bottom left, facing right), comes out of A (the floor pad,
# facing up) moving up-left, bounces off the right face of the tall wall x=312, flies right onto the sloped ramp and
# bounces straight up into the flag (won on physics frame 147). Found by a focused lattice + dense local search with
# in-page stepped frames (artifacts/TASK-100/search.log); the layout is unchanged. Keep these exact integer coordinates.
LEVEL16_LINE = ((96, 636), (299, 346))
LEVEL16_MAX_FRAMES = 3000

# Level 17 (srcId 17) solution: one long ramp under the ball sloping down to the right towards portal A (on the outer,
# left face of the flag box wall x=1091). The ball rolls off its low end into A, comes out of B (the pad on the left,
# facing up) 220 px higher, arcs over the wall x=308, bounces on the ramp and the box wall, rises through the gap above
# the box wall (y < 245) and drops onto the flag (won on physics frame 273, one A->B teleport). Found by a lattice
# search with in-page stepped frames (artifacts/TASK-101/search.log); the layout is unchanged. 6 of the 8
# single-coordinate +-2 px variants also win. Keep these exact integer coordinates.
LEVEL17_LINE = ((320, 280), (1060, 620))
LEVEL17_MAX_FRAMES = 3000

# Level 18 (srcId 18, lineK 2) solution: a ramp starting just under the ball and sloping down to the right into portal A
# (left face of the full-height wall x=640); B (right face of the pit wall x=1000) fires the ball down-right, away from
# the pit, onto a shallow second line right of the pit wall that bounces it back up-left over the wall x=1000 onto the
# flag (won on physics frame 150, one A->B teleport). Found with tools/level_search.py: a seed grid of second lines
# along the B exit path (--mode sample --around, +-6 px variants; artifacts/TASK-129/search_ref.json), then --mode local
# (+-2 px): 14 of the 16 single-coordinate variants also win (artifacts/TASK-129/local_ref.json).
# Keep these exact integer coordinates.
LEVEL18_LINES = [((130, 77), (630, 568)), ((1020, 768), (1189, 700))]
LEVEL18_MAX_FRAMES = 1500

# Level 19 (srcId 19, lineK 2) solution: a short ramp from under the ball down onto the right floor y=300 (the ball rolls
# off the floor's left end and drops under the middle shelf), and a "/" kicker below the shelf that bounces the ball up
# into portal A (the shelf's underside, facing down); B (left wall x=40, facing right) fires it up and over onto the flag
# shelf (won on physics frame 157, one A->B teleport). Found with tools/level_search.py's evaluate() (exploration wrapper
# artifacts/TASK-131/search/grid.py): the ramp fixed, every second line with both ends on a 30 px lattice under the
# shelf (x 250..700, y 480..800; artifacts/TASK-131/search_ref.json), then --mode local (+-2 px): all 16
# single-coordinate variants also win (artifacts/TASK-131/local_ref.json).
# Keep these exact integer coordinates.
LEVEL19_LINES = [((960, 270), (800, 296)), ((400, 690), (610, 660))]
LEVEL19_MAX_FRAMES = 1500

# Level 20 (srcId 20, lineK 3) solution: a short ramp from beside the ball onto the divider y=420 (the ball rolls off it
# and drops through the window x 480..800), a "/" ramp under the window that rolls the ball down-left into portal A
# (bottom pad, facing up), and a "\" deflector in B's exit stream that turns the leftward stream (B is on the right wall,
# facing left) back up through the same window onto the hanging flag (won on physics frame 183, one A->B teleport).
# Found with tools/level_search.py's evaluate() (exploration wrapper artifacts/TASK-133/search/grid.py): lines 1-2
# from a 270-pair feed grid (search/r2.json), then every third line with both ends on a 40 px lattice under the
# divider (x 500..1000, y 460..780, length 40..260; artifacts/TASK-133/search_ref.json: 49 wins), then --mode local
# (+-2 px): 22 of the 24 single-coordinate variants also win (artifacts/TASK-133/local_ref.json).
# Keep these exact integer coordinates.
LEVEL20_LINES = [((260, 395), (460, 420)), ((560, 460), (240, 760)), ((660, 500), (820, 580))]
LEVEL20_MAX_FRAMES = 1500

# Level 21 (srcId 21, lineK 2) solution: a shallow ramp from just under the resting ball down-left off its pad (the ball
# rolls off the ramp's left end moving left), and a steep "\" bank line below it that throws the falling ball back
# down-right, head-on into portal A (cut into the 45-degree slope, facing up-left), so B (pad on the left, facing up)
# fires it straight up into the hanging flag (won on physics frame 162, one A->B teleport).
# Found with tools/level_search.py's evaluate() (exploration wrapper artifacts/TASK-135/search/grid.py): line 1 fixed,
# every second line with both ends on a 40 px lattice (x 240..720, y 360..720, length 40..260;
# artifacts/TASK-135/search_ref.json: 55 wins of 4913; it was picked by a --mode local (+-2 px) scan of the wins of the
# first layout, artifacts/TASK-135/iter1), then --mode local on the final layout: 15 of the 16 single-coordinate variants
# win (artifacts/TASK-135/local_ref.json). Keep these exact integer coordinates.
LEVEL21_LINES = [((930, 312), (700, 360)), ((440, 440), (520, 680))]
LEVEL21_MAX_FRAMES = 1500

# Level 22 (srcId 22, lineK 3) solution: a shallow ramp from just left of the resting ball rolls it off its pad; it
# bounces between the long third line and the second line down into portal A (floor pad, facing up); B (right wall,
# 200 px higher, facing left) fires it left onto the second line, which rolls it back into A for a second lap; the
# faster ball out of B then flies up-left in a high arc, lands on line 1's right part under the shield wall and is
# thrown up past the shield's lower end into the corner flag (won on physics frame 416, teleports A->B, A->B).
# Found with tools/level_search.py's evaluate() (exploration wrapper artifacts/TASK-137/search/grid.py): line 1 fixed,
# second lines on a 40 px lattice under B's stream (85 two-lap A->B,A->B routes), then the 2 closest losing pairs with
# every third line on an 80 px lattice in the left half (artifacts/TASK-137/search_ref.json: 19 wins of 1791 including
# the reference row), then two --mode local (+-2 px) hill-climb steps for robustness. TASK-138 added the sloped roof
# over the start pad (it stopped 2-line wins off the pad); on that final layout 14 of the 24 single-coordinate +-2 px
# variants win (artifacts/TASK-138/g3_local.json). Keep these exact integer coordinates.
LEVEL22_LINES = [((150, 413), (420, 470)), ((1140, 660), (640, 760)), ((720, 482), (60, 540))]
LEVEL22_MAX_FRAMES = 1500

# Level 23 (srcId 23, lineK 2) solution: the ball rolls off its start slope; line 1 is a kicker under the slope's end
# (rising to the right) that throws it up and over the trap portal B in the floor (going in through B would drop it
# out of the lower portal A and lose height); it flies off the floor's open right end, falls onto line 2, a
# reflector under that end rising to the right, which sends it back left into A (low wall, facing right); B fires it
# straight up into the flag hanging high above B (won on physics frame 236, one teleport A->B).
# Found with tools/level_search.py's evaluate() (exploration wrapper artifacts/TASK-141/search/grid.py): first lines
# as kickers / slope extensions near the slope's end with 6 random second lines each, then the 15 most promising
# first lines with every second line of a reflector lattice under the floor's right end
# (artifacts/TASK-141/search_ref.json: 52 wins of 7410); 16 of the 16 single-coordinate +-2 px variants win
# (artifacts/TASK-141/local_ref.json). Keep these exact integer coordinates.
LEVEL23_LINES = [((330, 425), (450, 395)), ((880, 760), (1060, 580))]
LEVEL23_MAX_FRAMES = 1500

# Level 24 (srcId 24, lineK 3) solution: line 1 is a long, almost flat line over the start pad that rolls the ball
# off the pad and carries it right, past portal A (rolled straight off the pad it would drop onto A's left half and,
# mirrored, leave B in the lower lane, the tunnel); it falls onto line 2, a steep backboard right of A, which banks it
# back left under the small roof into A's RIGHT half, so B (mirrored offset) lets it out in the upper lane, above the
# shelf; line 3, a near-vertical reflector right of the flag pocket, sends it back left into the pocket (won on
# physics frame 283, one teleport A->B).
# Found with an exploration wrapper (artifacts/TASK-143/search/lane.py, same handleClick placement as
# tools/level_search.py): release lines over the pad, then a lattice of backboards (exit y < 360 = upper lane),
# then a lattice of third lines right of the pocket (artifacts/TASK-143/search_ref.json: 29 wins of 590);
# 15 of the 24 single-coordinate +-2 px variants win (artifacts/TASK-143/local_ref.json). Keep these exact
# integer coordinates.
LEVEL24_LINES = [((170, 476), (620, 513)), ((790, 610), (730, 714)), ((1000, 140), (1024, 278))]
LEVEL24_MAX_FRAMES = 1500

# Level 25 ('skim, don't drop', srcId 25, lineK 2): line 1, an almost flat kicker in the well under the start slope,
# throws the falling ball up and over the crest wall (x = 840, top y = 450) into A's pocket; line 2, a ~42 deg
# converter slope in the pocket, turns its steep (~75 deg) fall into a flat skim (0.041, 0.010 px/cycle) into floor
# portal A, so B on the right-edge wall lets it out going straight up the chimney to the flag (won on physics frame
# 153, one teleport A->B). Found with a hand-aimed scan (3 kickers x 60 converters at 38..50 deg around the kicker's
# landing point; artifacts/TASK-145/search/cv21.json re-evaluated with tools/level_search.py's evaluate() on the
# committed level 25 (srcId 25): 19 of 180 win, artifacts/TASK-145/search_ref.json); 13 of the 17 local +-2 px variants win.
# Keep these exact integer coordinates.
LEVEL25_LINES = [((535, 597), (635, 603)), ((920, 693), (980, 747))]
LEVEL25_MAX_FRAMES = 1500

# Level 26 ('one line, two jobs', srcId 26, lineK 4): line 1 tips the ball off its pad to the left; line 2, a long
# ramp under the pad's open side, carries the falling ball right to the shaft; line 3, a near-vertical backboard at
# the shaft (its right wall is too low), drops it steeply into floor portal A; B on the short right wall lets it out
# almost flat to the left, back over line 2, which it hits going the other way and bounces up-left off; line 4 at
# the left edge turns the rising ball right into the flag's pocket (won on physics frame 312, one teleport A->B).
# Found with exploration scans (artifacts/TASK-147/search/scan.py, same handleClick placement as
# tools/level_search.py): a lattice of ramps x backboards with a fixed release line, then reflectors at the left edge
# (artifacts/TASK-147/search_ref.json); keep these exact integer coordinates.
LEVEL26_LINES = [((230, 286), (90, 300)), ((20, 480), (700, 580)), ((860, 550), (868, 765)), ((15, 240), (15, 390))]
LEVEL26_MAX_FRAMES = 1500
# Level 27 ('side door', TASK-149, lineK 3; reference solution): line 1 is a tilted kicker inside the well, below
# portal A. The ball bouncing straight up and down bounces off it sideways and, on its way up, drifts into the left
# wall at A's depth, so A takes it. Out of B (floating pad, facing down) it heads down and to the right, line 2 lifts it
# up-right through the gap right of the flag pocket's floor, and line 3 at the right edge turns it back left into the pocket
# (won on physics frame 193 on the TASK-150 layout, one teleport A->B). Lines 2 and 3 were re-searched in TASK-150 for the
# reworked walls (artifacts/TASK-150/iterations.md, reference R3); keep these exact integer coordinates.
LEVEL27_LINES = [((530, 720), (630, 740)), ((1000, 660), (1213, 603)), ((1265, 290), (1265, 370))]
LEVEL27_MAX_FRAMES = 1500
# Level 28 ('wrap-around', TASK-151, lineK 2; reference solution): line 1 is a long ramp from the ball's pad down to
# the left edge; the bouncing ball lands on it, rolls down-left and flies off the left edge into portal A. A and B
# face each other across the whole field at the same height, so the ball comes back in through B on the right edge
# still moving left. Line 2 in the right half turns it around and throws it up-right into the flag's pocket, which is
# open only on its left side (won on physics frame 225, one teleport A->B). Found with a two-stage scan
# (artifacts/TASK-151/search/probe.py: 2240 ramps, then line 2 on a 50 px lattice for 4 of the 146 ramps that reach A;
# artifacts/TASK-151/search_ref.json); keep these exact integer coordinates.
LEVEL28_LINES = [((550, 255), (40, 570)), ((850, 660), (950, 560))]
LEVEL28_MAX_FRAMES = 1500
# Level 29 ('echo', TASK-153, lineK 3; reference solution): line 1 knocks the ball, which bounces in place on its pad,
# to the left over tower A's top (through the flag's shadow). Line 2 left of tower A turns it back to the right into
# portal A. A and B face the same way, so the ball comes out of B replaying its path backwards, moved by (560, -200).
# Line 3 is line 2 moved by (560, -200) (its twin): the replayed path bounces off it and flies over tower B's top
# into the flag. Found by a three-stage scan (artifacts/TASK-153/search/probe.py: 8 kicks x 2806 turn-around lines,
# 937 runs reach A; then each with the exact twin, 487/921 win; then +-10 px twin offsets, 9/9 win for this one;
# artifacts/TASK-153/search_ref.json); keep these exact integer coordinates.
LEVEL29_LINES = [((520, 400), (600, 340)), ((180, 560), (300, 720)), ((740, 360), (860, 520))]
LEVEL29_MAX_FRAMES = 1500
# Level 30 ('sky is lava', TASK-155, lineK 2; reference solution): line 1 knocks the ball, which bounces in place on its
# pad, right over the shaft wall so it drops into floor portal A. A -> B lifts it 520 px, more energy than the field
# holds: B's exit stream would fly off the top edge, so line 2 is a roof under the sky that turns the rising ball down
# to the flag tower. Found by a two-stage scan (artifacts/TASK-155/search/probe.py: 1020 kick lines, 8 reach A, all
# leave through the top; then 8 kicks x 1944 roof lines, 365 wins, 53 for this kick; artifacts/TASK-155/search_ref.json);
# keep these exact integer coordinates.
LEVEL30_LINES = [((193, 463), (287, 497)), ((780, 174), (860, 36))]
LEVEL30_MAX_FRAMES = 1500
# Level 31 ('low door', TASK-157, lineK 4; reference solution): line 1 kicks the ball, which bounces in place on its pad,
# off to the left; line 2 is a low deflector right of the porch that turns the falling ball left into the tunnel, so
# it goes into the tall door A under the porch (the lower part: B then throws it to an energy level of ~y 150, while
# the upper part only gives y >= 240, short of the flag). Line 3 throws the ball, which rises out of B into the roof,
# out to the right under the roof's wall, and line 4 turns it straight up into the bell. Found by a staged scan
# (artifacts/TASK-157/search/probe.py: kick x deflector, 375/2432 reach A, 235 low; then line 3 under B's roof, then
# line 4 under the bell, 64/3780 wins; artifacts/TASK-157/search_ref.json). TASK-158 lengthened line 3 by 3 px at
# each end (was (99,566)->(141,524)): tools/level_search.py --mode local then wins 17/32 single-coordinate +-2 px
# variants instead of 15/32 (artifacts/TASK-158/g3_local.json); keep these exact integer coordinates.
LEVEL31_LINES = [((1140, 430), (1220, 380)), ((735, 777), (785, 743)), ((96, 569), (144, 521)), ((521, 591), (561, 549))]
LEVEL31_MAX_FRAMES = 1500
# Level 32 ('under the wall', TASK-159, lineK 3; reference solution): line 1 kicks the ball, which bounces in place on its
# pad, off to the right; line 2 turns the falling ball flat into the low tunnel under the lid, so it drops into the left
# half of floor portal A (the wall x = 560 stands on A's centre). B (on the wall x = 760, facing right) throws it out of
# its lower half, and line 3 turns it back up into B's UPPER half, so it comes out of A's right half, under the wall, into
# the flag shaft (AB, BA). Found by a staged scan (artifacts/TASK-159/search/probe.py: 8 kicks x 1838 feed lines, 60
# reach A; then line 3 right of B, 54/3459 wins; this one's +-2 px neighbourhood wins 24/24;
# artifacts/TASK-159/search_ref.json); keep these exact integer coordinates.
LEVEL32_LINES = [((154, 360), (217, 390)), ((326, 645), (420, 670)), ((893, 682), (863, 598))]
LEVEL32_MAX_FRAMES = 1500

# Counts game frames that run physics and remembers the frame on which the level was completed.
LEVEL11_COUNTER_JS = """() => { window.__l11Frames = 0; window.__l11Win = null;
    const g = gameMechanics;
    gameMechanics = function() { const on = physics && !editorMode; const r = g();
        if (on) { ++window.__l11Frames;
            if (levelCompletedWindow && window.__l11Win === null) window.__l11Win = window.__l11Frames }
        return r } }"""


def play_solution(page, info, src, segments, max_frames, key, via=('A', 'B')):
    # Pause menu -> level square index + 1, real clicks; then play the solution with real mouse
    # input: draw each line (click, move, click), press start (unless the last allowed line already
    # started physics), and wait until the level is completed
    # (at most max_frames physics frames) with at least one via[0] -> via[1] teleport.
    index = place_and_start(page, info, src, segments, key)
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


def place_and_start(page, info, src, segments, key, before_draw_js=None):
    # play_solution's input part: menu -> 'Levels' -> map slot, draw the lines with real clicks, start physics.
    # before_draw_js runs right after the frame counter is installed (before any line is drawn).
    # src is the level's source id (definition number, TASK-177); its map slot holds levelBySrc(src).
    # Returns the play-order index.
    frames(page)
    index = page.evaluate("n => levelBySrc(n)", src)
    if index < 0:
        raise RuntimeError('%s: no level with srcId %s' % (key, src))
    pick_level(page, index)
    st = page.evaluate("({thisLevel, drawMenu, portals: (curLevel().portals || []).length})")
    info[key] = st
    info['srcId'] = page.evaluate("levels[thisLevel].srcId")
    if st != {'thisLevel': index, 'drawMenu': False, 'portals': 2} or info['srcId'] != src:
        raise RuntimeError('%s not loaded: %s' % (key, st))
    n0 = page.evaluate("lines.length")
    # installed before drawing: physics is off until the start (or the last allowed line), so the
    # counter starts with the first physics frame either way
    page.evaluate(LEVEL11_COUNTER_JS)
    if before_draw_js:
        page.evaluate(before_draw_js)
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
    return index


def sc_level11(page, info):
    play_solution(page, info, 11, [LEVEL11_LINE], LEVEL11_MAX_FRAMES, 'level11')


def sc_level12(page, info):
    play_solution(page, info, 12, [LEVEL12_LINE], LEVEL12_MAX_FRAMES, 'level12', via=('B', 'A'))


def sc_level13(page, info):
    play_solution(page, info, 13, LEVEL13_LINES, LEVEL13_MAX_FRAMES, 'level13')


def sc_level14(page, info):
    play_solution(page, info, 14, [LEVEL14_LINE], LEVEL14_MAX_FRAMES, 'level14')


def sc_level15(page, info):
    play_solution(page, info, 15, [LEVEL15_LINE], LEVEL15_MAX_FRAMES, 'level15', via=('B', 'A'))


def sc_level16(page, info):
    play_solution(page, info, 16, [LEVEL16_LINE], LEVEL16_MAX_FRAMES, 'level16', via=('B', 'A'))


def sc_level17(page, info):
    play_solution(page, info, 17, [LEVEL17_LINE], LEVEL17_MAX_FRAMES, 'level17')


def sc_level18(page, info):
    play_solution(page, info, 18, LEVEL18_LINES, LEVEL18_MAX_FRAMES, 'level18')


def sc_level19(page, info):
    play_solution(page, info, 19, LEVEL19_LINES, LEVEL19_MAX_FRAMES, 'level19')


def sc_level20(page, info):
    play_solution(page, info, 20, LEVEL20_LINES, LEVEL20_MAX_FRAMES, 'level20')


def sc_level21(page, info):
    play_solution(page, info, 21, LEVEL21_LINES, LEVEL21_MAX_FRAMES, 'level21')


def sc_level22(page, info):
    play_solution(page, info, 22, LEVEL22_LINES, LEVEL22_MAX_FRAMES, 'level22')


def sc_level23(page, info):
    play_solution(page, info, 23, LEVEL23_LINES, LEVEL23_MAX_FRAMES, 'level23')


def sc_level24(page, info):
    play_solution(page, info, 24, LEVEL24_LINES, LEVEL24_MAX_FRAMES, 'level24')


def sc_level25(page, info):
    play_solution(page, info, 25, LEVEL25_LINES, LEVEL25_MAX_FRAMES, 'level25')


def sc_level26(page, info):
    play_solution(page, info, 26, LEVEL26_LINES, LEVEL26_MAX_FRAMES, 'level26')


def sc_level27(page, info):
    play_solution(page, info, 27, LEVEL27_LINES, LEVEL27_MAX_FRAMES, 'level27')


def sc_level28(page, info):
    play_solution(page, info, 28, LEVEL28_LINES, LEVEL28_MAX_FRAMES, 'level28')


def sc_level29(page, info):
    play_solution(page, info, 29, LEVEL29_LINES, LEVEL29_MAX_FRAMES, 'level29')


def sc_level30(page, info):
    play_solution(page, info, 30, LEVEL30_LINES, LEVEL30_MAX_FRAMES, 'level30')


def sc_level31(page, info):
    play_solution(page, info, 31, LEVEL31_LINES, LEVEL31_MAX_FRAMES, 'level31')


def sc_level32(page, info):
    play_solution(page, info, 32, LEVEL32_LINES, LEVEL32_MAX_FRAMES, 'level32')


# TASK-164 rim trap: the level 19 lines from the bug video (artifacts/ball-physics-bug.mp4). Before the fix the ball
# landed on the BACK of portal A's host line (the shelf y=450) next to a rim and shuttled between the rims forever.
# The ball must not be trapped within L19_RIM_FRAMES game frames (it may win or lose; this is not a solution).
L19_RIM_LINES = [((40, 400), (295, 750)), ((295, 750), (980, 240))]
L19_RIM_FRAMES = 900
# Per-frame hook on the real game loop: the shared rim-trap detector (tests/portal/rimtrap.py TRAP_JS) and the
# ball path (one point per physics frame) for the path strip.
L19_RIM_WATCH_JS = """() => { window.__rt = null; window.__rtPath = [];
    const g = gameMechanics;
    gameMechanics = function() { const on = physics && !editorMode; const n0 = portalState.teleports.length;
        const r = g();
        if (on) { if (!window.__rt) window.__rt = window.__rimtrap.detector(currentPortals() || []);
            const tp = portalState.teleports.length > n0;
            window.__rt.frame(tp, window.__l11Frames);
            window.__rtPath.push([Math.round(ball.posX * 10) / 10, Math.round(ball.posY * 10) / 10, tp ? 1 : 0]) }
        return r } }"""


def path_strip(png, path, portals, out):
    # The screenshot with the ball path (blue -> red over time, teleports as yellow dots) and a strip below it:
    # x (blue) and y (orange) of the ball per frame, plus each portal's centre band (grey, +-h+r+2 around it in x).
    from PIL import Image, ImageDraw
    im = Image.open(png).convert('RGB')
    W, H = im.size
    sx, sy = W / 1280.0, H / 800.0
    sh = 200
    out_im = Image.new('RGB', (W, H + sh), (16, 20, 34))
    out_im.paste(im, (0, 0))
    d = ImageDraw.Draw(out_im)
    n = max(1, len(path) - 1)
    for i in range(1, len(path)):
        a, b = path[i - 1], path[i]
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 200:
            continue  # teleport / restart jump
        c = (int(255 * i / n), 80, int(255 * (1 - i / n)))
        d.line([(a[0] * sx, a[1] * sy), (b[0] * sx, b[1] * sy)], fill=c, width=2)
    for p in path:
        if p[2]:
            d.ellipse([p[0] * sx - 5, p[1] * sy - 5, p[0] * sx + 5, p[1] * sy + 5], outline=(255, 230, 0), width=2)
    y0 = H + 10
    for P in portals:  # x band of each portal around its centre
        for v in (P['x'] - P['h'] - 12, P['x'] + P['h'] + 12):
            yy = y0 + (sh - 20) * (1 - v / 1280.0)
            d.line([(0, yy), (W, yy)], fill=(90, 90, 90), width=1)
    for k, col, scale in ((0, (80, 160, 255), 1280.0), (1, (255, 160, 60), 800.0)):
        pts = [(W * i / n, y0 + (sh - 20) * (1 - p[k] / scale)) for i, p in enumerate(path)]
        if len(pts) > 1:
            d.line(pts, fill=col, width=2)
    d.text((6, H + 2), 'x (blue) / y (orange) per frame, %d frames; grey: portal x bands' % len(path), fill=(220, 220, 220))
    out_im.save(out)


def sc_l19_rim_backside(page, info, out_dir=None):
    sys.path.insert(0, os.path.join(ROOT, 'tests', 'portal'))
    from rimtrap import install
    install(page)
    place_and_start(page, info, 19, L19_RIM_LINES, 'l19_rim_backside', before_draw_js=L19_RIM_WATCH_JS)
    page.wait_for_function("levelCompletedWindow || (window.__rt && window.__rt.trapped) || window.__l11Frames >= %d"
                           % L19_RIM_FRAMES, timeout=180000, polling=100)
    r = page.evaluate("""() => ({trapped: window.__rt.trapped, trapFrame: window.__rt.trapFrame,
        trapPortal: window.__rt.trapPortal, frames: window.__l11Frames, levelCompleted: levelCompletedWindow,
        winFrame: window.__l11Win, teleports: portalState.teleports.map(t => t.from + '->' + t.to),
        hostHits: portalState.hostHits, rimHits: portalState.rimHits, ball: [ball.posX, ball.posY],
        portals: (currentPortals() || []).map(P => ({name: P.name, x: P.x, y: P.y, h: P.h}))})""")
    info['rimtrap'] = r
    info['_path'] = page.evaluate("window.__rtPath")
    frames(page)
    if r['trapped']:
        raise RuntimeError('l19_rim_backside: ball TRAPPED at frame %s near portal %s' % (r['trapFrame'], r['trapPortal']))


# TASK-172 exit overlap: on level 24 the shelf (60,360)->(1240,360) starts at portal B's centre. A ball entering A
# within ~r of A's centre would leave B with its centre on the shelf and slide inside it ('stuck in textures').
# These real-input lines send the ball into A within 5 px of its centre; the exit must be refused (blocked,
# reason 'overlap') and the shared embedded detector (tests/portal/embed.py EMBED_JS) must not fire within
# L24_CENTER_FRAMES game frames (the ball may win, lose or bounce; this is not a solution).
L24_CENTER_LINES = [((170, 476), (620, 513)), ((748, 595), (678, 726))]
L24_CENTER_FRAMES = 600
# Per-frame hook on the real game loop: the embedded detector and the ball path (one point per physics frame,
# blocked exits marked like teleports) for the path strip.
# Blocked records are collected per frame (an off-map ball restarts the level: physics off, portalState cleared).
L24_CENTER_WATCH_JS = """() => { window.__em = null; window.__emPath = []; window.__emBlocked = []; window.__emTeleports = [];
    const g = gameMechanics;
    gameMechanics = function() { const on = physics && !editorMode;
        const t0 = portalState.teleports.length, b0 = portalState.blockedExits;
        const r = g();
        if (on) { if (!window.__em) window.__em = window.__embed.detector();
            const kept = portalState.blockedExits >= b0 && portalState.teleports.length >= t0;   // no restart this frame
            if (kept) { for (const b of portalState.blocked.slice(b0)) window.__emBlocked.push(b);
                        for (const t of portalState.teleports.slice(t0)) window.__emTeleports.push(t) }
            const tp = kept && portalState.teleports.length + portalState.blockedExits > t0 + b0;
            window.__em.frame(window.__l11Frames);
            window.__emPath.push([Math.round(ball.posX * 10) / 10, Math.round(ball.posY * 10) / 10, tp ? 1 : 0]) }
        return r } }"""


def sc_l24_center_entry(page, info):
    sys.path.insert(0, os.path.join(ROOT, 'tests', 'portal'))
    from embed import install
    install(page)
    place_and_start(page, info, 24, L24_CENTER_LINES, 'l24_center_entry', before_draw_js=L24_CENTER_WATCH_JS)
    # ends on the win, after L24_CENTER_FRAMES frames, or when the ball left the map (the level restarted, physics off)
    page.wait_for_function("levelCompletedWindow || window.__l11Frames >= %d || (window.__l11Frames > 0 && !physics)"
                           % L24_CENTER_FRAMES, timeout=180000, polling=100)
    r = page.evaluate("""() => ({embedded: window.__em.embedded, embedFrame: window.__em.embedFrame,
        embedFrames: window.__em.count, maxRun: window.__em.maxRun, frames: window.__l11Frames,
        levelCompleted: levelCompletedWindow, winFrame: window.__l11Win, physics,
        end: levelCompletedWindow ? 'won' : physics ? 'frames' : 'offmap',
        blockedExits: window.__emBlocked.length,
        blocked: window.__emBlocked.map(b => ({step: b.step, from: b.from, to: b.to, s: b.s, kind: b.kind,
            reason: b.reason, before: b.before, after: b.after})),
        teleports: window.__emTeleports.map(t => ({step: t.step, from: t.from, to: t.to, s: t.s, after: t.after})),
        ball: [ball.posX, ball.posY],
        portals: (currentPortals() || []).map(P => ({name: P.name, x: P.x, y: P.y, h: P.h}))})""")
    info['embed'] = r
    info['_path'] = page.evaluate("window.__emPath")
    frames(page)
    first = r['blocked'][0] if r['blocked'] else None
    ok_block = r['blockedExits'] >= 1 and any(b['reason'] == 'overlap' for b in r['blocked'])
    centre = first is not None and first['from'] == 'A' and abs(first['s']) < 5
    if not (ok_block and centre):
        raise RuntimeError('l24_center_entry: no overlap-blocked A entry within 5 px of the centre: blockedExits=%s first=%s'
                           % (r['blockedExits'], first))
    if r['embedded']:
        raise RuntimeError('l24_center_entry: ball EMBEDDED at frame %s (%s frames)' % (r['embedFrame'], r['embedFrames']))


# TASK-180 route map (drawing only). map: no progress; map_progress: new levels 1-7 + the first two extra-branch
# levels solved through window.mapDebug. Both write their entry into state.json (MAP_STATE) in the task dir.
MAP_STATE = {}
MAP_STATE_JS = """() => { const M = ROUTEMAP, a = routeAssign(levels), s = window.mapState;
    const solved = i => levels[i].unlock == 2;
    const expectedCoral = M.hops.filter(h => a[h[0]] !== undefined && a[h[1]] !== undefined && solved(a[h[0]]) && solved(a[h[1]])).length;
    let expectedNext = levels.findIndex(l => l.unlock != 2) + 1;
    return {drawMap, nLevels: levels.length, solvedNumbers: levels.map((l, i) => l.unlock == 2 ? i + 1 : 0).filter(n => n),
        solvedSrcIds: progressSolved(), next: s.next, expectedNext, coralHops: s.coralHops, expectedCoralHops: expectedCoral,
        hops: s.hops, lamps: s.lamps, flags: s.flags, platforms: s.platforms, obstacles: s.obstacles,
        obstaclesInData: M.obstacles.length, portals: s.portals, ball: s.ball, builds: s.builds,
        menuIconVisible: drawMenuIcon, menuIconRect, slots: s.slots} }"""


def map_open(page, info, solved_js):
    solved = page.evaluate(solved_js)
    nxt = page.evaluate("ids => window.mapDebug(ids)", solved)
    frames(page, 4)
    st = page.evaluate(MAP_STATE_JS)
    st['hookNext'] = nxt
    info['mapstate'] = st


def sc_map(page, info):
    map_open(page, info, "[]")


def sc_map_progress(page, info):
    map_open(page, info, """(() => { const ids = levels.slice(0, 7).map(l => l.srcId);
        const extra = levels.map((l, i) => i).filter(i => routeBranch(levels, i) === 'extra').slice(0, 2);
        return ids.concat(extra.map(i => levels[i].srcId)) })()""")


# TASK-181 route map input. Each scenario writes <scenario>.json (compact) into the task dir; run_scenario adds
# the page's console error count and the final pass.
MAP_INPUT_FILES = {'map_open': 'map_open.json', 'map_play': 'map_play.json', 'map_touch': 'map_touch.json',
                   'map_close': 'map_close.json'}
MAP_UI_JS = """() => ({drawMap, drawMenu, drawMenuIcon, levelCompletedWindow, physics, thisLevel,
    srcId: levels[thisLevel].srcId, playtest: !!playtestLevel})"""
# counts the real DOM input events reaching the page (capture phase, before the game's handlers)
INPUT_COUNTER_JS = """() => { window.__inputs = {click: 0, mousedown: 0, touchstart: 0, touchend: 0};
    for (const t in window.__inputs) document.addEventListener(t, () => ++window.__inputs[t], true) }"""
# play-order index 7 = new level 8 (srcId 16 at TASK-177's order)
MAP_PLAY_INDEX = 7
MAP_PLAY_SRC = 16


def slot_info(page, i):
    return page.evaluate("""i => { const a = routeAssign(levels); const id = Object.keys(a).find(k => a[k] === i);
        return {index: i, number: i + 1, srcId: levels[i].srcId, slot: id || null, box: id ? routeSlotBox(id) : null,
            point: routeLevelPoint(levels, i), hitAtPoint: routeLevelAt(levels, ...routeLevelPoint(levels, i))} }""", i)


def sc_map_open(page, info):
    frames(page)
    page.evaluate(INPUT_COUNTER_JS)
    open_menu(page)
    menu = page.evaluate(MAP_UI_JS)
    btn = page.evaluate(LEVELS_BUTTON_JS)
    click(page, *btn)
    frames(page, 3)
    st = page.evaluate(MAP_UI_JS)
    ms = page.evaluate("window.mapState && {next: mapState.next, platforms: mapState.platforms, flags: mapState.flags}")
    d = {'menuOpened': menu, 'levelsButton': btn, 'state': st, 'mapState': ms, 'inputs': page.evaluate("window.__inputs"),
         'gridGone': page.evaluate("typeof drawLevels === 'undefined' && typeof levelsRectCollision === 'undefined'")}
    d['pass'] = bool(menu['drawMenu'] and st['drawMap'] and not st['drawMenu'] and st['drawMenuIcon'] and d['gridGone']
                     and ms and ms['platforms'] == page.evaluate("levels.length"))
    info['mapinput'] = d


def map_play_common(page, info, tap):
    frames(page)
    page.evaluate(INPUT_COUNTER_JS)
    before = page.evaluate(MAP_UI_JS)
    if tap:  # the whole flow by touch: tap the menu icon, tap 'Levels'
        for pt in (page.evaluate("[menuIconRect[0][0] + 31, menuIconRect[0][1] + 31]"), page.evaluate(LEVELS_BUTTON_JS)):
            page.touchscreen.tap(*to_client(page, *pt))
            frames(page)
        opened = page.evaluate("window.__inputs")
    else:
        open_map(page)
        opened = None
    onMap = page.evaluate(MAP_UI_JS)
    si = slot_info(page, MAP_PLAY_INDEX)
    page.evaluate("() => { window.__inputs = {click: 0, mousedown: 0, touchstart: 0, touchend: 0} }")
    # TASK-182: first tap / click selects (card shown, level not started), the second one on the same level starts it
    selected = None
    for k in range(2):
        if tap:
            page.touchscreen.tap(*to_client(page, *si['point']))
            frames(page)
        else:
            click(page, *si['point'])
        if k == 0:
            selected = page.evaluate("() => Object.assign((" + MAP_UI_JS + ")(), {mapSel, card: window.mapCard && window.mapCard.i})")
    frames(page, 3)
    after = page.evaluate(MAP_UI_JS)
    inputs = page.evaluate("window.__inputs")
    d = {'before': before, 'openInputs': opened, 'onMap': onMap, 'slot': si, 'selected': selected, 'after': after, 'inputs': inputs,
         'levelLoaded': page.evaluate("({ball: [ball.posX, ball.posY], start: [curLevel().ballX, curLevel().ballY], linesK, nLines: lines.length})")}
    ok = (onMap['drawMap'] and si['slot'] is not None and si['hitAtPoint'] == MAP_PLAY_INDEX
          and after['thisLevel'] == MAP_PLAY_INDEX and after['srcId'] == MAP_PLAY_SRC
          and not after['drawMap'] and not after['drawMenu'] and not after['levelCompletedWindow']
          and after['drawMenuIcon'] and not after['playtest']
          and selected['drawMap'] and selected['mapSel'] == MAP_PLAY_INDEX and selected['card'] == MAP_PLAY_INDEX
          and selected['thisLevel'] == before['thisLevel'])
    if tap:  # the tap went through the touch handlers (no mouse click event)
        ok = ok and inputs['touchstart'] == 2 and inputs['touchend'] == 2 and inputs['click'] == 0 and opened == {
            'click': 0, 'mousedown': 0, 'touchstart': 2, 'touchend': 2}
    else:
        ok = ok and inputs['click'] == 2 and inputs['touchstart'] == 0
    d['pass'] = bool(ok)
    info['mapinput'] = d


def sc_map_play(page, info):
    map_play_common(page, info, tap=False)


def sc_map_touch(page, info):
    map_play_common(page, info, tap=True)


def sc_map_close(page, info):
    frames(page)
    open_map(page)
    onMap = page.evaluate(MAP_UI_JS)
    # a click on empty map space (between slots) does nothing
    empty = [40, 40]
    emptyHit = page.evaluate("p => routeLevelAt(levels, p[0], p[1])", empty)
    click(page, *empty)
    afterEmpty = page.evaluate(MAP_UI_JS)
    icon = page.evaluate("[menuIconRect[0][0] + 31, menuIconRect[0][1] + 31]")
    click(page, *icon)
    frames(page, 2)
    after = page.evaluate(MAP_UI_JS)
    # and the menu's 'resume' still works afterwards
    click(page, *page.evaluate("""[menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2,
        menuCoords[1] + 300 + menuTextRect[1] / 2]"""))
    resumed = page.evaluate(MAP_UI_JS)
    d = {'onMap': onMap, 'emptyClick': {'point': empty, 'hit': emptyHit, 'after': afterEmpty}, 'menuIcon': icon,
         'after': after, 'resumed': resumed}
    d['pass'] = bool(onMap['drawMap'] and emptyHit == -1 and afterEmpty['drawMap'] and afterEmpty['thisLevel'] == onMap['thisLevel']
                     and not after['drawMap'] and after['drawMenu'] and not after['drawMenuIcon']
                     and after['thisLevel'] == onMap['thisLevel']
                     and not resumed['drawMenu'] and not resumed['drawMap'] and resumed['drawMenuIcon'])
    info['mapinput'] = d


# TASK-182 preview card. map_card_portal / map_card_plain: real mouse hover over a portal / non-portal level writes
# card_hover.json; map_card_edge: hover over the levels nearest each screen edge and corner, boxes.json + a composite
# map_card_edge.png (one tile per case, the per-case shots in card_edge/); card_play: click flow -> card_play.json.
CARD_FILES = {'map_card_portal': 'card_hover.json', 'map_card_plain': 'card_hover.json', 'map_card_edge': 'boxes.json',
              'card_play': 'card_play.json'}
CARD_HOVER = {}
# drawn card + an independent in-page recheck of its rects (overlap / on-screen / pointer direction)
CARD_STATE_JS = """() => { const c = window.mapCard; if (!c) return null;
    const ov = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
    const avoid = {menuIcon: c.menuIcon, flag: c.flag}; if (c.nextFlag) avoid.nextFlag = c.nextFlag;
    const hits = []; for (const k in avoid) { if (ov(c.body, avoid[k])) hits.push('body:' + k); if (ov(c.ptr, avoid[k])) hits.push('pointer:' + k) }
    const A = c.all, F = c.flag, t = c.tip;
    const dist = Math.hypot(Math.max(F[0] - t[0], 0, t[0] - F[2]), Math.max(F[1] - t[1], 0, t[1] - F[3]));
    const dir = c.side === 'above' ? t[1] > c.body[3] && t[1] < F[1] : c.side === 'below' ? t[1] < c.body[1] && t[1] > F[3]
        : c.side === 'right' ? t[0] < c.body[0] && t[0] > F[2] : t[0] > c.body[2] && t[0] < F[0];
    const along = (c.side === 'above' || c.side === 'below') ? (t[0] > F[0] && t[0] < F[2]) : (t[1] > F[1] && t[1] < F[3]);
    return {i: c.i, n: c.n, srcId: c.srcId, slot: c.slot, side: c.side, card: c.body, pointer: {tip: t, base: c.base, box: c.ptr},
        cardWithPointer: A, menuIcon: c.menuIcon, flag: c.flag, nextSlot: c.nextSlot, nextFlag: c.nextFlag,
        overlaps: hits.length, overlapList: hits, layoutOverlaps: c.overlaps,
        onscreen: A[0] >= 0 && A[1] >= 0 && A[2] <= GAME_W && A[3] <= GAME_H,
        pointsAtFlag: dir && along && dist <= 4, tipToFlag: dist,
        mapSel, mapHover, cursor: canvas.style.cursor, info: window.mapCardInfo, drawMap, thisLevel} }"""


def hover_level(page, i):
    pt = page.evaluate(LEVEL_POINT_JS, i)
    move(page, *pt)
    frames(page, 3)
    return pt


def card_hover(page, info, want_portal):
    frames(page)
    open_map(page)
    i = page.evaluate("p => levels.findIndex((l, i) => i >= 2 && !!(l.portals && l.portals.length) === p)", want_portal)
    before = page.evaluate("({card: window.mapCard, cursor: canvas.style.cursor})")
    pt = hover_level(page, i)
    st = page.evaluate(CARD_STATE_JS)
    d = {'level': i, 'number': i + 1, 'portalLevel': want_portal, 'point': pt, 'beforeHover': before, 'card': st}
    d['pass'] = bool(before['card'] is None and st and st['i'] == i and st['info']['i'] == i
                     and st['info']['badge'] == want_portal and st['info']['glyphs'] == page.evaluate("i => levels[i].lineK", i)
                     and st['info']['thumb']['lines'] > 0 and st['overlaps'] == 0 and st['onscreen'] and st['pointsAtFlag']
                     and st['drawMap'] and st['thisLevel'] == 0 and st['mapSel'] == -1 and st['cursor'] == 'pointer')
    info['card'] = d


def sc_map_card_portal(page, info):
    card_hover(page, info, True)


def sc_map_card_plain(page, info):
    card_hover(page, info, False)


EDGE_JS = """() => { const a = routeAssign(levels), ids = Object.keys(a), S = ROUTEMAP.slots;
    const pick = (f, best) => ids.reduce((m, id) => (m === null || best(f(id), f(m))) ? id : m, null);
    const lt = (x, y) => x < y, gt = (x, y) => x > y, X = id => S[id][0], Y = id => S[id][1];
    const want = {left: pick(X, lt), right: pick(X, gt), top: pick(Y, lt), bottom: pick(Y, gt),
        topLeft: pick(id => X(id) + Y(id), lt), topRight: pick(id => X(id) - Y(id), gt),
        bottomLeft: pick(id => X(id) - Y(id), lt), bottomRight: pick(id => X(id) + Y(id), gt)};
    const out = {}; for (const k in want) { const id = want[k]; (out[id] = out[id] || {slot: id, i: a[id], edges: []}).edges.push(k) }
    return Object.values(out) }"""


def sc_map_card_edge(page, info):
    frames(page)
    open_map(page)
    cases = page.evaluate(EDGE_JS)
    edge_dir = os.path.join(OUT_DIR, 'card_edge')
    os.makedirs(edge_dir, exist_ok=True)
    shots = []
    for c in cases:
        move(page, 20, 400)  # leave the previous level first
        frames(page)
        c['point'] = hover_level(page, c['i'])
        c['state'] = page.evaluate(CARD_STATE_JS)
        f = os.path.join(edge_dir, 'edge_%s.png' % c['slot'])
        page.screenshot(path=f)
        shots.append((f, '%s n%d %s' % (c['slot'], c['i'] + 1, '/'.join(c['edges']))))
    # every level's card by the same rule (no hover), as a wider check
    allc = page.evaluate("() => mapCardCheck().map(c => ({i: c.i, slot: c.slot, side: c.side, overlaps: c.overlaps, onscreen: c.all[0] >= 0 && c.all[1] >= 0 && c.all[2] <= GAME_W && c.all[3] <= GAME_H}))")
    d = {'cases': cases, 'edgesCovered': sorted({e for c in cases for e in c['edges']}), 'allLevels': {
        'count': len(allc), 'maxOverlaps': max(c['overlaps'] for c in allc), 'allOnscreen': all(c['onscreen'] for c in allc),
        'sides': {k: sum(1 for c in allc if c['side'] == k) for k in ('above', 'right', 'left', 'below')}, 'levels': allc}}
    d['pass'] = bool(len(cases) >= 4 and len(d['edgesCovered']) == 8 and all(
        c['state'] and c['state']['i'] == c['i'] and c['state']['overlaps'] == 0 and c['state']['layoutOverlaps'] == 0
        and c['state']['onscreen'] and c['state']['pointsAtFlag'] for c in cases)
        and d['allLevels']['maxOverlaps'] == 0 and d['allLevels']['allOnscreen'] and len(allc) == page.evaluate("levels.length"))
    info['card'] = d
    info['_composite'] = shots


def composite(shots, out):
    from PIL import Image, ImageDraw
    tiles = [Image.open(f).convert('RGB') for f, _ in shots]
    tw, th = tiles[0].width // 2, tiles[0].height // 2
    cols = 2 if len(tiles) <= 4 else 3
    rows = (len(tiles) + cols - 1) // cols
    img = Image.new('RGB', (cols * tw, rows * th), (0, 0, 0))
    dr = ImageDraw.Draw(img)
    for k, (t, (_, label)) in enumerate(zip(tiles, shots)):
        x, y = (k % cols) * tw, (k // cols) * th
        img.paste(t.resize((tw, th)), (x, y))
        dr.rectangle([x, y, x + tw - 1, y + th - 1], outline=(90, 90, 90))
        dr.text((x + 8, y + th - 18), label, fill=(255, 255, 0))
    img.save(out)


def sc_card_play(page, info):
    frames(page)
    page.evaluate(INPUT_COUNTER_JS)
    j, k = MAP_PLAY_INDEX, MAP_PLAY_INDEX + 5
    ui = "() => Object.assign((" + MAP_UI_JS + ")(), {mapSel, card: window.mapCard && window.mapCard.i, play: window.mapCard && window.mapCard.play})"
    # A: first click selects (card, not started), then a click on the card's play button starts it
    open_map(page)
    a0 = page.evaluate(ui)
    pa = page.evaluate(LEVEL_POINT_JS, j)
    click(page, *pa)
    frames(page)
    a1 = page.evaluate(ui)
    cardA = page.evaluate(CARD_STATE_JS)
    move(page, a1['play'][0], a1['play'][1])  # travel to the play button: the card stays
    frames(page)
    a2 = page.evaluate(ui)
    a2['cursor'] = page.evaluate("canvas.style.cursor")
    click(page, a1['play'][0], a1['play'][1])
    frames(page, 3)
    a3 = page.evaluate(ui)
    # B: a first click selects level k, a second click on it starts it
    open_map(page)
    b0 = page.evaluate(ui)
    pb = page.evaluate(LEVEL_POINT_JS, k)
    click(page, *pb)
    frames(page)
    b1 = page.evaluate(ui)
    click(page, *pb)
    frames(page, 3)
    b2 = page.evaluate(ui)
    # C: a click on empty map space clears the selection without starting anything
    open_map(page)
    click(page, *page.evaluate(LEVEL_POINT_JS, j))
    c1 = page.evaluate(ui)
    click(page, 40, 40)
    c2 = page.evaluate(ui)
    d = {'playButton': {'level': j, 'point': pa, 'onMap': a0, 'afterFirstClick': a1, 'card': cardA, 'hoverPlay': a2, 'afterPlay': a3},
         'secondClick': {'level': k, 'point': pb, 'onMap': b0, 'afterFirstClick': b1, 'afterSecondClick': b2},
         'emptyClick': {'selected': c1, 'after': c2}, 'inputs': page.evaluate("window.__inputs")}
    d['firstClickShowsCardNotStarted'] = bool(a1['drawMap'] and a1['mapSel'] == j and a1['card'] == j and a1['thisLevel'] == a0['thisLevel'] == 0)
    d['playStarts'] = bool(a2['card'] == j and a2['cursor'] == 'pointer' and a3['thisLevel'] == j and not a3['drawMap'] and not a3['drawMenu'])
    d['secondClickFirstNotStarted'] = bool(b1['drawMap'] and b1['mapSel'] == k and b1['card'] == k and b1['thisLevel'] == j)
    d['secondClickStarts'] = bool(b2['thisLevel'] == k and not b2['drawMap'] and not b2['drawMenu'] and b2['srcId'] == page.evaluate("i => levels[i].srcId", k))
    d['emptyClears'] = bool(c1['mapSel'] == j and c2['mapSel'] == -1 and c2['drawMap'] and c2['thisLevel'] == k)
    d['pass'] = bool(d['firstClickShowsCardNotStarted'] and d['playStarts'] and d['secondClickFirstNotStarted']
                     and d['secondClickStarts'] and d['emptyClears'] and cardA and cardA['overlaps'] == 0)
    info['card'] = d


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
    'next_level_order': sc_next_level_order,
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
    'level18': sc_level18,
    'level19': sc_level19,
    'level20': sc_level20,
    'level21': sc_level21,
    'level22': sc_level22,
    'level23': sc_level23,
    'level24': sc_level24,
    'level25': sc_level25,
    'level26': sc_level26,
    'level27': sc_level27,
    'level28': sc_level28,
    'level29': sc_level29,
    'level30': sc_level30,
    'level31': sc_level31,
    'level32': sc_level32,
    'l19_rim_backside': sc_l19_rim_backside,
    'l24_center_entry': sc_l24_center_entry,
    'progress_reload': sc_progress_reload,
    'progress_storage_blocked': sc_progress_storage_blocked,
    'progress_garbage': sc_progress_garbage,
    'map': sc_map,
    'map_progress': sc_map_progress,
    'map_open': sc_map_open,
    'map_play': sc_map_play,
    'map_touch': sc_map_touch,
    'map_close': sc_map_close,
    'map_card_portal': sc_map_card_portal,
    'map_card_plain': sc_map_card_plain,
    'map_card_edge': sc_map_card_edge,
    'card_play': sc_card_play,
}

# Extra browser.new_page() options per scenario (the viewport stays the default/--viewport one).
PAGE_OPTIONS = {
    'touch_line': {'has_touch': True},
    'map_touch': {'has_touch': True},
}
# Scripts added with page.add_init_script() before the first load (they run before every page script).
PAGE_INIT = {
    'progress_storage_blocked': STORAGE_THROW_JS,
    'progress_garbage': "localStorage.setItem('bp.progress.v1', '{solved: [1, 2,')",
}
OUT_DIR = None
# Screenshot file name when it differs from the scenario name
SHOT_NAME = {'map': 'map_fresh'}


def run_scenario(browser, name, out_dir, eval_js, viewport=VIEWPORT, dpr=1):
    errors = []
    info = {}
    page = browser.new_page(viewport=viewport, device_scale_factor=dpr, **PAGE_OPTIONS.get(name, {}))
    page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
    entry = {'errors': errors}
    try:
        if name in PAGE_INIT:
            page.add_init_script(PAGE_INIT[name])
        page.goto(URL)
        page.wait_for_load_state('load')
        page.wait_for_function(BOOT_JS)
        frames(page)
        SCENARIOS[name](page, info)
        if eval_js:
            entry['eval'] = page.evaluate(
                "async js => JSON.parse(JSON.stringify(await (0, eval)(js)) ?? 'null')", eval_js)
            frames(page)
        entry['state'] = page.evaluate(STATE_JS)
        page.screenshot(path=os.path.join(out_dir, SHOT_NAME.get(name, name) + '.png'))
        if '_path' in info:  # path strip next to the screenshot (TASK-164)
            path_strip(os.path.join(out_dir, name + '.png'), info.pop('_path'), (info.get('rimtrap') or info['embed'])['portals'],
                       os.path.join(out_dir, name + '_path.png'))
    except Exception as e:  # recorded as an error -> non-zero exit
        errors.append('exception: %s: %s' % (type(e).__name__, str(e).splitlines()[0] if str(e) else ''))
    finally:
        page.close()
    entry.update(info)
    if name in PROGRESS_FILES and 'progress' in info:  # final error count of the whole page lifetime
        d = info['progress']
        d['consoleErrors'] = len(errors)
        d['errors'] = list(errors)
        if name == 'progress_storage_blocked':
            d['pass'] = bool(not errors and d['storageProbe'].startswith('throws') and d['won']['levelCompletedWindow']
                             and d['gameRunning'] and d['before']['solved'] == [])
        elif name == 'progress_garbage':
            d['pass'] = bool(not errors and d['solvedCount'] == 0 and d['completedCount'] == 0 and d['gameRunning']
                             and d['storedRaw'] not in (None, 'THROWS'))
        else:
            d['pass'] = bool(d['pass'] and not errors)
        with open(os.path.join(out_dir, PROGRESS_FILES[name]), 'w') as f:
            json.dump(d, f, separators=(',', ':'))
        if not d['pass']:
            errors.append('progress check failed: %s' % PROGRESS_FILES[name])
    if name in MAP_INPUT_FILES and 'mapinput' in info:  # TASK-181: map input + the page's final console error count
        d = info['mapinput']
        d['consoleErrors'] = len(errors)
        d['errors'] = list(errors)
        d['pass'] = bool(d['pass'] and not errors)
        with open(os.path.join(out_dir, MAP_INPUT_FILES[name]), 'w') as f:
            json.dump(d, f, separators=(',', ':'))
        if not d['pass']:
            errors.append('map input check failed: %s' % MAP_INPUT_FILES[name])
    elif name in MAP_INPUT_FILES:
        errors.append('map input scenario wrote no data: %s' % name)
    if '_composite' in info:  # TASK-182 map_card_edge: one tile per hovered edge case
        composite(info.pop('_composite'), os.path.join(out_dir, 'map_card_edge.png'))
    if name in CARD_FILES:  # TASK-182 card checks + the page's final console error count
        d = info.get('card')
        if d is None:
            errors.append('card scenario wrote no data: %s' % name)
        else:
            d['consoleErrors'] = len(errors)
            d['errors'] = list(errors)
            d['pass'] = bool(d['pass'] and not errors)
            if CARD_FILES[name] == 'card_hover.json':
                CARD_HOVER[name] = d
                d = CARD_HOVER
            with open(os.path.join(out_dir, CARD_FILES[name]), 'w') as f:
                json.dump(d, f, separators=(',', ':'))
            if not info['card']['pass']:
                errors.append('card check failed: %s' % name)
    if 'mapstate' in info:  # TASK-180: route map state + the page's final console error count
        d = info['mapstate']
        d['consoleErrors'] = len(errors)
        d['errors'] = list(errors)
        want_next = 8 if name == 'map_progress' else 1
        d['pass'] = bool(not errors and d['next'] == want_next == d['expectedNext'] == d['hookNext']
                         and d['coralHops'] == d['expectedCoralHops'] and d['lamps'] == 1 and d['drawMap']
                         and d['obstacles'] == d['obstaclesInData'] and d['portals'] == 2 and d['ball'] is not None
                         and d['platforms'] == d['nLevels'])
        MAP_STATE[name] = d
        with open(os.path.join(out_dir, 'state.json'), 'w') as f:
            json.dump(MAP_STATE, f, separators=(',', ':'))
        if not d['pass']:
            errors.append('map state check failed: %s' % name)
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
    global OUT_DIR
    OUT_DIR = out_dir

    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in names:
            entry = run_scenario(browser, name, out_dir, args.eval_js, viewport, args.dpr)
            result[name] = entry
            print('%-9s errors=%d state=%s%s' % (
                name, len(entry['errors']), json.dumps(entry.get('state'), separators=(',', ':')),
                (' eval=' + json.dumps(entry['eval'], separators=(',', ':'))[:300]) if 'eval' in entry else ''))
            if 'play' in entry:  # play_solution scenarios: win frame and teleports of the real-input run
                pl = entry['play']
                print('    play levelCompleted=%s winFrame=%s frames=%s teleports=%s' % (
                    pl['levelCompleted'], pl['winFrame'], pl['frames'],
                    ','.join(t['from'] + '->' + t['to'] for t in pl['teleports']) or '-'))
            if 'rimtrap' in entry:  # l19_rim_backside: rim-trap detector on the real game loop
                rt = entry['rimtrap']
                print('    rimtrap trapped=%s trapFrame=%s frames=%s levelCompleted=%s teleports=%s hostHits=%s rimHits=%s' % (
                    str(rt['trapped']).lower(), rt['trapFrame'], rt['frames'], rt['levelCompleted'],
                    ','.join(rt['teleports']) or '-', rt['hostHits'], rt['rimHits']))
            if 'embed' in entry:  # l24_center_entry: blocked exit (reason) + embedded detector on the real game loop
                em = entry['embed']
                print('    embed embedded=%s embedFrame=%s maxRun=%s frames=%s end=%s blockedExits=%s blocked=%s teleports=%s' % (
                    str(em['embedded']).lower(), em['embedFrame'], em['maxRun'], em['frames'], em['end'],
                    em['blockedExits'], ','.join('%s->%s:%s:s=%.2f' % (b['from'], b['to'], b['reason'], b['s']) for b in em['blocked']) or '-',
                    ','.join(t['from'] + '->' + t['to'] for t in em['teleports']) or '-'))
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
