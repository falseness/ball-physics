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
import contextlib
import json
import os
import re
import sys
import time

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
    page.evaluate("() => { const L = curLevel(); ball.posX = L.flagX + (flag[2][0] + flag[3][0]) / 2; ball.posY = L.flagY + (flag[2][1] + flag[3][1]) / 2; physics = true }")
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


# TASK-213: the win shortcuts put the ball centre on the pennant edge flag[2]-flag[3] (flagCollision is then true at
# once). They used to put it on the flag origin, which sits on the floor line: the contact push-out (TASK-199) moves
# such a ball out of the floor, away from the pole, and it fell off the map instead of winning.
def win_level_src(page, src):
    # Menu -> 'Levels' -> map slot (real clicks); real win through gameMechanics' flagCollision (ball on the flag).
    i = page.evaluate("n => levelBySrc(n)", src)
    pick_level(page, i)
    st = page.evaluate("({thisLevel, srcId: levels[thisLevel].srcId, drawMenu})")
    if st != {'thisLevel': i, 'srcId': src, 'drawMenu': False}:
        raise RuntimeError('level %s not loaded: %s' % (src, st))
    page.evaluate("() => { const L = curLevel(); ball.posX = L.flagX + (flag[2][0] + flag[3][0]) / 2; ball.posY = L.flagY + (flag[2][1] + flag[3][1]) / 2; physics = true }")
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

# Level 13 'accelerator' reference solution (TASK-204, lineK 1; was TASK-074's ramp + (589,381)-(712,393) kicker, lineK 4):
# under the contact physics the TASK-074 ramp under the ball wins on its own: the ball rolls right onto floor portal A,
# loops A -> B (shelf underside) twice, gaining speed, and reaches the flag (won on physics frame 241). G3: 5 of 8
# single-coordinate +-2 px variants also win (artifacts/TASK-204/gates_13.json).
LEVEL13_LINES = (((381, 679), (696, 744)),)
LEVEL13_MAX_FRAMES = 3000

# Level 14 (srcId 14) solution: one long ramp under the ball. The ball rolls down it into portal A, comes out of B
# 152 px higher still moving right, lands on the ramp again, and after the second A -> B teleport it has enough
# speed to clear wall A and hit the flag. TASK-204 (contact physics): the TASK-077 ramp (183,580)-(779,608) had only
# 2 of 8 winning +-2 px variants; its right end moved 8 px left, (183,580)-(771,608), is robust (re-found with
# tools/level_search.py, artifacts/TASK-204/gates_14.json).
LEVEL14_LINE = ((183, 580), (771, 608))
LEVEL14_MAX_FRAMES = 3000

# Level 15 (srcId 15) solution (layout from artifacts/new_level15.json, TASK-113): one long line under the ball
# rising to the right and crossing the wall x=633. The ball lands on it, rolls down-left into portal B (the floor pad
# facing up), comes out of A on the wall's right face and reaches the flag (won on physics frame 175, one B->A
# teleport). Found by a lattice + random search with in-page stepped frames (artifacts/TASK-114/search.log); all 8
# single-coordinate and all 8 whole-line +-2 px variants also win. Keep these exact integer coordinates.
LEVEL15_LINE = ((207, 547), (1024, 437))
LEVEL15_MAX_FRAMES = 3000

# Level 16 (srcId 16) solution: one line low under the ball sloping down to the left towards portal B (on the short
# wall at the bottom left, facing right). The ball drops beside the tall wall x=312 onto it, bounces down-left into B,
# comes out of A (the floor pad, facing up) and arcs right onto the flag (won on physics frame 101, one B->A teleport). TASK-205 (contact physics): the TASK-100 line
# (96,636)-(299,346) no longer wins (the ball bounces off it over B and leaves the map); this one was found by the G4
# sample of tools/level_search.py and wins with all 8 single-coordinate +-2 px variants
# (artifacts/TASK-205/gates_16.json). Keep these exact integer coordinates.
LEVEL16_LINE = ((336, 609), (227, 783))
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
# TASK-207: under the contact physics the old reference (260,395)-(460,420), (560,460)-(240,760) loses (the ball
# leaves B's stream off the map, frame 166); lines 1-2 re-found from single-coordinate +-10..60 px shifts of the old
# reference, then --mode local: 24/24 +-2 px variants win, the reference wins on frame 182 (one A->B teleport).
LEVEL20_LINES = [((220, 395), (420, 420)), ((560, 460), (280, 800)), ((660, 500), (820, 580))]
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
# TASK-208: under the TASK-199/200/201 contact physics the old second line (1140,660)-(640,760) loses (the ball leaves
# the map on frame 477, artifacts/TASK-208/logs/trace_l22_oldref.jsonl); a single-coordinate shift of it, (1140,620), wins
# on frame 395 (A->B, A->B) with 19 of 24 +-2 px variants (artifacts/TASK-208/runs/g3_l22.json).
LEVEL22_LINES = [((150, 413), (420, 470)), ((1140, 620), (640, 760)), ((720, 482), (60, 540))]
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
# TASK-208: under the contact physics the old kicker (330,425)-(450,395) no longer clears B (B->A, off the map on
# frame 288, artifacts/TASK-208/logs/trace_l23_oldref.jsonl); (320,425) wins on frame 232 (A->B) with 14 of 16 +-2 px
# variants (artifacts/TASK-208/runs/g3_l23.json).
LEVEL23_LINES = [((320, 425), (450, 395)), ((880, 760), (1060, 580))]
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
# TASK-209: under the contact physics the old kicker (535,597)-(635,603) loses (A->B, then off the map on frame 298,
# artifacts/TASK-209/logs/trace_l25_oldref.jsonl; 2 of 16 +-2 px
# variants win, artifacts/TASK-209/runs/oldref/); a single-coordinate shift of it, (495,597), wins on frame 155 (A->B)
# with 12 of 16 +-2 px variants (artifacts/TASK-209/runs/g3_l25.json).
LEVEL25_LINES = [((495, 597), (635, 603)), ((920, 693), (980, 747))]
LEVEL25_MAX_FRAMES = 1500

# Level 26 ('one line, two jobs', srcId 26, lineK 4): line 1 tips the ball off its pad to the left; line 2, a long
# ramp under the pad's open side, carries the falling ball right to the shaft; line 3, a near-vertical backboard at
# the shaft (its right wall is too low), drops it steeply into floor portal A; B on the short right wall lets it out
# almost flat to the left, back over line 2, which it hits going the other way and bounces up-left off; line 4 at
# the left edge turns the rising ball right into the flag's pocket (won on physics frame 312, one teleport A->B).
# Found with exploration scans (artifacts/TASK-147/search/scan.py, same handleClick placement as
# tools/level_search.py): a lattice of ramps x backboards with a fixed release line, then reflectors at the left edge
# (artifacts/TASK-147/search_ref.json); keep these exact integer coordinates.
# TASK-210: under the contact physics the old ramp (20,480)-(700,580) loses: the ball falling off line 1 hits the
# ramp's left end point and leaves the map on frame 85 (artifacts/TASK-210/logs/trace_l26_oldref.jsonl; 0 of 32
# +-2 px variants win). Raising the ramp's left end, (10,450)-(700,620), wins on frame 310 (A->B) with 22 of 32
# +-2 px variants (artifacts/TASK-210/runs/g3_l26.json).
LEVEL26_LINES = [((230, 286), (90, 300)), ((10, 450), (700, 620)), ((860, 550), (868, 765)), ((15, 240), (15, 390))]
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
# TASK-211: under the contact physics the old line 2 (850,660)-(950,560) loses (the faster ball from B falls under
# it and leaves the map); line 2 is now (950,640)-(1070,790), from a 30 px lattice scan with line 1 kept
# (artifacts/TASK-211/runs/lat28_r.json): the ball from B bounces off it to the right wall, comes back and leaves its
# upper end up-right into the pocket (win frame 145, A->B, 15/15 +-2 px variants win).
LEVEL28_LINES = [((550, 255), (40, 570)), ((950, 640), (1070, 790))]
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
# TASK-212 (contact physics): the old reference still won (frame 122) but entered door A at y ~757, on the opening's
# lower edge, so only 12/32 +-2 px variants won (no line-2 or line-3 shift did). Line 2 moved to a lattice winner
# (lines 1, 3, 4 kept; 4/1886 win, best local): (780,730)-(840,690), win frame 124 (A->B), 22/32 variants win.
LEVEL31_LINES = [((1140, 430), (1220, 380)), ((780, 730), (840, 690)), ((96, 569), (144, 521)), ((521, 591), (561, 549))]
LEVEL31_MAX_FRAMES = 1500
# Level 32 ('under the wall', TASK-159, lineK 3; reference solution): line 1 kicks the ball, which bounces in place on its
# pad, off to the right; line 2 turns the falling ball flat into the low tunnel under the lid, so it drops into the left
# half of floor portal A (the wall x = 560 stands on A's centre). B (on the wall x = 760, facing right) throws it out of
# its lower half, and line 3 turns it back up into B's UPPER half, so it comes out of A's right half, under the wall, into
# the flag shaft (AB, BA). Found by a staged scan (artifacts/TASK-159/search/probe.py: 8 kicks x 1838 feed lines, 60
# reach A; then line 3 right of B, 54/3459 wins; this one's +-2 px neighbourhood wins 24/24;
# artifacts/TASK-159/search_ref.json); keep these exact integer coordinates.
# TASK-212 (contact physics): the old line 3 (893,682)-(863,598) sent the ball back into B (AB, BA, AB) and off the
# map on frame 143; line 3's lower end moved down 40 px (single-coordinate +-10..60 px shift search, 17/143 win, then
# --mode local on the best 4): (893,722)-(863,598) wins on frame 93 (AB, BA), 21/24 +-2 px variants win.
LEVEL32_LINES = [((154, 360), (217, 390)), ((326, 645), (420, 670)), ((893, 722), (863, 598))]
LEVEL32_MAX_FRAMES = 1500

# Levels 1-5 (srcId 1-5, no portals) references re-found for the TASK-199/200 contact physics (TASK-202): each is the
# best of the winning random candidates of tools/level_search.py sample runs, ranked by the share of its single-
# coordinate +-2 px variants that also win (all 100 %), with every drop-one variant losing (artifacts/TASK-202/search).
# Levels 1, 2 and 3 got new layouts in TASK-202 (js/levels.js). Keep these exact integer coordinates.
LEVEL1_LINES = [((537, 248), (83, 689))]
LEVEL1_MAX_FRAMES = 1500
LEVEL2_LINES = [((532, 325), (99, 714))]
LEVEL2_MAX_FRAMES = 1500
LEVEL3_LINES = [((387, 523), (1204, 103)), ((237, 446), (171, 44))]
LEVEL3_MAX_FRAMES = 1500
LEVEL4_LINES = [((100, 204), (774, 664)), ((548, 272), (296, 689))]
LEVEL4_MAX_FRAMES = 1500
LEVEL5_LINES = [((192, 621), (1083, 9))]
LEVEL5_MAX_FRAMES = 1500

# Levels 6-10 (srcId 6-10, no portals) references found for the TASK-199/200/201 contact physics (TASK-203), the
# same way as levels 1-5 (artifacts/TASK-203/search). Keep these exact integer coordinates.
LEVEL6_LINES = [((100, 200), (700, 300)), ((414, 763), (983, 626)), ((83, 604), (495, 778))]
LEVEL6_MAX_FRAMES = 1500
LEVEL7_LINES = [((964, 269), (393, 350))]
LEVEL7_MAX_FRAMES = 1500
LEVEL8_LINES = [((453, 480), (0, 565))]
LEVEL8_MAX_FRAMES = 1500
LEVEL9_LINES = [((476, 208), (188, 259))]  # level 9 layout changed in TASK-203 (wider gap in the x = 630 wall)
LEVEL9_MAX_FRAMES = 1500
LEVEL10_LINES = [((0, 460), (120, 580)), ((837, 355), (495, 687))]
LEVEL10_MAX_FRAMES = 1500

# Counts game frames that run physics and remembers the frame on which the level was completed.
LEVEL11_COUNTER_JS = """() => { window.__l11Frames = 0; window.__l11Win = null;
    const g = gameMechanics;
    gameMechanics = function() { const on = physics && !editorMode; const r = g();
        if (on) { ++window.__l11Frames;
            if (levelCompletedWindow && window.__l11Win === null) window.__l11Win = window.__l11Frames }
        return r } }"""


def play_solution(page, info, src, segments, max_frames, key, via=('A', 'B'), portals=2):
    # Pause menu -> level square index + 1, real clicks; then play the solution with real mouse
    # input: draw each line (click, move, click), press start (unless the last allowed line already
    # started physics), and wait until the level is completed
    # (at most max_frames physics frames) with at least one via[0] -> via[1] teleport (via None: a level without
    # portals, no teleport required; TASK-202).
    index = place_and_start(page, info, src, segments, key, portals=portals)
    page.wait_for_function("levelCompletedWindow || window.__l11Frames >= %d" % max_frames,
                           timeout=180000, polling=100)
    r = page.evaluate("""i => ({levelCompleted: levelCompletedWindow, winFrame: window.__l11Win,
        frames: window.__l11Frames, unlock: levels[i].unlock, ball: [ball.posX, ball.posY],
        teleports: portalState.teleports.map(t => ({step: t.step, from: t.from, to: t.to,
            before: t.before, after: t.after}))})""", index)
    info['play'] = r
    ab = [t for t in r['teleports'] if t['from'] == via[0] and t['to'] == via[1]] if via else [True]
    if not (r['levelCompleted'] and r['winFrame'] is not None and r['winFrame'] <= max_frames and ab):
        raise RuntimeError('%s not won with a %s->%s teleport: %s' % (key, via[0], via[1], {k: r[k] for k in (
            'levelCompleted', 'winFrame', 'frames', 'ball')}))
    # a fresh draw after the win so the screenshot shows the completed-level panel
    frames(page)


def place_and_start(page, info, src, segments, key, before_draw_js=None, portals=2):
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
    if st != {'thisLevel': index, 'drawMenu': False, 'portals': portals} or info['srcId'] != src:
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


def sc_level1(page, info):
    play_solution(page, info, 1, LEVEL1_LINES, LEVEL1_MAX_FRAMES, 'level1', via=None, portals=0)


def sc_level2(page, info):
    play_solution(page, info, 2, LEVEL2_LINES, LEVEL2_MAX_FRAMES, 'level2', via=None, portals=0)


def sc_level3_win(page, info):
    play_solution(page, info, 3, LEVEL3_LINES, LEVEL3_MAX_FRAMES, 'level3', via=None, portals=0)


def sc_level4(page, info):
    play_solution(page, info, 4, LEVEL4_LINES, LEVEL4_MAX_FRAMES, 'level4', via=None, portals=0)


def sc_level5(page, info):
    play_solution(page, info, 5, LEVEL5_LINES, LEVEL5_MAX_FRAMES, 'level5', via=None, portals=0)


def sc_level6(page, info):
    play_solution(page, info, 6, LEVEL6_LINES, LEVEL6_MAX_FRAMES, 'level6', via=None, portals=0)


def sc_level7(page, info):
    play_solution(page, info, 7, LEVEL7_LINES, LEVEL7_MAX_FRAMES, 'level7', via=None, portals=0)


def sc_level8(page, info):
    play_solution(page, info, 8, LEVEL8_LINES, LEVEL8_MAX_FRAMES, 'level8', via=None, portals=0)


def sc_level9(page, info):
    play_solution(page, info, 9, LEVEL9_LINES, LEVEL9_MAX_FRAMES, 'level9', via=None, portals=0)


def sc_level10(page, info):
    play_solution(page, info, 10, LEVEL10_LINES, LEVEL10_MAX_FRAMES, 'level10', via=None, portals=0)


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


# TASK-185: the player's lines per level (js/linestore.js, key bp.lines.v1 through PLATFORM.storage).
# Each lines_* scenario puts one record (state dumps + pass) into LINES; run_scenario adds the page's console
# error count and rewrites lines.json (all records of this run) after every lines_* scenario.
LINES = {}
LINES_STATE_JS = """async () => { const L = levels[thisLevel];
    const stored = (await PLATFORM.storage.getMany([LINES_STORE]))[LINES_STORE];
    let entry = null; try { entry = JSON.parse(stored)[L.srcId] || null } catch (e) { entry = 'unparsable' }
    return {thisLevel, srcId: L.srcId, lineK: L.lineK, linesK, nLevelLines: L.lines.length,
        player: lines.filter(l => l.type == 'player').map(l => [l.posX, l.posY, l.posX2, l.posY2]),
        ball: [ball.posX, ball.posY], ballStart: [L.ballX, L.ballY], ballSpeed: [ball.speedX, ball.speedY],
        physics, levelStarted, levelCompletedWindow, drawMenu, drawMap, sha: levelGeometrySha(L), entry,
        platformId: PLATFORM.getPlatformId()} }"""
LINE_X = ((700, 600), (900, 640))   # level 1 (srcId 1): away from the ball's start (512, 125)
LINE_Y = ((300, 700), (460, 730))
LINE_L2 = ((700, 500), (900, 520))  # level 2 (srcId 2)
PLAY_ICON_JS = "[menuIconRect[0][0] - 73 + 31, menuIconRect[0][1] + 31]"


def lines_state(page):
    return page.evaluate(LINES_STATE_JS)


def draw_seg(page, seg):
    # one player line with real input (click, move, click); returns the lines the game placed
    (x1, y1), (x2, y2) = seg
    n0 = page.evaluate("lines.filter(l => l.type == 'player').length")
    click(page, x1, y1)
    move(page, x2, y2)
    frames(page)
    click(page, x2, y2)
    st = lines_state(page)
    if len(st['player']) != n0 + 1:
        raise RuntimeError('line %s not placed: %s' % (seg, st['player']))
    return st


def pause_if_running(page):
    if page.evaluate("physics"):
        click(page, *page.evaluate(PLAY_ICON_JS))  # the play box toggles physics off (no win, no off-map reset)


def same_lines(a, b, eps=1e-6):
    return len(a) == len(b) and all(abs(p - q) <= eps for u, v in zip(a, b) for p, q in zip(u, v))


def reload_page(page):
    page.reload()
    page.wait_for_load_state('load')
    page.wait_for_function(BOOT_JS)
    frames(page, 3)


def lines_out(info, name, data):
    info['lines'] = data
    LINES[name] = data


def sc_lines_draft_restore(page, info):
    pick_level(page, 0)
    drawn = draw_seg(page, LINE_X)
    pause_if_running(page)
    pick_level(page, 1)
    other = lines_state(page)
    pick_level(page, 0)
    back = lines_state(page)
    d = {'drawn': drawn, 'level2': other, 'back': back}
    d['pass'] = bool(drawn['srcId'] == 1 and other['srcId'] == 2 and other['player'] == [] and back['srcId'] == 1
                     and same_lines(back['player'], drawn['player']) and back['linesK'] == len(drawn['player']) == drawn['linesK']
                     and back['entry'] and same_lines(back['entry']['draft'], drawn['player']) and back['entry']['passed'] is None
                     and back['linesK'] <= back['lineK'])
    lines_out(info, 'lines_draft_restore', d)


def sc_lines_reload(page, info):
    pick_level(page, 0)
    drawn = draw_seg(page, LINE_X)
    pause_if_running(page)
    pick_level(page, 1)
    drawn2 = draw_seg(page, LINE_L2)
    pause_if_running(page)
    reload_page(page)
    boot = lines_state(page)  # boot opens level 1 (thisLevel 0) with its saved lines
    pick_level(page, 1)
    back2 = lines_state(page)
    d = {'drawn': drawn, 'drawnLevel2': drawn2, 'afterReload': boot, 'afterReloadLevel2': back2}
    d['pass'] = bool(boot['srcId'] == 1 and same_lines(boot['player'], drawn['player']) and boot['linesK'] == len(drawn['player'])
                     and back2['srcId'] == 2 and same_lines(back2['player'], drawn2['player'])
                     and back2['linesK'] == len(drawn2['player']) and not boot['physics'] and not boot['levelStarted'])
    lines_out(info, 'lines_reload', d)


def bin_click(page):
    # select the (only) player line by clicking its midpoint, then click the bin
    mid = page.evaluate("(() => { const l = lines.find(l => l.type == 'player'); return [(l.posX + l.posX2) / 2, (l.posY + l.posY2) / 2] })()")
    click(page, *mid)
    if page.evaluate("playerSel") is None:
        raise RuntimeError('player line not selected')
    click(page, *page.evaluate("binCenter(lines[playerSel])"))


def sc_lines_passed_restore(page, info):
    pick_level(page, 0)
    x = draw_seg(page, LINE_X)
    # real win through gameMechanics' flagCollision with line X on the field (as win_level_src)
    page.evaluate("() => { const L = curLevel(); ball.posX = L.flagX + (flag[2][0] + flag[3][0]) / 2; ball.posY = L.flagY + (flag[2][1] + flag[3][1]) / 2; ball.speedX = ball.speedY = 0; physics = true }")
    page.wait_for_function("levelCompletedWindow", timeout=30000, polling=50)
    frames(page, 3)
    won = lines_state(page)
    # completion window 'restart' (blocks[2]): ball reset, line X kept and editable
    click(page, *page.evaluate("""[menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2,
        menuCoords[1] + blocks[2] + menuTextRect[1] / 2]"""))
    restarted = lines_state(page)
    bin_click(page)  # delete X
    deleted = lines_state(page)
    y = draw_seg(page, LINE_Y)  # change to Y, not won
    pause_if_running(page)
    changed = lines_state(page)
    pick_level(page, 1)
    pick_level(page, 0)
    back = lines_state(page)
    d = {'drawnX': x, 'won': won, 'restarted': restarted, 'deleted': deleted, 'drawnY': y, 'changed': changed, 'back': back}
    d['pass'] = bool(won['levelCompletedWindow'] and won['entry'] and same_lines(won['entry']['passed'], x['player'])
                     and same_lines(restarted['player'], x['player']) and deleted['player'] == [] and deleted['linesK'] == 0
                     and same_lines(deleted['entry']['draft'], []) and not changed['levelCompletedWindow']
                     and same_lines(changed['entry']['draft'], y['player']) and not same_lines(x['player'], y['player'])
                     and same_lines(back['player'], x['player']) and back['linesK'] == len(x['player']))
    lines_out(info, 'lines_passed_restore', d)


def sc_lines_restart_keeps(page, info):
    pick_level(page, 0)
    drawn = draw_seg(page, LINE_X)  # lineK 1: the last line starts the run
    frames(page, 20)
    running = lines_state(page)
    # HUD restart box (visible once a run started)
    r = page.evaluate("restartIconRect()")
    click(page, r[0] + r[2] / 2, r[1] + r[3] / 2)
    hud = lines_state(page)
    click(page, *page.evaluate(PLAY_ICON_JS))  # run again, then the pause menu 'restart' (i = 1)
    frames(page, 20)
    running2 = lines_state(page)
    open_menu(page)
    click(page, *page.evaluate("""[menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2,
        menuCoords[1] + 300 + 1 * 85 + menuTextRect[1] / 2]"""))
    menu = lines_state(page)
    def ok(s):
        return (same_lines(s['player'], drawn['player']) and s['linesK'] == drawn['linesK'] and s['ball'] == s['ballStart']
                and s['ballSpeed'] == [0, 0] and not s['physics'] and not s['levelStarted'] and not s['drawMenu'])
    d = {'drawn': drawn, 'running': running, 'afterHudRestart': hud, 'running2': running2, 'afterMenuRestart': menu}
    d['pass'] = bool(running['ball'] != running['ballStart'] and running2['ball'] != running2['ballStart'] and ok(hud) and ok(menu))
    lines_out(info, 'lines_restart_keeps', d)


def sc_lines_sha_mismatch(page, info):
    pick_level(page, 0)
    drawn = draw_seg(page, LINE_X)
    pause_if_running(page)
    pick_level(page, 1)
    drawn2 = draw_seg(page, LINE_L2)
    pause_if_running(page)
    # tamper level 1's sha in storage (through the facade); level 2's entry stays valid
    tampered = page.evaluate("""async () => { const v = JSON.parse((await PLATFORM.storage.getMany([LINES_STORE]))[LINES_STORE]);
        v[1].sha = 'deadbeef'; await PLATFORM.storage.setMany({[LINES_STORE]: JSON.stringify(v)}); return v }""")
    reload_page(page)
    l1 = lines_state(page)
    pick_level(page, 1)
    l2 = lines_state(page)
    d = {'drawn': drawn, 'drawnLevel2': drawn2, 'tamperedStore': tampered, 'level1': l1, 'level2': l2}
    d['pass'] = bool(tampered['1']['sha'] == 'deadbeef' and l1['srcId'] == 1 and l1['entry']['sha'] != l1['sha']
                     and l1['player'] == [] and l1['linesK'] == 0
                     and l2['srcId'] == 2 and same_lines(l2['player'], drawn2['player']))
    lines_out(info, 'lines_sha_mismatch', d)


def sc_lines_storage_blocked(page, info):
    # the backend's setMany throws from now on (the facade falls back with a console.warn, never an error)
    page.evaluate("() => { PLATFORM_BACKEND.storage.setMany = function() { throw new Error('blocked by test') } }")
    probe = page.evaluate("() => { try { PLATFORM_BACKEND.storage.setMany({}); return 'no throw' } catch (e) { return 'throws: ' + e.message } }")
    pick_level(page, 0)
    drawn = draw_seg(page, LINE_X)
    pause_if_running(page)
    pick_level(page, 1)
    pick_level(page, 0)
    back = lines_state(page)  # in-memory copy still restores the lines this session
    page.evaluate("() => { const L = curLevel(); ball.posX = L.flagX + (flag[2][0] + flag[3][0]) / 2; ball.posY = L.flagY + (flag[2][1] + flag[3][1]) / 2; ball.speedX = ball.speedY = 0; physics = true }")
    page.wait_for_function("levelCompletedWindow", timeout=30000, polling=50)
    won = lines_state(page)
    page.evaluate(LOOP_COUNTER_JS)
    frames(page, 10)
    f1 = page.evaluate("window.__loopFrames")
    d = {'backendProbe': probe, 'drawn': drawn, 'back': back, 'won': won, 'frameCount': [0, f1], 'gameRunning': f1 > 0}
    d['pass'] = bool(probe.startswith('throws') and same_lines(back['player'], drawn['player']) and won['levelCompletedWindow']
                     and d['gameRunning'])
    lines_out(info, 'lines_storage_blocked', d)


def lines_tag_rewriter(tb, backend):
    # one-argument handler (Playwright passes the request too when the handler takes two arguments)
    tag = tb.backend_tag(backend)

    def rewrite(route):
        resp = route.fetch()
        route.fulfill(response=resp, body=resp.text().replace(tb.LOCAL_TAG, tag))
    return rewrite


def sc_lines_backends(page, info):
    # every platform backend (tests/platform/test_backends.py tag rewrite over a local http server):
    # draw on level 1, reload, level 1 comes back with the line
    sys.path.insert(0, os.path.join(ROOT, 'tests', 'platform'))
    import test_backends as tb
    from functools import partial
    from http.server import ThreadingHTTPServer
    from threading import Thread
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(tb.QuietHandler, directory=ROOT))
    Thread(target=server.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/index.html' % server.server_port
    out = []
    try:
        for backend in tb.BACKENDS:
            ctx = page.context.browser.new_context(viewport=VIEWPORT)
            errors = []
            try:
                ctx.route('**/index.html', lines_tag_rewriter(tb, backend))
                p = ctx.new_page()
                p.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                p.on('pageerror', lambda e: errors.append(str(e)))
                p.goto(url)
                p.wait_for_function(tb.READY, timeout=15000)
                frames(p)
                pick_level(p, 0)
                drawn = draw_seg(p, LINE_X)
                pause_if_running(p)
                reload_page(p)
                p.wait_for_function(tb.READY, timeout=15000)
                back = lines_state(p)
                r = {'backend': backend, 'platformId': back['platformId'], 'drawn': drawn['player'], 'restored': back['player'],
                     'linesK': back['linesK'], 'consoleErrors': len(errors), 'errors': errors}
            except Exception as e:
                r = {'backend': backend, 'exception': '%s: %s' % (type(e).__name__, str(e).splitlines()[0] if str(e) else ''),
                     'consoleErrors': len(errors), 'errors': errors}
            finally:
                ctx.close()
            r['pass'] = bool('exception' not in r and r['platformId'] == backend and r['drawn']
                             and same_lines(r['restored'], r['drawn']) and r['linesK'] == len(r['drawn']) and not errors)
            out.append(r)
    finally:
        server.shutdown()
        server.server_close()
    d = {'backends': out, 'nPass': sum(r['pass'] for r in out)}
    d['pass'] = bool(len(out) == 5 and all(r['pass'] for r in out))
    lines_out(info, 'lines_backends', d)



# TASK-187: '3x speed' HUD box (UI + state; speed itself is TASK-188). speed_* scenarios add one record each to SPEED
# (written to speed.json by run_scenario with the page's final console error count).
SPEED = {}
SPEED_STATE_JS = """async () => ({speedMul, visible: speedIconVisible(), restartVisible: restartIconVisible(),
    rect: speedIconRect(), restartRect: restartIconRect(), levelStarted, physics, line: !!line,
    nPlayer: lines.filter(l => l.type == 'player').length, linesK,
    stored: (await PLATFORM.storage.getMany([SPEED_STORE]))[SPEED_STORE]})"""
# counts drawSpeedIcon calls (draw.js calls it through the global name every frame while visible)
SPEED_DRAW_COUNTER_JS = """() => { if (window.__speedDraws === undefined) { window.__speedDraws = 0; const f = drawSpeedIcon;
    drawSpeedIcon = function() { ++window.__speedDraws; return f.apply(this, arguments) } } return window.__speedDraws }"""


def speed_state(page):
    return page.evaluate(SPEED_STATE_JS)


def speed_run(page):
    # level 1 (srcId 1, lineK 1): one player line with real input, then the run (the last line starts it; the play box
    # is clicked only if it did not); a few frames so the ball is moving but still on the map
    if page.evaluate("levels[thisLevel].srcId") != 1:
        pick_level(page, page.evaluate("levelBySrc(1)"))
    draw_seg(page, LINE_X)
    if not page.evaluate("levelStarted"):
        click(page, *page.evaluate(PLAY_ICON_JS))
    frames(page, 4)
    st = speed_state(page)
    if not (st['levelStarted'] and st['visible']):
        raise RuntimeError('run not started / speed box hidden: %s' % st)
    return st


def speed_click(page):
    r = page.evaluate("speedIconRect()")
    click(page, r[0] + r[2] / 2, r[1] + r[3] / 2)
    return speed_state(page)


def speed_out(info, name, data):
    info['speed'] = data
    SPEED[name] = data


def sc_speed_off(page, info):
    st = speed_run(page)
    # '3x' label ink box in logical px (same font / anchor as drawSpeedIcon), excluded from the arrow bbox in centre.json
    label = page.evaluate("""() => { const r = speedIconRect(); ctx.save(); ctx.font = '23px ' + THEME.fontStack;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; const m = ctx.measureText('3x'); ctx.restore();
        const x = r[0] + 48, y = r[1] + 49;
        return [x - m.actualBoundingBoxLeft, y - m.actualBoundingBoxAscent, x + m.actualBoundingBoxRight, y + m.actualBoundingBoxDescent] }""")
    speed_out(info, 'speed_off', {'state': st, 'label': label, 'pass': bool(st['speedMul'] == 1 and st['visible'])})


def sc_speed_on(page, info):
    speed_run(page)
    st = speed_click(page)
    speed_out(info, 'speed_on', {'state': st, 'pass': bool(st['speedMul'] == 3 and st['visible'] and st['stored'] == '3')})


def sc_speed_toggle(page, info):
    run = speed_run(page)
    r = run['rect']
    # TASK-188: 3x really runs 3x faster, so the level-1 ball would leave the map (run over, box hidden) before the
    # last tap; pause the run with the play box first (levelStarted stays true, the speed box stays visible)
    click(page, *page.evaluate(PLAY_ICON_JS))
    frames(page)
    if page.evaluate("physics") or not speed_state(page)['visible']:
        raise RuntimeError('speed_toggle: run not paused / speed box hidden')
    one = speed_click(page)   # mouse click: 1 -> 3
    two = speed_click(page)   # mouse click: 3 -> 1
    # the same with two touch taps (touchstart + touchend inside TAP_SLOP -> handleClick)
    tx, ty = to_client(page, r[0] + r[2] / 2, r[1] + r[3] / 2)
    page.touchscreen.tap(tx, ty)
    frames(page)
    tap1 = speed_state(page)
    page.touchscreen.tap(tx, ty)
    frames(page)
    tap2 = speed_state(page)
    seq = [run, one, two, tap1, tap2]
    d = {'mouse': [s['speedMul'] for s in seq[:3]], 'touch': [two['speedMul'], tap1['speedMul'], tap2['speedMul']],
         'nPlayer': [s['nPlayer'] for s in seq], 'lineStarted': [s['line'] for s in seq],
         'stored': [s['stored'] for s in seq], 'rect': r, 'restartRect': run['restartRect']}
    d['gapPx'] = run['restartRect'][0] - (r[0] + r[2])
    d['pass'] = bool(d['mouse'] == [1, 3, 1] and d['touch'] == [1, 3, 1] and len(set(d['nPlayer'])) == 1
                     and not any(d['lineStarted']) and d['stored'][1:] == ['3', '1', '3', '1']
                     and r[2] == r[3] == 63 and d['gapPx'] == 10 and r[0] == run['restartRect'][0] - 73)
    speed_out(info, 'speed_toggle', d)


def bright_count(page, rect):
    # screenshot of the rect (CSS px clip, device pixels in the PNG): pixels with every channel > 160
    from PIL import Image
    import io
    x1, y1 = to_client(page, rect[0] + 3, rect[1] + 3)
    x2, y2 = to_client(page, rect[0] + rect[2] - 3, rect[1] + rect[3] - 3)
    im = Image.open(io.BytesIO(page.screenshot(clip={'x': x1, 'y': y1, 'width': x2 - x1, 'height': y2 - y1}))).convert('RGB')
    return sum(1 for p in im.getdata() if min(p) > 160)


def sc_speed_hidden(page, info):
    if page.evaluate("levels[thisLevel].srcId") != 1:
        pick_level(page, page.evaluate("levelBySrc(1)"))
    page.evaluate(SPEED_DRAW_COUNTER_JS)
    frames(page, 3)
    before = speed_state(page)
    r = before['rect']
    draws0 = page.evaluate("window.__speedDraws")
    hiddenBright = bright_count(page, r)
    clicked = speed_click(page)  # before the run: no toggle (the box is not there)
    page.keyboard.press('Escape')
    page.evaluate("() => { line = false; bounce.cancel(); levelChoosed(thisLevel) }")  # drop a line the click may have started
    frames(page)
    shown = speed_run(page)
    page.evaluate("() => { window.__speedDraws = 0 }")
    frames(page, 3)
    draws1 = page.evaluate("window.__speedDraws")
    shownBright = bright_count(page, r)
    d = {'before': before, 'drawCallsHidden': draws0, 'brightHidden': hiddenBright, 'afterClickHidden': clicked,
         'shown': shown, 'drawCallsShown': draws1, 'brightShown': shownBright}
    d['pass'] = bool(not before['visible'] and not before['levelStarted'] and draws0 == 0 and hiddenBright == 0
                     and clicked['speedMul'] == 1 and clicked['stored'] is None
                     and shown['visible'] and draws1 > 0 and shownBright > 100)
    speed_out(info, 'speed_hidden', d)


def sc_speed_reload(page, info):
    speed_run(page)
    on = speed_click(page)
    reload_page(page)
    after = speed_state(page)
    d = {'set': on, 'afterReload': after}
    d['pass'] = bool(on['speedMul'] == 3 and on['stored'] == '3' and after['speedMul'] == 3 and after['stored'] == '3')
    speed_out(info, 'speed_reload', d)


# TASK-191: level telemetry (js/telemetry.js) with the none analytics backend. The scenario opens its own context on a
# local http server whose index.html has the GameAnalytics SDK tag dropped and the gameanalytics backend tag swapped for
# analytics/backends/none.js (tests/platform/test_analytics.py), plays the script in tests/visual/telemetry_expected_levels.json
# with real input, compares the filtered ANALYTICS.debugLog with the expected list, reloads and reads bp.stats.v1.
# Writes sequence_levels.json (TASK-192; was sequence.json) and counters.json (compact) next to the screenshots.
TELEMETRY_EXPECTED = os.path.join(ROOT, 'tests', 'visual', 'telemetry_expected_levels.json')
TELEMETRY_LOG_JS = """() => ANALYTICS.debugLog.filter(e => e.fn == 'addProgressionEvent'
    || (e.fn == 'addDesignEvent' && String(e.args[0]).startsWith('level:')))
    .map(e => e.fn == 'addProgressionEvent' ? [e.fn, e.args[0], e.args[1]] : [e.fn, e.args[0], e.args[1] ?? null])"""
WIN_RESTART_JS = """[menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2, menuCoords[1] + blocks[2] + menuTextRect[1] / 2]"""


def telemetry_match(actual, expected):
    if len(actual) != len(expected):
        return False
    for a, e in zip(actual, expected):
        if e[2] == 'time>0':
            if a[:2] != e[:2] or not (isinstance(a[2], (int, float)) and a[2] > 0):
                return False
        elif a != e:
            return False
    return True


def telemetry_run(p):
    # a run: the last line starts it, else the play box
    if not p.evaluate("levelStarted && physics"):
        click(p, *p.evaluate(PLAY_ICON_JS))
    if not p.evaluate("levelStarted && physics"):
        raise RuntimeError('run did not start')


# Full ANALYTICS.debugLog of each telemetry scenario ([fn, ...args]); telemetry_ui computes coverage.json from both
TELEMETRY_LOGS = {}
FULL_LOG_JS = "() => ANALYTICS.debugLog.map(e => [e.fn, ...e.args.map(a => a === undefined ? null : a)])"


# TASK-193: tests/platform/live_check.py sets these to run telemetry_ui with the committed gameanalytics backend
# (index.html unchanged) and js/buildinfo.js stamped with TELEMETRY_BUILD; the defaults keep the none backend
TELEMETRY_BACKEND = 'none'
TELEMETRY_BUILD = None
TELEMETRY_PAGE_HOOK = None  # called with the new page before the first load (live_check: request/response capture)
TELEMETRY_CLOSE_HOOK = None  # called with the page before its context closes (live_check: wait for the relay answers)
TELEMETRY_STEP_HOOK = None  # telemetry_ui / telemetry_editor: called with (page, step name) after each step (live_check: timed SDK sends)


@contextlib.contextmanager
def telemetry_page(page, errors, init=None, boot_timeout=15000, **ctx_options):
    # own context on a local http server; index.html with the GA SDK tag dropped and the none backend swapped in
    sys.path.insert(0, os.path.join(ROOT, 'tests', 'platform'))
    import test_analytics as ta
    from functools import partial
    from http.server import ThreadingHTTPServer
    from threading import Thread
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(ta.QuietHandler, directory=ROOT))
    Thread(target=server.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/index.html' % server.server_port

    def rewrite(route):
        resp = route.fetch()
        body = resp.text().replace(ta.SDK_TAG + '\n', '').replace(ta.GA_TAG, ta.NONE_TAG)
        route.fulfill(response=resp, body=body)

    def buildinfo(route):
        resp = route.fetch()
        route.fulfill(response=resp, body=ta.stamp_build.stamped(resp.text(), TELEMETRY_BUILD))
    ctx = page.context.browser.new_context(viewport=VIEWPORT, **ctx_options)
    try:
        if TELEMETRY_BACKEND == 'none':
            ctx.route('**/index.html', rewrite)
        if TELEMETRY_BUILD:
            ctx.route('**/js/buildinfo.js', buildinfo)
        p = ctx.new_page()
        if TELEMETRY_PAGE_HOOK:
            TELEMETRY_PAGE_HOOK(p)
        p.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        p.on('pageerror', lambda e: errors.append(str(e)))
        if init:  # TASK-238: page.clock / CDP throttling before the first load
            init(p)
        p.goto(url)
        p.wait_for_function(BOOT_JS, timeout=boot_timeout)
        frames(p)
        yield p
        if TELEMETRY_CLOSE_HOOK:
            TELEMETRY_CLOSE_HOOK(p)
    finally:
        ctx.close()
        server.shutdown()
        server.server_close()


def sc_telemetry_levels(page, info):
    with open(TELEMETRY_EXPECTED) as f:
        want = json.load(f)
    errors, steps = [], []
    with telemetry_page(page, errors) as p:
        backend = p.evaluate("ANALYTICS_BACKEND.backendId")

        def step(name):
            steps.append({'step': name, 'srcId': p.evaluate("levels[thisLevel].srcId"),
                          'attempt': p.evaluate("TELEMETRY.attempt() && TELEMETRY.attempt().n")})
        step('boot')
        if p.evaluate("levels[thisLevel].srcId") != 1:
            raise RuntimeError('boot did not open srcId 1')
        draw_seg(p, LINE_X)  # line X is away from the ball: the ball falls off the map
        telemetry_run(p)
        step('run1')
        p.wait_for_function("TELEMETRY.attempt().n == 2 && !levelStarted", timeout=30000, polling=50)
        step('offmap')
        telemetry_run(p)
        frames(p, 3)
        r = p.evaluate("restartIconRect()")
        if not p.evaluate("restartIconVisible()"):
            raise RuntimeError('restart box hidden')
        click(p, r[0] + r[2] / 2, r[1] + r[3] / 2)
        step('restart')
        telemetry_run(p)
        # the run goes through gameMechanics' flagCollision: the ball is put on the flag (as win_level_src)
        p.evaluate("() => { const L = curLevel(); ball.posX = L.flagX + (flag[2][0] + flag[3][0]) / 2; ball.posY = L.flagY + (flag[2][1] + flag[3][1]) / 2; ball.speedX = ball.speedY = 0 }")
        p.wait_for_function("levelCompletedWindow", timeout=30000, polling=50)
        step('win')
        click(p, *p.evaluate(WIN_RESTART_JS))  # the completion window has no map button
        step('winRestart')
        pick_level(p, 1)
        step('level2')
        open_map(p)
        step('map')
        actual = p.evaluate(TELEMETRY_LOG_JS)
        full = p.evaluate(FULL_LOG_JS)
        stats_before = p.evaluate("JSON.parse(JSON.stringify(TELEMETRY.stats()))")
        reload_page(p)
        after = p.evaluate(TELEMETRY_LOG_JS)
        stored = p.evaluate("async () => (await PLATFORM.storage.getMany([STATS_STORE]))[STATS_STORE]")
        mem = p.evaluate("JSON.parse(JSON.stringify(TELEMETRY.stats()))")
        backend_after = p.evaluate("ANALYTICS_BACKEND.backendId")
        full_after = p.evaluate(FULL_LOG_JS)
    TELEMETRY_LOGS['telemetry_levels'] = full + full_after
    seq = {'backend': [backend, backend_after], 'steps': steps, 'expected': want['events'], 'debugLog': actual,
           'expectedAfterReload': want['afterReload'], 'debugLogAfterReload': after, 'consoleErrors': len(errors), 'errors': errors}
    seq['matchExpected'] = telemetry_match(actual, want['events'])
    seq['matchAfterReload'] = telemetry_match(after, want['afterReload'])
    seq['pass'] = bool(seq['matchExpected'] and seq['matchAfterReload'] and backend == backend_after == 'none' and not errors)
    parsed = json.loads(stored) if stored else None
    rows = {}
    for sid, exp in want['counters'].items():
        got = (parsed or {}).get(sid, {})
        rows[sid] = {'expected': exp, 'stored': got, 'match': all(got.get(k) == v for k, v in exp.items()),
                     'secondsPositive': isinstance(got.get('seconds'), (int, float)) and got['seconds'] > 0}
    cnt = {'key': 'bp.stats.v1', 'storedRaw': stored, 'statsBeforeReload': stats_before, 'inMemoryAfterReload': mem,
           'note': 'read after the reload; the reload boot opens level 1 again (attempt 5 of srcId 1)', 'rows': rows}
    cnt['pass'] = bool(parsed is not None and all(r['match'] and r['secondsPositive'] for r in rows.values()))
    seq['fullLog'] = full
    seq['fullLogAfterReload'] = full_after
    # TASK-192: sequence.json is telemetry_ui's file now
    with open(os.path.join(OUT_DIR, 'sequence_levels.json'), 'w') as f:
        json.dump(seq, f, separators=(',', ':'))
    with open(os.path.join(OUT_DIR, 'counters.json'), 'w') as f:
        json.dump(cnt, f, separators=(',', ':'))
    info['telemetry'] = {'sequencePass': seq['pass'], 'countersPass': cnt['pass'], 'events': len(actual)}
    if not seq['pass']:
        raise RuntimeError('telemetry sequence mismatch (sequence_levels.json)')
    if not cnt['pass']:
        raise RuntimeError('telemetry counters mismatch (counters.json)')


# TASK-192: UI, line and session telemetry. Same page setup as telemetry_levels (none backend, own context, touch on).
# Real input for every button (mouse, plus one touch tap on the HUD menu icon); the play-time milestones are driven with
# TELEMETRY.tick (the game loop's own per-frame call, here with large steps), page hide with a visibilitychange to
# hidden and a pagehide event. ui:/lines:/session: events of ANALYTICS.debugLog must equal
# tests/visual/telemetry_expected_ui.json. Writes sequence.json; coverage.json (every event id of docs/telemetry.md
# seen in the telemetry_levels + telemetry_ui logs) when telemetry_levels ran first in the same shoot.py run.
TELEMETRY_UI_EXPECTED = os.path.join(ROOT, 'tests', 'visual', 'telemetry_expected_ui.json')
TELEMETRY_DOC = os.path.join(ROOT, 'docs', 'telemetry.md')
TELEMETRY_UI_LOG_JS = """() => ANALYTICS.debugLog.filter(e => e.fn == 'addDesignEvent' && /^(ui|lines|session):/.test(String(e.args[0])))
    .map(e => [e.fn, e.args[0], e.args[1] ?? null])"""
MENU_ICON_JS = "[menuIconRect[0][0] + 31, menuIconRect[0][1] + 31]"
MENU_BUTTON_JS = """i => [menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2,
    menuCoords[1] + 300 + i * 85 + menuTextRect[1] / 2]"""
WIN_NEXT_JS = """[menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2 + menuTextRect[0] / 2, menuCoords[1] + blocks[1] + menuTextRect[1] / 2]"""
EDITOR_BUTTON_JS = "(() => { const r = editorButtonRect(); return [r[0] + r[2] / 2, r[1] + r[3] / 2] })()"
REJECT_POINT = (200, 400)


def box_centre(p, rect_js):
    r = p.evaluate(rect_js)
    return r[0] + r[2] / 2, r[1] + r[3] / 2


def telemetry_doc_ids():
    # first cell of every catalogue row: progression `S`, `L<srcId>` | facade `fn` | `design:id:<srcId>:<ctx>`
    rows = []
    with open(TELEMETRY_DOC) as f:
        for line in f:
            if not line.startswith('| ') or line.startswith('| event id') or line.startswith('|--'):
                continue
            cell = re.split(r'(?<!\\)\|', line)[1].strip().replace('\\|', '|')  # TASK-233: '\\|' inside a cell
            toks = re.findall(r'`([^`]+)`', cell)
            if not toks:
                continue
            if cell.startswith('progression'):
                rows.append({'row': cell, 'kind': 'progression', 'status': toks[0]})
            elif cell.startswith('facade'):
                rows.append({'row': cell, 'kind': 'facade', 'fn': toks[0]})
            elif ':' in toks[0]:
                ph = {'<srcId>': r'\d+', '<ctx>': r'(L\d+|map)', '<from>': '(menu|win)', '<h>': '[0-9a-f]{8}',
                      '<code>': '[a-z0-9_]{1,64}'}  # TASK-232; TASK-234 <code>
                # TASK-233: '<a|b|c>' = one of the listed words
                pat = ''.join(ph.get(x, '(' + x[1:-1] + ')' if x.startswith('<') and '|' in x else re.escape(x))
                              for x in re.split(r'(<[^>]+>)', toks[0]))
                rows.append({'row': cell, 'kind': 'design', 'regex': '^' + pat + '$'})
    return rows


def telemetry_coverage(logs, editor=False):
    # TASK-232: editor: rows are covered by telemetry_editor's own log (editor=True), all other rows by levels + ui
    # TASK-236: editor=None = every catalogue row (editor:/edit: included) against all the logs given
    rows = [r for r in telemetry_doc_ids() if editor is None or r['row'].startswith(('`editor:', '`edit:')) == editor]
    out = []
    for r in rows:
        hits = 0
        for name, log in logs.items():
            for e in log:
                if r['kind'] == 'progression':
                    ok = e[0] == 'addProgressionEvent' and e[1] == r['status']
                elif r['kind'] == 'facade':
                    ok = e[0] == r['fn']
                else:
                    ok = e[0] == 'addDesignEvent' and re.match(r['regex'], str(e[1])) is not None
                hits += ok
        out.append({'id': r['row'], 'hits': hits})
    uncovered = [r['id'] for r in out if r['hits'] == 0]
    return {'doc': 'docs/telemetry.md', 'logs': {k: len(v) for k, v in logs.items()}, 'rows': out,
            'catalogueRows': len(out), 'uncovered': uncovered, 'pass': bool(out and not uncovered)}


def write_coverage():
    """coverage.json once telemetry_levels and telemetry_ui have run: their rows (TASK-192); with telemetry_editor too
    (TASK-236) every catalogue row incl. editor:/edit: against all three logs. None before levels + ui."""
    if not {'telemetry_levels', 'telemetry_ui'} <= set(TELEMETRY_LOGS):
        return None
    full = 'telemetry_editor' in TELEMETRY_LOGS
    cov = telemetry_coverage(TELEMETRY_LOGS, editor=None if full else False)
    cov['scope'] = 'all rows, levels+ui+editor logs' if full else 'non-editor rows, levels+ui logs'
    with open(os.path.join(OUT_DIR, 'coverage.json'), 'w') as f:
        json.dump(cov, f, separators=(',', ':'))
    return cov


def sc_telemetry_ui(page, info):
    with open(TELEMETRY_UI_EXPECTED) as f:
        want = json.load(f)
    errors, steps = [], []
    with telemetry_page(page, errors, has_touch=True) as p:
        backend = p.evaluate("ANALYTICS_BACKEND.backendId")
        p.evaluate("() => { window.__inputs = {click: 0, touchend: 0}; document.addEventListener('click', () => ++__inputs.click, true);"
                   " canvas.addEventListener('touchend', () => ++__inputs.touchend, true) }")

        def step(name):
            n = p.evaluate("ANALYTICS.debugLog.length")
            steps.append({'step': name, 'srcId': p.evaluate("levels[thisLevel].srcId"), 'logLength': n})
            if TELEMETRY_STEP_HOOK:
                TELEMETRY_STEP_HOOK(p, name)
        if p.evaluate("levels[thisLevel].srcId") != 1 or p.evaluate("curLevel().lineK") != 1:
            raise RuntimeError('boot did not open srcId 1 (lineK 1)')
        step('boot')
        draw_seg(p, LINE_X)  # the last line (lineK 1) starts the run
        click(p, *p.evaluate(PLAY_ICON_JS))  # pause
        if p.evaluate("physics") or not p.evaluate("speedIconVisible()"):
            raise RuntimeError('run not paused / speed box hidden')
        step('place+pause')
        click(p, *box_centre(p, "speedIconRect()"))
        click(p, *box_centre(p, "speedIconRect()"))
        step('speed on/off')
        click(p, *p.evaluate(PLAY_ICON_JS))  # run again
        click(p, *box_centre(p, "restartIconRect()"))
        if p.evaluate("levelStarted"):
            raise RuntimeError('HUD restart did not reset the run')
        step('run+restart')
        if p.evaluate("p => playerLineAt(p[0], p[1])", list(REJECT_POINT)) is not None:
            raise RuntimeError('reject point hits a player line')
        click(p, *REJECT_POINT)  # lineK reached: nothing starts
        if p.evaluate("!!line"):
            raise RuntimeError('a line started over the limit')
        step('reject_limit')
        end = p.evaluate("(() => { const l = lines.find(l => l.type == 'player'); return [l.posX2, l.posY2] })()")
        p.mouse.move(*to_client(p, *end))
        p.mouse.down()
        for k in range(1, 6):
            p.mouse.move(*to_client(p, end[0] + 10 * k, end[1] - 8 * k))
        p.mouse.up()
        frames(p)
        moved = p.evaluate("(() => { const l = lines.find(l => l.type == 'player'); return [l.posX2, l.posY2] })()")
        if moved == end:
            raise RuntimeError('drag did not move the end')
        step('drag')
        bin_click(p)
        if p.evaluate("lines.filter(l => l.type == 'player').length") != 0:
            raise RuntimeError('bin did not delete the line')
        step('bin')
        draw_seg(p, LINE_X)  # placed again (index 1 of this attempt), the run starts
        p.touchscreen.tap(*to_client(p, *p.evaluate(MENU_ICON_JS)))  # the touch tap
        frames(p)
        if not p.evaluate("drawMenu"):
            raise RuntimeError('touch tap on the menu icon did not open the menu')
        step('touch menu_open')
        click(p, *p.evaluate(MENU_BUTTON_JS, 0))  # resume
        step('resume')
        open_map(p)
        click(p, *p.evaluate(MENU_ICON_JS))  # map -> back to the pause menu
        if p.evaluate("drawMap") or not p.evaluate("drawMenu"):
            raise RuntimeError('map menu icon did not go back to the pause menu')
        step('map_close')
        click(p, *p.evaluate(LEVELS_BUTTON_JS))
        pt = p.evaluate(LEVEL_POINT_JS, 1)
        click(p, *pt)  # select level 2: card shown
        play = p.evaluate("mapCardLayout(1).play")
        move(p, play[0], play[1])
        frames(p)
        click(p, play[0], play[1])  # the card's play button
        if p.evaluate("levels[thisLevel].srcId") != 2 or p.evaluate("drawMap"):
            raise RuntimeError('preview play did not start level 2')
        step('map_level+preview_play')
        telemetry_run(p)  # play box, no lines
        p.evaluate("() => { const L = curLevel(); ball.posX = L.flagX + (flag[2][0] + flag[3][0]) / 2; ball.posY = L.flagY + (flag[2][1] + flag[3][1]) / 2; ball.speedX = ball.speedY = 0 }")
        p.wait_for_function("levelCompletedWindow", timeout=30000, polling=50)
        click(p, *p.evaluate(WIN_NEXT_JS))
        if p.evaluate("thisLevel") != 2 or p.evaluate("levels[thisLevel].srcId") != 11:
            raise RuntimeError('next level did not open play-order level 3 (srcId 11)')
        step('next_level')
        before = p.evaluate("TELEMETRY.playSeconds()")
        if before >= 25:
            raise RuntimeError('real active play already %.1f s (milestone order not deterministic)' % before)
        for m in (30, 60, 120, 300, 600):
            p.evaluate("m => TELEMETRY.tick((m - TELEMETRY.playSeconds()) * 1000 + 500)", m)
        step('play_seconds')
        p.evaluate("() => { Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'});"
                   " Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});"
                   " document.dispatchEvent(new Event('visibilitychange'));"
                   " delete document.visibilityState; delete document.hidden;"
                   " document.dispatchEvent(new Event('visibilitychange')) }")
        step('hide')
        open_menu(p)
        click(p, *p.evaluate(EDITOR_BUTTON_JS))
        if not p.evaluate("editorMode"):
            raise RuntimeError('editor button did not open the editor')
        step('editor_open')
        p.evaluate("() => window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: false}))")
        step('pagehide')
        actual = p.evaluate(TELEMETRY_UI_LOG_JS)
        full = p.evaluate(FULL_LOG_JS)
        inputs = p.evaluate("window.__inputs")
        play_secs = p.evaluate("TELEMETRY.playSeconds()")
    TELEMETRY_LOGS['telemetry_ui'] = full
    seq = {'backend': backend, 'steps': steps, 'expected': want['events'], 'debugLog': actual,
           'playSecondsBeforeTicks': before, 'playSecondsEnd': play_secs, 'inputs': inputs,
           'consoleErrors': len(errors), 'errors': errors, 'fullLog': full}
    seq['matchExpected'] = telemetry_match(actual, want['events'])
    seq['touchTap'] = bool(inputs['touchend'] >= 1)
    seq['pass'] = bool(seq['matchExpected'] and backend == TELEMETRY_BACKEND and not errors and seq['touchTap'])
    with open(os.path.join(OUT_DIR, 'sequence.json'), 'w') as f:
        json.dump(seq, f, separators=(',', ':'))
    cov = write_coverage()
    info['telemetry'] = {'sequencePass': seq['pass'], 'events': len(actual),
                         'coverage': None if cov is None else {'pass': cov['pass'], 'uncovered': cov['uncovered']}}
    if not seq['pass']:
        raise RuntimeError('telemetry ui sequence mismatch (sequence.json)')
    if cov is not None and not cov['pass']:
        raise RuntimeError('telemetry coverage: uncovered %s (coverage.json)' % cov['uncovered'])


# TASK-232: editor session and level summary telemetry (js/telemetry.js, editor:*). Same page setup as telemetry_levels
# (none backend, own context). Real clicks: editor from the pause menu, line tool + one line, play-test, the HUD 'edit'
# box back, export, exit; a win, the completion window's editor button, exit unchanged; the editor from the menu again and
# a pagehide (abandon). The editor: events of ANALYTICS.debugLog must equal tests/visual/telemetry_expected_editor.json
# ('time>0' = any number > 0). Writes sequence_editor.json and hash.json (levelHash checks + an independent Python FNV-1a).
TELEMETRY_EDITOR_EXPECTED = os.path.join(ROOT, 'tests', 'visual', 'telemetry_expected_editor.json')
TELEMETRY_EDITOR_LOG_JS = """() => ANALYTICS.debugLog.filter(e => e.fn == 'addDesignEvent' && /^edit(or)?:/.test(String(e.args[0])))
    .map(e => [e.fn, e.args[0], e.args[1] ?? null])"""
EDITOR_LINE = ((300, 560), (520, 640))
GA_PART = re.compile(r'^[A-Za-z0-9 \-_.()!?]{1,64}$')


EDITOR_BTN_CENTRE_JS = "id => { const b = EDITOR_BUTTONS.find(b => b.id == id); return [b.x + b.w / 2, b.y + b.h / 2] }"


def editor_tool(p, bid):
    click(p, *p.evaluate(EDITOR_BTN_CENTRE_JS, bid))


def fnv1a(s):
    h = 0x811c9dc5
    for ch in s:
        h = ((h ^ ord(ch)) * 0x01000193) & 0xffffffff
    return '%08x' % h


def ga_design_id_ok(eid):
    parts = eid.split(':')
    return 1 <= len(parts) <= 5 and all(GA_PART.match(x) for x in parts)


# TASK-233: an editor session from the pause menu that clicks every toolbar button: select, snap on / off, ⟳ on the
# flag, new, lines − twice (the second clamped at 0), lines +, two level lines, a portal pair, ⟲ on the selected portal,
# size − / size + / size + (refused: portal B's line is too short for h 60), ⟳ on the selected line, the delete tool by a
# touch tap, a toolbar drag, export, import of the exported file / a non-JSON file / a version 1 file with portals, exit.
EDITOR_TB_LINE_A = ((150, 300), (650, 300))
EDITOR_IMPORT_WAIT_JS = """n => ANALYTICS.debugLog.slice(n).some(e => e.fn == 'addDesignEvent' && String(e.args[0]).startsWith('editor:import:'))"""


def toolbar_session(p, tb, step):
    open_menu(p)
    click(p, *p.evaluate(EDITOR_BUTTON_JS))
    if not p.evaluate("editorMode"):
        raise RuntimeError('menu editor button did not open the editor (toolbar session)')
    step('open menu toolbar')
    tb('select')
    tb('snap')
    tb('snap')
    if p.evaluate("editor.snap"):
        raise RuntimeError('snap is still on')
    tb('flagCW')  # nothing selected: the flag
    tb('new')
    if p.evaluate("editor.level.lines.length") != 0:
        raise RuntimeError('new did not empty the level')
    tb('linesDec')
    tb('linesDec')  # clamped at 0
    tb('linesInc')
    if p.evaluate("editor.level.lineK") != 1:
        raise RuntimeError('lineK not back at 1')
    step('new + lineK')
    r = p.evaluate("ball.radius")
    hmax = p.evaluate("EDITOR_PORTAL_H") + p.evaluate("EDITOR_PORTAL_H_STEP")
    lb = 2 * (hmax - 8 + r)  # fits h 45, not h 60
    line_b = ((150, 500), (150 + lb, 500))
    tb('line')
    for a, b in (EDITOR_TB_LINE_A, line_b):
        click(p, *a)
        click(p, *b)
    if p.evaluate("editor.level.lines.length") != 2:
        raise RuntimeError('line tool did not add two lines')
    tb('portal')
    click(p, 400, 290)
    click(p, 150 + lb / 2, 490)
    if p.evaluate("editor.level.portals.length") != 2:
        raise RuntimeError('portal tool did not place a pair')
    step('lines + portals')
    tb('select')
    click(p, *p.evaluate("(() => { const P = editorPortals()[0]; return [P.x, P.y] })()"))
    if not p.evaluate("!!editorSelectedPortal()"):
        raise RuntimeError('portal A not selected')
    tb('flagCCW')
    tb('portalSmaller')
    tb('portalBigger')
    tb('portalBigger')  # refused: portal does not fit on line B
    if p.evaluate("editor.level.portals[0].h") != hmax - p.evaluate("EDITOR_PORTAL_H_STEP"):
        raise RuntimeError('refused resize changed h')
    step('portal edits')
    click(p, 600, 300)
    if not p.evaluate("!!editorSelectedLine()"):
        raise RuntimeError('line A not selected')
    tb('flagCW')
    tb('delete', touch=True)
    if p.evaluate("editor.tool") != 'delete':
        raise RuntimeError('touch tap did not pick the delete tool')
    step('line rotate + delete tool (touch)')
    R = p.evaluate("editorBarRect()")
    gx, gy = R[0] + 3, R[1] + R[3] / 2  # left pad of the panel (no button)
    n = p.evaluate("ANALYTICS.debugLog.length")
    p.mouse.move(*to_client(p, gx, gy))
    p.mouse.down()
    p.mouse.move(*to_client(p, gx + 20, gy + 300), steps=5)
    p.mouse.up()
    frames(p)
    if p.evaluate("editorBarRect()")[1] == R[1]:
        raise RuntimeError('toolbar drag did not move the panel')
    toolbar_drag = p.evaluate("n => ANALYTICS.debugLog.slice(n).filter(e => e.fn == 'addDesignEvent').map(e => e.args[0])", n)
    step('toolbar drag')
    with p.expect_download() as dl:
        tb('export')
    files = {'ok': os.path.join(OUT_DIR, 'import_ok.json'), 'invalid': os.path.join(OUT_DIR, 'import_invalid.json'),
             'old_format': os.path.join(OUT_DIR, 'import_old_format.json')}
    dl.value.save_as(files['ok'])
    with open(files['invalid'], 'w') as f:
        f.write('this is not a level file')
    with open(files['old_format'], 'w') as f:
        json.dump({'version': 1, 'ballX': 200, 'ballY': 200, 'flagX': 1000, 'flagY': 600, 'flagRotate': 0, 'lineK': 1,
                   'lines': [[100, 300, 600, 300]], 'portals': [{'x': 300, 'y': 200, 'angle': 0}, {'x': 500, 'y': 200, 'angle': 0}]}, f)
    for kind in ('ok', 'invalid', 'old_format'):
        def pick(path=files[kind]):
            n = p.evaluate("ANALYTICS.debugLog.length")
            p.set_input_files('#editorImportFile', path)
            p.wait_for_function(EDITOR_IMPORT_WAIT_JS, arg=n, timeout=10000, polling=50)
        tb('import', after=pick)
    step('import x3')
    tb('exit')
    if p.evaluate("editorMode"):
        raise RuntimeError('exit did not close the editor (toolbar session)')
    step('exit toolbar')
    return toolbar_drag


# TASK-234: an editor session from the pause menu with every object event (mouse unless noted): new, line tool:
# cancel (2nd click on the pending point), lines C / D / E; portal tool: a click off the lines (error), A, B overlapping
# A (error), B; select tool: a press on line D that only selects (nothing sent), ball and flag drags, portal B moved
# (ok) and dropped on A (refused + error), line D moved, its end dragged by mouse, by touch (CDP touch events) and onto
# its other end (degenerate); line C's end dragged too close (refused + error); ⟳ on line E at the field edge (error);
# a seeded over-wide pair (h 400, unreachable from the UI: a line move keeps the length and the pair's u) for one
# refused line move; the delete tool on line D and on the pair; Delete key on the selected line E; exit.
EDITOR_OBJ = {'C': ((300, 250), (900, 250)), 'D': ((300, 450), (600, 450)), 'E': ((1240, 120), (1240, 680))}
EDITOR_EVENTS_SINCE_JS = """n => ANALYTICS.debugLog.slice(n).filter(e => e.fn == 'addDesignEvent' && String(e.args[0]).startsWith('editor:'))
    .map(e => [e.args[0], e.args[1] ?? null])"""


EDITOR_JS = os.path.join(ROOT, 'js', 'editor.js')
EDITOR_ERRORS_UNREACHABLE = {}  # message -> reason; every message is reachable from the UI today


def editor_error_messages():
    # every `grep -n editorShowError js/editor.js` call site with the message strings it can show: a literal argument,
    # or for a variable the string literals assigned to it in the enclosing function (ternaries over several lines) plus
    # the literals returned by editorLineEditError when the function calls it
    with open(EDITOR_JS) as f:
        src = f.read().split('\n')
    fn_start = [i for i, l in enumerate(src) if l.startswith('function ')]

    def body(i):
        a = max(x for x in fn_start if x <= i)
        b = min([x for x in fn_start if x > i] + [len(src)])
        return a, b

    def returns_of(name):
        i = next(k for k, l in enumerate(src) if l.startswith('function ' + name + '('))
        a, b = body(i)
        return [m for l in src[a:b] for m in re.findall(r"return '([^']+)'", l)]
    sites = []
    for i, l in enumerate(src):
        if 'editorShowError' not in l or l.startswith('function editorShowError'):
            continue
        m = re.search(r"editorShowError\('([^']+)'", l)
        if m:
            msgs = [m.group(1)]
        else:
            a, b = body(i)
            msgs = []
            # from the nearest `const|let ... err =` declaration before the call to the call (block-scoped err)
            a = max(k for k in range(a, i) if re.search(r'\b(const|let)\b.*\berr\s*=(?!=)', src[k]))
            for k in range(a, i):
                if re.search(r'\berr\s*=(?!=)', src[k]):
                    j = k
                    msgs += re.findall(r"'([^']+)'", src[j].split('err', 1)[1])
                    while src[j].rstrip().endswith((':', '?')):
                        j += 1
                        msgs += re.findall(r"'([^']+)'", src[j])
                    if 'editorLineEditError(' in src[k]:
                        msgs += returns_of('editorLineEditError')
        sites.append({'line': i + 1, 'text': l.strip(), 'messages': list(dict.fromkeys(msgs))})
    out = {}
    for st in sites:
        for msg in st['messages']:
            out.setdefault(msg, {'message': msg, 'callSites': []})['callSites'].append(st['line'])
    return list(out.values())


def editor_error_report(ids, slugs):
    import subprocess
    grep = subprocess.run(['grep', '-n', 'editorShowError', EDITOR_JS], capture_output=True, text=True).stdout.splitlines()
    rows = []
    for m in editor_error_messages():
        code = slugs[m['message']]
        n = sum(1 for i in ids if i.startswith('editor:error:') and i.split(':')[3] == code)
        rows.append(dict(m, slug=code, produced=n > 0, count=n, unreachable=EDITOR_ERRORS_UNREACHABLE.get(m['message'])))
    r = {'grep': grep, 'messages': rows,
         'notes': {'rotate line (editorRotateLine err)': 'its editorLineEditError messages cannot come from a rotation '
                   '(length and the pair u are kept); both messages are produced by drags (other call sites)'},
         'errorIdsInRun': sorted({i for i in ids if i.startswith('editor:error:')})}
    r['notProduced'] = [x['message'] for x in rows if not x['produced'] and not x['unreachable']]
    r['unknownCodes'] = sorted({i.split(':')[3] for i in r['errorIdsInRun']} - {x['slug'] for x in rows})
    r['pass'] = bool(rows and not r['notProduced'] and not r['unknownCodes'])
    return r


def drag(p, a, b, steps=6):
    p.mouse.move(*to_client(p, *a))
    p.mouse.down()
    p.mouse.move(*to_client(p, *b), steps=steps)
    p.mouse.up()
    frames(p)


def touch_drag(p, cdp, a, b, steps=6):
    # one finger: touchstart at a, touchmove in steps, touchend at b (Input.dispatchTouchEvent; real touch handlers)
    ax, ay = to_client(p, *a)
    bx, by = to_client(p, *b)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': ax, 'y': ay}]})
    for i in range(1, steps + 1):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [
            {'x': ax + (bx - ax) * i / steps, 'y': ay + (by - ay) * i / steps}]})
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    frames(p)


def objects_session(p, tb, step):
    open_menu(p)
    click(p, *p.evaluate(EDITOR_BUTTON_JS))
    if not p.evaluate("editorMode"):
        raise RuntimeError('menu editor button did not open the editor (objects session)')
    step('open menu objects')
    R = p.evaluate("editorBarRect()")
    pts = [q for ab in EDITOR_OBJ.values() for q in ab] + [(700, 200), (1100, 100)]
    if any(R[0] - 30 <= x <= R[0] + R[2] + 30 and R[1] - 30 <= y <= R[1] + R[3] + 30 for x, y in pts):
        raise RuntimeError('objects session point inside the toolbar %s' % R)
    out = {'events': {}}

    def act(name, fn):
        n = p.evaluate("ANALYTICS.debugLog.length")
        fn()
        ev = p.evaluate(EDITOR_EVENTS_SINCE_JS, n)
        out['events'][name] = ev
        return ev
    tb('new')
    tb('line')
    act('line cancel', lambda: (click(p, 700, 200), click(p, 700, 200)))
    for k in 'CDE':
        act('line add ' + k, lambda k=k: (click(p, *EDITOR_OBJ[k][0]), click(p, *EDITOR_OBJ[k][1])))
    if p.evaluate("editor.level.lines.length") != 3:
        raise RuntimeError('line tool did not add C, D, E')
    step('lines C D E')
    tb('portal')
    act('portal off lines', lambda: click(p, 1100, 100))
    act('portal a', lambda: click(p, 400, 240))
    act('portal b overlapping', lambda: click(p, 410, 240))
    act('portal b', lambda: click(p, 800, 240))
    if p.evaluate("editor.level.portals.length") != 2:
        raise RuntimeError('portal pair not placed')
    step('portals')
    tb('select')
    act('select only', lambda: (drag(p, (450, 450), (450, 450), steps=1), click(p, 450, 450)))
    if not p.evaluate("!!editorSelectedLine()"):
        raise RuntimeError('press on line D did not select it')
    act('ball', lambda: drag(p, (200, 200), (230, 170)))
    act('flag', lambda: drag(p, (1000, 600), (980, 650)))
    PB = lambda i: tuple(p.evaluate("i => { const P = editorPortals()[i]; return [P.x, P.y] }", i))
    act('portal move ok', lambda: drag(p, PB(1), (PB(1)[0] - 60, PB(1)[1])))
    act('portal move refused', lambda: drag(p, PB(1), PB(0)))
    act('line move ok', lambda: drag(p, (450, 450), (450, 500)))
    D2 = (600, 500)
    act('line end ok (mouse)', lambda: drag(p, D2, (650, 520)))
    cdp = p.context.new_cdp_session(p)
    tn = p.evaluate("() => { window.__tin = {touchstart: 0, touchmove: 0, touchend: 0, mousedown: 0};"
                    " for (const k of ['touchstart', 'touchmove', 'touchend', 'mousedown']) canvas.addEventListener(k, () => ++__tin[k], true) }")
    end_before = p.evaluate("[editor.level.lines[1].posX2, editor.level.lines[1].posY2]")
    act('line end ok (touch)', lambda: touch_drag(p, cdp, (650, 520), (620, 560)))
    end_after = p.evaluate("[editor.level.lines[1].posX2, editor.level.lines[1].posY2]")
    tin = p.evaluate("__tin")
    act('line end degenerate', lambda: drag(p, (620, 560), (300, 500)))
    act('line end refused', lambda: drag(p, EDITOR_OBJ['C'][1], (330, 250)))
    step('drags')
    act('line rotate off field', lambda: (click(p, 1240, 400), tb('flagCW')))
    # seeded state (not reachable from the UI): an over-wide pair on line C, so a real line move is refused
    hold = p.evaluate("() => { const h = editor.level.portals.map(P => P.h); editor.level.portals.forEach(P => P.h = 400); return h }")
    if p.evaluate("editorPickAt([350, 250])")[0] != 'line':
        raise RuntimeError('(350, 250) does not pick line C')
    act('line move refused (seeded h 400)', lambda: drag(p, (350, 250), (350, 300)))
    p.evaluate("h => editor.level.portals.forEach((P, i) => P.h = h[i])", hold)
    step('refused line move')
    tb('delete')
    dm = p.evaluate("(() => { const l = editor.level.lines[1]; return [(l.posX + l.posX2) / 2, (l.posY + l.posY2) / 2] })()")
    act('delete line D', lambda: click(p, *dm))
    # 10 px off the middle of portal A's opening, on the side away from line C: no line within 8 px, the opening within 12
    rim = p.evaluate("""(() => { const P = editorPortals()[0], r = portalRims(P), c = editor.level.lines[0]
        const mx = (r[0][0] + r[1][0]) / 2, my = (r[0][1] + r[1][1]) / 2
        const cand = [1, -1].map(s => [mx + s * 10 * Math.cos(P.angle), my + s * 10 * Math.sin(P.angle)])
        return cand.sort((a, b) => pointSegDist(b[0], b[1], c.posX, c.posY, c.posX2, c.posY2) -
                                   pointSegDist(a[0], a[1], c.posX, c.posY, c.posX2, c.posY2))[0] })()""")
    act('delete portals', lambda: click(p, *rim))
    if p.evaluate("editor.level.portals.length") != 0:
        raise RuntimeError('delete tool did not remove the pair')
    tb('select')
    click(p, 1240, 400)
    if not p.evaluate("!!editorSelectedLine()"):
        raise RuntimeError('line E not selected for the Delete key')
    act('delete key', lambda: (p.keyboard.press('Delete'), frames(p)))
    step('deletes')
    tb('exit')
    if p.evaluate("editorMode"):
        raise RuntimeError('exit did not close the editor (objects session)')
    step('exit objects')
    out['touch'] = {'events': out['events']['line end ok (touch)'], 'mouseEvents': out['events']['line end ok (mouse)'],
                    'endBefore': end_before, 'endAfter': end_after, 'inputs': tin}
    return out


# TASK-235: a play-test of a fresh level (edit:<h>:* events): editor from the menu, new, lines + x2 (lineK 3), line tool +
# one level line EDITOR_LINE, play
# (attempt 1), lines X and Y placed (line_place 1, 2), Y's end dragged (line_drag 1), Y deleted with the bin
# (line_delete), run (play box) + pause, speed on / off, HUD restart (attempt 2), run -> the ball falls off the map
# (offmap, attempt 3), run + the ball put on the flag (win), the completion window's 'editor' button (back), exit.
# isolation: the full log between 'play' and 'back' has no level: / lines: / ui: events and bp.stats.v1 (storage and
# TELEMETRY.stats()) is the same before and after.
PT_STATS_JS = """async () => ({stored: (await PLATFORM.storage.getMany([STATS_STORE]))[STATS_STORE] ?? null,
    mem: JSON.stringify(TELEMETRY.stats())})"""
PT_EVENTS_SINCE_JS = """n => ANALYTICS.debugLog.slice(n).filter(e => e.fn == 'addDesignEvent' && String(e.args[0]).startsWith('edit:'))
    .map(e => [e.args[0], e.args[1] ?? null])"""


def playtest_session(p, tb, step):
    open_menu(p)
    click(p, *p.evaluate(EDITOR_BUTTON_JS))
    if not p.evaluate("editorMode"):
        raise RuntimeError('menu editor button did not open the editor (play-test session)')
    step('open menu playtest')
    tb('new')
    tb('linesInc')
    tb('linesInc')
    R = p.evaluate("editorBarRect()")
    if any(R[0] - 30 <= x <= R[0] + R[2] + 30 and R[1] - 30 <= y <= R[1] + R[3] + 30 for x, y in EDITOR_LINE):
        raise RuntimeError('play-test session level line inside the toolbar %s' % R)
    tb('line')  # one level line (away from the ball's fall at x 200), so levels[thisLevel] keeps a line after exit
    click(p, *EDITOR_LINE[0])
    click(p, *EDITOR_LINE[1])
    if p.evaluate("editor.level.lineK") != 3 or p.evaluate("editor.level.lines.length") != 1:
        raise RuntimeError('lineK is not 3 (play-test session)')
    acts = {}
    stats0 = p.evaluate(PT_STATS_JS)
    n_play = p.evaluate("ANALYTICS.debugLog.length")

    def act(name, fn):
        n = p.evaluate("ANALYTICS.debugLog.length")
        fn()
        acts[name] = p.evaluate(PT_EVENTS_SINCE_JS, n)
    act('play', lambda: tb('play'))
    if p.evaluate("editorMode") or not p.evaluate("!!playtestLevel"):
        raise RuntimeError('play did not start a play-test (play-test session)')
    h = p.evaluate("TELEMETRY.levelHash(playtestLevel)")
    act('place X', lambda: draw_seg(p, LINE_X))
    act('place Y', lambda: draw_seg(p, LINE_Y))
    if p.evaluate("lines.filter(l => l.type == 'player').length") != 2 or p.evaluate("levelStarted"):
        raise RuntimeError('two player lines not placed (play-test session)')
    step('playtest 2 lines')

    def drag_y():
        end = p.evaluate("(() => { const l = lines.filter(l => l.type == 'player')[1]; return [l.posX2, l.posY2] })()")
        p.mouse.move(*to_client(p, *end))
        p.mouse.down()
        for k in range(1, 6):
            p.mouse.move(*to_client(p, end[0] + 6 * k, end[1] + 4 * k))
        p.mouse.up()
        frames(p)
        if p.evaluate("(() => { const l = lines.filter(l => l.type == 'player')[1]; return [l.posX2, l.posY2] })()") == end:
            raise RuntimeError('drag did not move line Y (play-test session)')
    act('drag Y', drag_y)

    def bin_y():
        mid = p.evaluate("(() => { const l = lines.filter(l => l.type == 'player')[1]; return [(l.posX + l.posX2) / 2, (l.posY + l.posY2) / 2] })()")
        click(p, *mid)
        if p.evaluate("playerSel") is None:
            raise RuntimeError('line Y not selected (play-test session)')
        click(p, *p.evaluate("binCenter(lines[playerSel])"))
        if p.evaluate("lines.filter(l => l.type == 'player').length") != 1:
            raise RuntimeError('bin did not delete line Y (play-test session)')
    act('delete Y', bin_y)
    step('playtest drag+delete')
    act('run+pause', lambda: (click(p, *p.evaluate(PLAY_ICON_JS)), click(p, *p.evaluate(PLAY_ICON_JS))))
    if p.evaluate("physics") or not p.evaluate("speedIconVisible()"):
        raise RuntimeError('run not paused / speed box hidden (play-test session)')
    act('speed on/off', lambda: (click(p, *box_centre(p, "speedIconRect()")), click(p, *box_centre(p, "speedIconRect()"))))
    act('restart', lambda: click(p, *box_centre(p, "restartIconRect()")))
    if p.evaluate("levelStarted"):
        raise RuntimeError('HUD restart did not reset the run (play-test session)')
    step('playtest restart')

    def offmap():
        telemetry_run(p)
        p.wait_for_function("!levelStarted", timeout=30000, polling=50)  # the ball left the map: automatic restart
    act('run+offmap', offmap)
    step('playtest offmap')

    def win():
        telemetry_run(p)
        p.evaluate("() => { const L = curLevel(); ball.posX = L.flagX + (flag[2][0] + flag[3][0]) / 2; ball.posY = L.flagY + (flag[2][1] + flag[3][1]) / 2; ball.speedX = ball.speedY = 0 }")
        p.wait_for_function("levelCompletedWindow", timeout=30000, polling=50)
    act('run+win', win)
    step('playtest win')
    stats_win = p.evaluate(PT_STATS_JS)
    act('back', lambda: click(p, *p.evaluate(WIN_NEXT_JS)))  # play-test: 'editor' in place of 'next level'
    if not p.evaluate("editorMode") or p.evaluate("!!playtestLevel"):
        raise RuntimeError('completion window editor button did not return to the editor (play-test session)')
    step('playtest back')
    window = p.evaluate("(a) => ANALYTICS.debugLog.slice(a).map(e => [e.fn, ...e.args.map(x => x === undefined ? null : x)])", n_play)
    stats1 = p.evaluate(PT_STATS_JS)
    tb('exit')
    if p.evaluate("editorMode"):
        raise RuntimeError('exit did not close the editor (play-test session)')
    step('exit playtest')
    design = [e for e in window if e[0] == 'addDesignEvent']
    count = {k: sum(1 for e in design if str(e[1]).startswith(k + ':')) for k in ('level', 'lines', 'ui', 'session', 'edit', 'editor')}
    iso = {'hash': h, 'window': 'ANALYTICS.debugLog from the play click to the back click (inclusive)', 'windowEvents': len(window),
           'counts': count, 'progression': sum(1 for e in window if e[0] == 'addProgressionEvent'),
           'statsBefore': stats0, 'statsAtWin': stats_win, 'statsAfter': stats1,
           'statsStoredIdentical': stats0['stored'] == stats_win['stored'] == stats1['stored'],
           'statsMemIdentical': stats0['mem'] == stats_win['mem'] == stats1['mem'], 'acts': acts, 'windowLog': window}
    iso['pass'] = bool(count['level'] == 0 and count['lines'] == 0 and count['ui'] == 0 and iso['progression'] == 0
                       and iso['statsStoredIdentical'] and iso['statsMemIdentical'] and count['edit'] > 0)
    return iso


def sc_telemetry_editor(page, info):
    with open(TELEMETRY_EDITOR_EXPECTED) as f:
        want = json.load(f)
    errors, steps = [], []
    buttons = {}  # TASK-233: toolbar button id -> editor: event ids its clicks produced
    with telemetry_page(page, errors, has_touch=True) as p:
        backend = p.evaluate("ANALYTICS_BACKEND.backendId")

        def step(name):
            steps.append({'step': name, 'editorMode': p.evaluate("editorMode"), 'playtest': p.evaluate("!!playtestLevel"),
                          'logLength': p.evaluate("ANALYTICS.debugLog.length")})
            if TELEMETRY_STEP_HOOK:
                TELEMETRY_STEP_HOOK(p, name)

        def tb(bid, touch=False, after=None):
            # one toolbar button click (or touch tap); after() runs before the events are collected (import: pick a file)
            n = p.evaluate("ANALYTICS.debugLog.length")
            if touch:
                p.touchscreen.tap(*to_client(p, *p.evaluate(EDITOR_BTN_CENTRE_JS, bid)))
                frames(p)
            else:
                editor_tool(p, bid)
            if after:
                after()
            new = p.evaluate("n => ANALYTICS.debugLog.slice(n).filter(e => e.fn == 'addDesignEvent' &&"
                             " String(e.args[0]).startsWith('editor:')).map(e => e.args[0])", n)
            buttons.setdefault(bid, []).extend(new)
            return new
        if p.evaluate("levels[thisLevel].srcId") != 1:
            raise RuntimeError('boot did not open srcId 1')
        step('boot')
        open_menu(p)
        click(p, *p.evaluate(EDITOR_BUTTON_JS))
        if not p.evaluate("editorMode"):
            raise RuntimeError('menu editor button did not open the editor')
        step('open menu')
        n0 = p.evaluate("editor.level.lines.length")
        tb('line')
        click(p, *EDITOR_LINE[0])
        click(p, *EDITOR_LINE[1])
        if p.evaluate("editor.level.lines.length") != n0 + 1:
            raise RuntimeError('line tool did not add a line')
        step('line')
        tb('play')
        if p.evaluate("editorMode") or not p.evaluate("!!playtestLevel"):
            raise RuntimeError('play did not start a play-test')
        frames(p, 10)
        step('playtest')
        click(p, *box_centre(p, "editIconRect()"))
        if not p.evaluate("editorMode") or p.evaluate("!!playtestLevel"):
            raise RuntimeError('edit box did not return to the editor')
        step('back')
        with p.expect_download() as dl:
            tb('export')
        exported = dl.value.suggested_filename
        step('export')
        level_json = p.evaluate("editorLevelToJSON(editor.level)")
        tb('exit')
        if p.evaluate("editorMode") or p.evaluate("levels[thisLevel].lines.length") != n0 + 1:
            raise RuntimeError('exit did not write the line back')
        step('exit')
        telemetry_run(p)
        p.evaluate("() => { const L = curLevel(); ball.posX = L.flagX + (flag[2][0] + flag[3][0]) / 2; ball.posY = L.flagY + (flag[2][1] + flag[3][1]) / 2; ball.speedX = ball.speedY = 0 }")
        p.wait_for_function("levelCompletedWindow", timeout=30000, polling=50)
        step('win')
        click(p, *p.evaluate(EDITOR_BUTTON_JS))
        if not p.evaluate("editorMode"):
            raise RuntimeError('win window editor button did not open the editor')
        step('open win')
        tb('exit')
        if p.evaluate("editorMode"):
            raise RuntimeError('exit did not close the editor')
        step('exit unchanged')
        toolbar_drag = toolbar_session(p, tb, step)
        objects = objects_session(p, tb, step)  # TASK-234
        iso = playtest_session(p, tb, step)  # TASK-235
        open_menu(p)
        click(p, *p.evaluate(EDITOR_BUTTON_JS))
        if not p.evaluate("editorMode"):
            raise RuntimeError('menu editor button did not open the editor (2)')
        step('open menu 2')
        p.evaluate("() => window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: false}))")
        step('pagehide')
        actual = p.evaluate(TELEMETRY_EDITOR_LOG_JS)
        full = p.evaluate(FULL_LOG_JS)
        bspec = p.evaluate("EDITOR_BUTTONS.map(b => ({id: b.id, kind: b.kind}))")
        page_slugs = p.evaluate("ms => Object.fromEntries(ms.map(m => [m, TELEMETRY.editorErrorCode(m)]))",
                                [m['message'] for m in editor_error_messages()])
        hv = p.evaluate("""() => {
            const A = editorCloneLevel(levels[thisLevel]), B = editorCloneLevel(levels[thisLevel])
            const C = editorCloneLevel(levels[thisLevel]); C.lines[0].posX += 1
            return {a: TELEMETRY.levelHash(A), b: TELEMETRY.levelHash(B), moved: TELEMETRY.levelHash(C),
                    jsonA: editorLevelToJSON(A), jsonMoved: editorLevelToJSON(C)} }""")
    TELEMETRY_LOGS['telemetry_editor'] = full
    hx = re.compile(r'^[0-9a-f]{8}$')
    hj = {'level': 'levels[thisLevel] (srcId 1 after the editor exit)', 'cloneA': hv['a'], 'cloneB': hv['b'],
          'oneLineMoved1px': hv['moved'], 'pythonFnvA': fnv1a(hv['jsonA']), 'pythonFnvMoved': fnv1a(hv['jsonMoved']),
          'exportedLevelHashPython': fnv1a(level_json)}
    hj['sameForClones'] = hv['a'] == hv['b']
    hj['differsAfterMove'] = hv['moved'] != hv['a']
    hj['hexForm'] = all(hx.match(v) is not None for v in (hv['a'], hv['b'], hv['moved']))
    hj['matchesPython'] = hj['pythonFnvA'] == hv['a'] and hj['pythonFnvMoved'] == hv['moved']
    hj['pass'] = bool(hj['sameForClones'] and hj['differsAfterMove'] and hj['hexForm'] and hj['matchesPython'])
    ids = [e[1] for e in actual]
    seq = {'backend': backend, 'steps': steps, 'expected': want['events'], 'debugLog': actual, 'download': exported,
           'consoleErrors': len(errors), 'errors': errors,
           'gaIdsOk': all(ga_design_id_ok(i) for i in ids), 'badIds': [i for i in ids if not ga_design_id_ok(i)],
           'summaryHashPython': fnv1a(level_json),
           'summaryHashInLog': sorted({i.split(':')[3] for i in ids if i.startswith('editor:sum:')}), 'fullLog': full}
    seq['matchExpected'] = telemetry_match(actual, want['events'])
    seq['coverage'] = telemetry_coverage({'telemetry_editor': full}, editor=True)
    seq['pass'] = bool(seq['matchExpected'] and seq['gaIdsOk'] and backend == TELEMETRY_BACKEND and not errors
                       and seq['coverage']['pass'])
    allcov = write_coverage()  # TASK-236: all three logs when levels + ui ran before in this run
    if allcov is not None:
        info['telemetryCoverage'] = {'scope': allcov['scope'], 'pass': allcov['pass'], 'uncovered': allcov['uncovered']}
    with open(os.path.join(OUT_DIR, 'sequence_editor.json'), 'w') as f:
        json.dump(seq, f, separators=(',', ':'))
    with open(os.path.join(OUT_DIR, 'hash.json'), 'w') as f:
        json.dump(hj, f, separators=(',', ':'))
    # TASK-233: every EDITOR_BUTTONS id of kind tool / toggle / action with the editor: events its clicks produced
    ids_kinds = [(b['id'], b['kind']) for b in bspec]
    bj = {'source': 'EDITOR_BUTTONS (js/editor.js), kinds tool/toggle/action', 'toolbarDrag': toolbar_drag,
          'buttons': [{'id': i, 'kind': k, 'events': buttons.get(i, [])} for i, k in ids_kinds if k != 'value']}
    bj['zeroEvents'] = [b['id'] for b in bj['buttons'] if not b['events']]
    bj['importOutcomes'] = sorted({e.split(':')[3] for e in buttons.get('import', []) if e.startswith('editor:import:')})
    bj['refusedResize'] = [e for e in actual if e[1].startswith('editor:portal_size:') and e[2] == 0]
    bj['lineKClampAt0'] = [e for e in actual if e[1].startswith('editor:linek:') and e[1].endswith(':dec') and e[2] == 0]
    bj['rotateTargets'] = sorted({e.split(':')[4] for e in ids if e.startswith('editor:rotate:')})
    bj['pass'] = bool(bj['buttons'] and not bj['zeroEvents'] and bj['importOutcomes'] == ['invalid', 'ok', 'old_format']
                      and bj['refusedResize'] and len(bj['lineKClampAt0']) >= 2 and bj['rotateTargets'] == ['flag', 'line', 'portal']
                      and any(e.startswith('editor:bar_move:') for e in toolbar_drag))
    with open(os.path.join(OUT_DIR, 'buttons.json'), 'w') as f:
        json.dump(bj, f, separators=(',', ':'))
    # TASK-234: object events per scripted act, the error messages of editorShowError vs the run, the touch drag
    oj = {'acts': objects['events'], 'eventIds': sorted({e[1] for e in actual})}
    with open(os.path.join(OUT_DIR, 'objects.json'), 'w') as f:
        json.dump(oj, f, separators=(',', ':'))
    ej = editor_error_report(ids, page_slugs)
    with open(os.path.join(OUT_DIR, 'errors.json'), 'w') as f:
        json.dump(ej, f, separators=(',', ':'))
    t = objects['touch']
    tj = dict(t)
    tj['lineEndEvents'] = [e for e in t['events'] if e[0].startswith('editor:line_end:')]
    tj['mouseLineEndEvents'] = [e for e in t['mouseEvents'] if e[0].startswith('editor:line_end:')]
    tj['endMoved'] = t['endBefore'] != t['endAfter']
    tj['pass'] = bool(len(tj['lineEndEvents']) == 1 and len(tj['mouseLineEndEvents']) == 1 and
                      tj['lineEndEvents'][0][0] == tj['mouseLineEndEvents'][0][0] and tj['endMoved'] and
                      t['inputs']['touchstart'] == 1 and t['inputs']['touchend'] == 1 and t['inputs']['mousedown'] == 0)
    with open(os.path.join(OUT_DIR, 'touch.json'), 'w') as f:
        json.dump(tj, f, separators=(',', ':'))
    # TASK-235: every edit: hash equals an editor:sum hash sent at 'play' (the editor:sum events right after btn:play)
    play_hashes = []
    for i, e in enumerate(actual):
        if e[1].startswith('editor:btn:') and e[1].endswith(':play') and i + 1 < len(actual) and actual[i + 1][1].startswith('editor:sum:'):
            play_hashes.append(actual[i + 1][1].split(':')[3])
    edit_ids = [e[1] for e in actual if e[1].startswith('edit:')]
    iso['editHashes'] = sorted({i.split(':')[1] for i in edit_ids})
    iso['playSumHashes'] = play_hashes
    iso['editHashEqualsPlaySum'] = bool(edit_ids and set(iso['editHashes']) <= set(play_hashes) and iso['hash'] in play_hashes)
    iso['pass'] = bool(iso['pass'] and iso['editHashEqualsPlaySum'])
    with open(os.path.join(OUT_DIR, 'isolation.json'), 'w') as f:
        json.dump(iso, f, separators=(',', ':'))
    if not iso['pass']:
        raise RuntimeError('play-test isolation / hash check failed (isolation.json)')
    if not ej['pass']:
        raise RuntimeError('editor errors: not produced %s (errors.json)' % ej['notProduced'])
    if not tj['pass']:
        raise RuntimeError('touch line_end drag check failed (touch.json)')
    info['telemetry'] = {'sequencePass': seq['pass'], 'hashPass': hj['pass'], 'buttonsPass': bj['pass'], 'events': len(actual)}
    if not seq['pass']:
        raise RuntimeError('telemetry editor sequence mismatch (sequence_editor.json)')
    if not bj['pass']:
        raise RuntimeError('toolbar button coverage failed (buttons.json)')
    if not hj['pass']:
        raise RuntimeError('levelHash check failed (hash.json)')
    if allcov is not None and not allcov['pass']:
        raise RuntimeError('telemetry coverage: uncovered %s (coverage.json)' % allcov['uncovered'])


SPEED_CONCEPT = os.path.join(ROOT, 'artifacts', 'concepts', 'speed', '14-arrow-centre-big3x-v2.png')


def speed_centre(out_dir, page_dpr):
    # centre.json: bright-pixel bbox of the double arrow in speed_off.png, inside the box (3 px stroke margin)
    # and outside the measured '3x' label box; centre vs the box centre in logical px
    from PIL import Image
    d = SPEED.get('speed_off')
    if not d:
        return
    r = d['state']['rect']
    lab = d.get('label')
    k = page_dpr
    im = Image.open(os.path.join(out_dir, 'speed_off.png')).convert('RGB')
    xs, ys = [], []
    for py in range(int((r[1] + 3) * k), int((r[1] + r[3] - 3) * k)):
        for px in range(int((r[0] + 3) * k), int((r[0] + r[2] - 3) * k)):
            lx, ly = px / k, py / k
            if lab and lab[0] - 2 <= lx <= lab[2] + 2 and lab[1] - 2 <= ly <= lab[3] + 2:
                continue
            if min(im.getpixel((px, py))) > 200:
                xs.append(px); ys.append(py)
    bbox = [min(xs) / k, min(ys) / k, (max(xs) + 1) / k, (max(ys) + 1) / k]
    c = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    box_c = [r[0] + r[2] / 2, r[1] + r[3] / 2]
    err = [abs(c[0] - box_c[0]), abs(c[1] - box_c[1])]
    out = {'dpr': k, 'rect': r, 'labelBox': lab, 'threshold': 'min(r,g,b)>200', 'nPixels': len(xs),
           'arrowBboxLogical': bbox, 'arrowCentre': c, 'boxCentre': box_c, 'errPx': err,
           'pass': bool(err[0] <= 1 and err[1] <= 1)}
    with open(os.path.join(out_dir, 'centre.json'), 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    return out


def speed_hud_compare(out_dir):
    # hud_compare.png: the real HUD row (2x crop 930..1270 x 10..96, scaled like the concept inset, k 1.45) in both
    # states on the left, the concept-14 inset block (both states) on the right
    from PIL import Image, ImageDraw
    try:
        off = Image.open(os.path.join(out_dir, 'speed_off.png')).convert('RGB')
        on = Image.open(os.path.join(out_dir, 'speed_on.png')).convert('RGB')
    except FileNotFoundError:
        return
    if not os.path.exists(SPEED_CONCEPT):  # gitignored artifacts/ absent (clean checkout): visual aid only
        print('hud_compare skipped: concept missing %s' % SPEED_CONCEPT)
        return
    con = Image.open(SPEED_CONCEPT).convert('RGB')
    k = off.width / 1280
    crop = lambda im, kk: im.crop((int(930 * kk), int(10 * kk), int(1270 * kk), int(96 * kk)))
    W, H = int(340 * 1.45 * 2), int(86 * 1.45 * 2)
    a, b = crop(off, k).resize((W, H)), crop(on, k).resize((W, H))
    ins = con.crop((755 * 2, 474 * 2, 1266 * 2, 790 * 2))
    hgt = max(2 * H + 120, ins.height + 60)
    out = Image.new('RGB', (W + ins.width + 60, hgt), (4, 14, 28))
    dr = ImageDraw.Draw(out)
    out.paste(a, (20, 40)); out.paste(b, (20, 80 + H))
    out.paste(ins, (W + 40, 40))
    dr.text((20, 10), 'game speed_off.png (1x)', fill=(200, 230, 255))
    dr.text((20, 50 + H), 'game speed_on.png (3x)', fill=(200, 230, 255))
    dr.text((W + 40, 10), 'concept 14-arrow-centre-big3x-v2.png inset (1x / 3x on)', fill=(200, 230, 255))
    out.save(os.path.join(out_dir, 'hud_compare.png'))

# TASK-238: first-30-seconds telemetry, load timing + session context (js/telemetry.js sendLoad, index.html boot marks).
# none backend, own context with clean storage, page.clock installed before navigation. The load:/ctx: ids of
# ANALYTICS.debugLog must equal tests/visual/telemetry_expected_first30.json 'events' in order; a reload in the same
# storage must give 'afterReload' (ctx:visitor:ret). Stage values: html <= dom <= boot <= platform <= storage <= fonts
# <= first_frame, all >= 0. Writes sequence_first30.json, visitor.json and throttle.json (informational: load:first_frame
# unthrottled vs. a CDP Slow 3G run; never fails the scenario).
TELEMETRY_FIRST30_EXPECTED = os.path.join(ROOT, 'tests', 'visual', 'telemetry_expected_first30.json')
TELEMETRY_FIRST30_LOG_JS = """() => ANALYTICS.debugLog.filter(e => e.fn == 'addDesignEvent' && /^(load|ctx):/.test(String(e.args[0])))
    .map(e => [e.args[0], e.args[1] ?? null])"""
FIRST30_ORDER = ['html', 'dom', 'boot', 'platform', 'storage', 'fonts', 'first_frame']
# DevTools 'Slow 3G' preset (latency 400 ms x 5, 500 kbit/s x 0.8 down, 500 kbit/s x 0.8 up)
SLOW_3G = {'offline': False, 'latency': 2000, 'downloadThroughput': 500 * 1024 / 8 * 0.8,
           'uploadThroughput': 500 * 1024 / 8 * 0.8}


def first30_values(log):
    vals = {e[0][len('load:'):]: e[1] for e in log if e[0].startswith('load:')}
    seq = [vals.get(k) for k in FIRST30_ORDER]
    ok = all(isinstance(v, (int, float)) and v >= 0 for v in seq) and all(a <= b for a, b in zip(seq, seq[1:]))
    return vals, ok


def sc_telemetry_first30(page, info):
    with open(TELEMETRY_FIRST30_EXPECTED) as f:
        want = json.load(f)
    errors = []
    t_start = time.time()
    with telemetry_page(page, errors, init=lambda p: p.clock.install()) as p:
        backend = p.evaluate("ANALYTICS_BACKEND.backendId")
        frames(p, 3)
        actual = p.evaluate(TELEMETRY_FIRST30_LOG_JS)
        first = {'visitor': p.evaluate("TELEMETRY.firstVisitor()"),
                 'stored': p.evaluate("async () => (await PLATFORM.storage.getMany([FIRST_STORE]))[FIRST_STORE]")}
        reload_page(p)
        frames(p, 3)
        after = p.evaluate(TELEMETRY_FIRST30_LOG_JS)
        second = {'visitor': p.evaluate("TELEMETRY.firstVisitor()"),
                  'stored': p.evaluate("async () => (await PLATFORM.storage.getMany([FIRST_STORE]))[FIRST_STORE]")}
        full = p.evaluate(FULL_LOG_JS)
    TELEMETRY_LOGS['telemetry_first30'] = full
    ids, ids_after = [e[0] for e in actual], [e[0] for e in after]
    vals, order_ok = first30_values(actual)
    vals_after, order_ok_after = first30_values(after)
    seq = {'backend': backend, 'clock': 'page.clock.install() before navigation', 'expected': want['events'],
           'ids': ids, 'debugLog': actual, 'matchExpected': ids == want['events'],
           'expectedAfterReload': want['afterReload'], 'idsAfterReload': ids_after, 'debugLogAfterReload': after,
           'matchAfterReload': ids_after == want['afterReload'], 'order': FIRST30_ORDER,
           'values': {k: vals.get(k) for k in FIRST30_ORDER}, 'orderOk': order_ok,
           'valuesAfterReload': {k: vals_after.get(k) for k in FIRST30_ORDER}, 'orderOkAfterReload': order_ok_after,
           'consoleErrors': len(errors), 'errors': errors}
    seq['pass'] = bool(seq['matchExpected'] and seq['matchAfterReload'] and order_ok and order_ok_after
                       and backend == 'none' and not errors)
    # the new code reads / writes bp.first.v1 only through PLATFORM.storage: no localStorage in js/telemetry.js,
    # nor on the index.html lines that mention FIRST_STORE / loadMark / firstFrame
    src = open(os.path.join(ROOT, 'js', 'telemetry.js')).read()
    html_lines = [l for l in open(os.path.join(ROOT, 'index.html')).read().splitlines()
                  if re.search(r'FIRST_STORE|loadMark|firstFrame', l)]
    vis = {'key': 'bp.first.v1', 'first': {**first, 'ctx': [i for i in ids if i.startswith('ctx:visitor:')]},
           'reload': {**second, 'ctx': [i for i in ids_after if i.startswith('ctx:visitor:')]},
           'localStorageInTelemetryJs': src.count('localStorage'),
           'indexHtmlNewLines': html_lines, 'localStorageInIndexHtmlNewLines': sum('localStorage' in l for l in html_lines),
           'storageCalls': re.findall(r'PLATFORM\.storage\.\w+\(\{ \[FIRST_STORE\]', src)}
    vis['pass'] = bool(vis['first']['ctx'] == ['ctx:visitor:new'] and vis['first']['visitor'] == 'new'
                       and vis['reload']['ctx'] == ['ctx:visitor:ret'] and vis['reload']['visitor'] == 'ret'
                       and first['stored'] and second['stored'] == first['stored']
                       and vis['localStorageInTelemetryJs'] == 0 and vis['localStorageInIndexHtmlNewLines'] == 0
                       and vis['storageCalls'])
    seq['seconds'] = round(time.time() - t_start, 1)
    # informational: the same first load under CDP Slow 3G (own clean context)
    thr = {'preset': 'Slow 3G (DevTools)', 'conditions': SLOW_3G, 'unthrottled': {k: vals.get(k) for k in FIRST30_ORDER}}
    terr = []
    try:
        t1 = time.time()

        def slow(p):
            p.clock.install()
            cdp = p.context.new_cdp_session(p)
            cdp.send('Network.enable')
            cdp.send('Network.emulateNetworkConditions', SLOW_3G)
        with telemetry_page(page, terr, init=slow, boot_timeout=300000) as p:
            frames(p, 3)
            tl = p.evaluate(TELEMETRY_FIRST30_LOG_JS)
        tv, tok = first30_values(tl)
        thr.update({'throttled': {k: tv.get(k) for k in FIRST30_ORDER}, 'throttledAll': dict(tl),
                    'throttledOrderOk': tok, 'wallSeconds': round(time.time() - t1, 1), 'errors': terr})
        uf, tf = vals.get('first_frame'), tv.get('first_frame')
        thr['firstFrameMs'] = {'unthrottled': uf, 'throttled': tf}
        thr['slowdown'] = round(tf / uf, 1) if uf and tf else None
    except Exception as e:
        thr['error'] = '%s: %s' % (type(e).__name__, str(e).splitlines()[0] if str(e) else '')
    for name, d in (('sequence_first30.json', seq), ('visitor.json', vis), ('throttle.json', thr)):
        with open(os.path.join(OUT_DIR, name), 'w') as f:
            json.dump(d, f, separators=(',', ':'))
    info['telemetry'] = {'sequencePass': seq['pass'], 'visitorPass': vis['pass'], 'events': len(actual),
                         'throttledFirstFrame': thr.get('firstFrameMs')}
    if not seq['pass']:
        raise RuntimeError('first30 load/ctx sequence mismatch (sequence_first30.json)')
    if not vis['pass']:
        raise RuntimeError('first30 visitor check failed (visitor.json)')


SCENARIOS = {
    'start': sc_start,
    'level3_open': sc_level3,  # level 3 opened, no lines (was 'level3' before TASK-202)
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
    'level1': sc_level1,
    'level2': sc_level2,
    'level3': sc_level3_win,  # TASK-202: the srcId 3 reference win, like every other levelNN
    'level4': sc_level4,
    'level5': sc_level5,
    'level6': sc_level6,
    'level7': sc_level7,
    'level8': sc_level8,
    'level9': sc_level9,
    'level10': sc_level10,
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
    'lines_draft_restore': sc_lines_draft_restore,
    'lines_reload': sc_lines_reload,
    'lines_passed_restore': sc_lines_passed_restore,
    'lines_restart_keeps': sc_lines_restart_keeps,
    'lines_sha_mismatch': sc_lines_sha_mismatch,
    'lines_storage_blocked': sc_lines_storage_blocked,
    'lines_backends': sc_lines_backends,
    'speed_off': sc_speed_off,
    'speed_on': sc_speed_on,
    'speed_toggle': sc_speed_toggle,
    'speed_hidden': sc_speed_hidden,
    'speed_reload': sc_speed_reload,
    'telemetry_levels': sc_telemetry_levels,
    'telemetry_ui': sc_telemetry_ui,
    'telemetry_editor': sc_telemetry_editor,
    'telemetry_first30': sc_telemetry_first30,
}

# Extra browser.new_page() options per scenario (the viewport stays the default/--viewport one).
PAGE_OPTIONS = {
    'touch_line': {'has_touch': True},
    'map_touch': {'has_touch': True},
    'speed_toggle': {'has_touch': True},
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
    if name.startswith('lines_'):  # TASK-185: one record per scenario + the page's final console error count
        d = info.get('lines')
        if d is None:
            d = LINES[name] = {'pass': False}
            errors.append('lines scenario wrote no data: %s' % name)
        d['consoleErrors'] = len(errors)
        d['errors'] = list(errors)
        d['pass'] = bool(d['pass'] and not errors)
        with open(os.path.join(out_dir, 'lines.json'), 'w') as f:
            json.dump(LINES, f, separators=(',', ':'))
        if not d['pass']:
            errors.append('lines check failed: %s' % name)
    if name.startswith('speed_'):  # TASK-187: one record per scenario + the page's final console error count
        d = info.get('speed')
        if d is None:
            d = SPEED[name] = {'pass': False}
            errors.append('speed scenario wrote no data: %s' % name)
        d['consoleErrors'] = len(errors)
        d['errors'] = list(errors)
        d['pass'] = bool(d['pass'] and not errors)
        with open(os.path.join(out_dir, 'speed.json'), 'w') as f:
            json.dump(SPEED, f, separators=(',', ':'))
        if not d['pass']:
            errors.append('speed check failed: %s' % name)
        try:
            if name == 'speed_off' and d['pass']:
                c = speed_centre(out_dir, dpr)
                if not (c and c['pass']):
                    errors.append('centre check failed: %s' % c)
            if name in ('speed_off', 'speed_on'):
                speed_hud_compare(out_dir)
        except Exception as e:
            errors.append('speed evidence: %s: %s' % (type(e).__name__, e))
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
