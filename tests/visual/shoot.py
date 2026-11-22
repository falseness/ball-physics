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
    # Centre of level square 2 (i = 1), from levelRectXY() like levelsRectCollision().
    x, y = page.evaluate("() => { const r = levelRectXY(1); return [r[0] + rectSize / 2, r[1] + rectSize / 2] }")
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

# Level 15 (index 14) solution (layout from artifacts/new_level15.json, TASK-113): one long line under the ball
# rising to the right and crossing the wall x=633. The ball lands on it, rolls down-left into portal B (the floor pad
# facing up), comes out of A on the wall's right face and reaches the flag (won on physics frame 175, one B->A
# teleport). Found by a lattice + random search with in-page stepped frames (artifacts/TASK-114/search.log); all 8
# single-coordinate and all 8 whole-line +-2 px variants also win. Keep these exact integer coordinates.
LEVEL15_LINE = ((207, 547), (1024, 437))
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

# Level 18 (index 17, lineK 2) solution: a ramp starting just under the ball and sloping down to the right into portal A
# (left face of the full-height wall x=640); B (right face of the pit wall x=1000) fires the ball down-right, away from
# the pit, onto a shallow second line right of the pit wall that bounces it back up-left over the wall x=1000 onto the
# flag (won on physics frame 150, one A->B teleport). Found with tools/level_search.py: a seed grid of second lines
# along the B exit path (--mode sample --around, +-6 px variants; artifacts/TASK-129/search_ref.json), then --mode local
# (+-2 px): 14 of the 16 single-coordinate variants also win (artifacts/TASK-129/local_ref.json).
# Keep these exact integer coordinates.
LEVEL18_LINES = [((130, 77), (630, 568)), ((1020, 768), (1189, 700))]
LEVEL18_MAX_FRAMES = 1500

# Level 19 (index 18, lineK 2) solution: a short ramp from under the ball down onto the right floor y=300 (the ball rolls
# off the floor's left end and drops under the middle shelf), and a "/" kicker below the shelf that bounces the ball up
# into portal A (the shelf's underside, facing down); B (left wall x=40, facing right) fires it up and over onto the flag
# shelf (won on physics frame 157, one A->B teleport). Found with tools/level_search.py's evaluate() (exploration wrapper
# artifacts/TASK-131/search/grid.py): the ramp fixed, every second line with both ends on a 30 px lattice under the
# shelf (x 250..700, y 480..800; artifacts/TASK-131/search_ref.json), then --mode local (+-2 px): all 16
# single-coordinate variants also win (artifacts/TASK-131/local_ref.json).
# Keep these exact integer coordinates.
LEVEL19_LINES = [((960, 270), (800, 296)), ((400, 690), (610, 660))]
LEVEL19_MAX_FRAMES = 1500

# Level 20 (index 19, lineK 3) solution: a short ramp from beside the ball onto the divider y=420 (the ball rolls off it
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

# Level 21 (index 20, lineK 2) solution: a shallow ramp from just under the resting ball down-left off its pad (the ball
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

# Level 22 (index 21, lineK 3) solution: a shallow ramp from just left of the resting ball rolls it off its pad; it
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

# Level 23 (index 22, lineK 2) solution: the ball rolls off its start slope; line 1 is a kicker under the slope's end
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

# Level 24 (index 23, lineK 3) solution: line 1 is a long, almost flat line over the start pad that rolls the ball
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

# Level 25 ('skim, don't drop', levels[24], lineK 2): line 1, an almost flat kicker in the well under the start slope,
# throws the falling ball up and over the crest wall (x = 840, top y = 450) into A's pocket; line 2, a ~42 deg
# converter slope in the pocket, turns its steep (~75 deg) fall into a flat skim (0.041, 0.010 px/cycle) into floor
# portal A, so B on the right-edge wall lets it out going straight up the chimney to the flag (won on physics frame
# 153, one teleport A->B). Found with a hand-aimed scan (3 kickers x 60 converters at 38..50 deg around the kicker's
# landing point; artifacts/TASK-145/search/cv21.json re-evaluated with tools/level_search.py's evaluate() on the
# committed levels[24]: 19 of 180 win, artifacts/TASK-145/search_ref.json); 13 of the 17 local +-2 px variants win.
# Keep these exact integer coordinates.
LEVEL25_LINES = [((535, 597), (635, 603)), ((920, 693), (980, 747))]
LEVEL25_MAX_FRAMES = 1500

# Level 26 ('one line, two jobs', levels[25], lineK 4): line 1 tips the ball off its pad to the left; line 2, a long
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


def sc_level18(page, info):
    play_solution(page, info, 17, LEVEL18_LINES, LEVEL18_MAX_FRAMES, 'level18')


def sc_level19(page, info):
    play_solution(page, info, 18, LEVEL19_LINES, LEVEL19_MAX_FRAMES, 'level19')


def sc_level20(page, info):
    play_solution(page, info, 19, LEVEL20_LINES, LEVEL20_MAX_FRAMES, 'level20')


def sc_level21(page, info):
    play_solution(page, info, 20, LEVEL21_LINES, LEVEL21_MAX_FRAMES, 'level21')


def sc_level22(page, info):
    play_solution(page, info, 21, LEVEL22_LINES, LEVEL22_MAX_FRAMES, 'level22')


def sc_level23(page, info):
    play_solution(page, info, 22, LEVEL23_LINES, LEVEL23_MAX_FRAMES, 'level23')


def sc_level24(page, info):
    play_solution(page, info, 23, LEVEL24_LINES, LEVEL24_MAX_FRAMES, 'level24')


def sc_level25(page, info):
    play_solution(page, info, 24, LEVEL25_LINES, LEVEL25_MAX_FRAMES, 'level25')


def sc_level26(page, info):
    play_solution(page, info, 25, LEVEL26_LINES, LEVEL26_MAX_FRAMES, 'level26')


def sc_level27(page, info):
    play_solution(page, info, 26, LEVEL27_LINES, LEVEL27_MAX_FRAMES, 'level27')


def sc_level28(page, info):
    play_solution(page, info, 27, LEVEL28_LINES, LEVEL28_MAX_FRAMES, 'level28')


def sc_level29(page, info):
    play_solution(page, info, 28, LEVEL29_LINES, LEVEL29_MAX_FRAMES, 'level29')


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
            if 'play' in entry:  # play_solution scenarios: win frame and teleports of the real-input run
                pl = entry['play']
                print('    play levelCompleted=%s winFrame=%s frames=%s teleports=%s' % (
                    pl['levelCompleted'], pl['winFrame'], pl['frames'],
                    ','.join(t['from'] + '->' + t['to'] for t in pl['teleports']) or '-'))
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
