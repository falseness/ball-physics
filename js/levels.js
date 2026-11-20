let levels = []

levels.push(
{
    // Same start as before (512, 125): levels.js used to run while the canvas still had its
    // 1024x750 HTML size, so half the width and half the height minus 250 gave these values.
    ballX: GAME_W * 0.4,
    ballY: GAME_H / 2 - 275,
    flagX: 200,
    flagY: 450,
    flagRotate: 0,
    lineK: 1,
    lines: [
        new Line(100, 450, 300, 450, dotRadius, levelLineColor, 'line'), 
        new Line(100, 450, 100, 200, dotRadius, levelLineColor, 'line')],
    unlock: 1
}, 
{
    
    ballX: 100,
    ballY: 15,
    flagX: 360,
    flagY: 400,
    flagRotate: 0,
    lineK: 1,
    lines: [
        new Line(0, 50, 200, 250, dotRadius, levelLineColor, 'line'),
        new Line(235, 235, 420, 50, dotRadius, levelLineColor, 'line'),
        new Line(450, 400, 280, 400, dotRadius, levelLineColor, 'line')
    ],
    unlock: 0
},
{
    ballX: 200,
    ballY: 150,
    flagX: 390,
    flagY: 340,
    flagRotate: -0.96667 + Math.PI * 1.5,
    lineK: 2,
    lines: [
        new Line(100, 400, 300, 400, dotRadius, levelLineColor, 'line'),
        new Line(300, 400, 450, 300, dotRadius, levelLineColor, 'line')],
    unlock: 0
},
{
    ballX: 200,
    ballY: 50,
    flagX: 300,
    flagY: 281,
    flagRotate: Math.PI,
    lineK: 2,
    lines: [
        new Line(250, 0, 250, 60, dotRadius, levelLineColor, 'line'),
        new Line(250, 60, 170, 70, dotRadius, levelLineColor, 'line'),
        new Line(0, 280, 450, 280, dotRadius, levelLineColor, 'line')
    ],
    unlock: 0
},
{
    ballX: 645,
    ballY: 50,
    flagX: 430,
    flagY: 100,
    flagRotate: Math.PI / 2,
    lineK: 1,
    lines: [
        new Line(240, 370, 80, 250, dotRadius, levelLineColor, 'line'),
        new Line(430, 250, 430, 10, dotRadius, levelLineColor, 'line'),
        new Line(430, 310, 430, 600, dotRadius, levelLineColor, 'line')
    ],
    unlock: 0
},
{
    ballX: 200,
    ballY: 50,
    flagX: 360,
    flagY: 400,
    flagRotate: 0,
    lineK: 3,
    lines: [
        new Line(0, 280, 450, 280, dotRadius, levelLineColor, 'line'),
        new Line(450, 280, 450, 400, dotRadius, levelLineColor, 'line'),
        new Line(450, 400, 280, 400, dotRadius, levelLineColor, 'line')
    ],
    unlock: 0
},
{
    ballX: 645,
    ballY: 100,
    flagX: 190,
    flagY: 260,
    flagRotate: 0,
    lineK: 1,
    lines: [
        new Line(250, 0, 420, 200, dotRadius, levelLineColor, 'line'),
        new Line(630, 200, 630, 50, dotRadius, levelLineColor, 'line'),
        new Line(280, 280, 310, 280, dotRadius, levelLineColor, 'line'),
        new Line(170, 260, 200, 260, dotRadius, levelLineColor, 'line')
    ],
    unlock: 0
},
{
    ballX: 350,
    ballY: 15,
    flagX: 240,
    flagY: 100,
    flagRotate: Math.PI,
    lineK: 1,
    lines: [
        new Line(100, 100, 100, 400, dotRadius, levelLineColor, 'line'),
        new Line(100, 400, 300, 400, dotRadius, levelLineColor, 'line'),
        new Line(300, 360, 300, 100, dotRadius, levelLineColor, 'line'),
        new Line(100, 100, 300, 100, dotRadius, levelLineColor, 'line')
    ],
    unlock: 0
},
{
    ballX: 40,
    ballY: 15,
    flagX: 370,
    flagY: 600,
    flagRotate: 0,
    lineK: 1,
    lines: [
        new Line(350, 260, 0, 0, dotRadius, levelLineColor, 'line'),
        new Line(380, 180, 380, 300, dotRadius, levelLineColor, 'line'),
        new Line(380, 300, 630, 450, dotRadius, levelLineColor, 'line'),
        new Line(800, 700, 1000, 500, dotRadius, levelLineColor, 'line'),
        new Line(340, 600, 390, 600, dotRadius, levelLineColor, 'line'),
        new Line(380, 300, 340, 600, dotRadius, levelLineColor, 'line'),
        new Line(630, 520, 630, 250, dotRadius, levelLineColor, 'line'),
        new Line(630, 650, 630, 550, dotRadius, levelLineColor, 'line')
    ],
    unlock: 0
},
{
    ballX: 40,
    ballY: 15,
    flagX: 240,
    flagY: 150,
    flagRotate: 0,
    lineK: 2,
    lines: [
        new Line(100, 10, 100, 300, dotRadius, levelLineColor, 'line'),
        new Line(100, 300, 300, 300, dotRadius, levelLineColor, 'line'),
        new Line(300, 200, 200, 200, dotRadius, levelLineColor, 'line'),
        new Line(200, 200, 200, 150, dotRadius, levelLineColor, 'line'),
        new Line(200, 150, 300, 150, dotRadius, levelLineColor, 'line'),
        new Line(300, 200, 300, 10, dotRadius, levelLineColor, 'line')
    ],
    unlock: 0
},
{
    // Level 11, the first portal level: the flag sits in a walled pocket on the right that the
    // ball can only enter through portal B. Steer the ball into portal A, cut into the floor
    // segment at y = 600 (front facing up); B is cut into the pocket's left wall x = 1040
    // (front facing into the pocket, +x).
    // Reference solution (tests/visual/shoot.py level11): one line (100, 180) -> (580, 450), then start;
    // the ball rolls off its end into A, leaves B into the pocket and hits the flag.
    ballX: 200,
    ballY: 100,
    flagX: 1200,
    flagY: 450,
    flagRotate: 0,
    lineK: 2,
    lines: [
        new Line(1040, 0, 1040, 450, dotRadius, levelLineColor, 'line'),
        new Line(1040, 450, 1270, 450, dotRadius, levelLineColor, 'line'),
        new Line(1270, 450, 1270, 0, dotRadius, levelLineColor, 'line'),
        new Line(450, 600, 750, 600, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (600, 600) facing up,
    // B at (1040, 250) facing +x
    portals: [
        { line: 3, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 0, u: 250 / 450, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 12, 'understanding portals' (the user's editor export, squared): the ball drops onto
    // portal B (pad y = 510, front facing up) right under it and comes out of portal A (pad
    // y = 310, front facing up) moving up. The flag hangs under the ceiling in the top-left corner.
    // Pad A was at y = 695 in the export; TASK-073 raised it to 310 so the B -> A exit can reach the
    // flag (a teleport keeps the speed, so the ball rises only ~155 px above A; one deflector line wins).
    ballX: 195,
    ballY: 355,
    flagX: 47,
    flagY: 161,
    flagRotate: -Math.PI / 2,
    lineK: 1,
    lines: [
        new Line(43, 112, 453, 112, dotRadius, levelLineColor, 'line'),
        new Line(43, 112, 43, 209, dotRadius, levelLineColor, 'line'),
        new Line(289, 310, 449, 310, dotRadius, levelLineColor, 'line'),
        new Line(86, 510, 246, 510, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (369, 310) facing up (0, -1),
    // B at (166, 510) facing up (0, -1)
    portals: [
        { line: 2, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 3, u: 0.5, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 13, 'accelerator': a closed box with a shelf in the middle. Portal A is cut into the
    // floor (front facing up), portal B into the shelf's underside (front facing down), so a ball
    // falling into A drops out of B above it and gains speed on every loop.
    ballX: 430,
    ballY: 655,
    flagX: 362,
    flagY: 112,
    flagRotate: -Math.PI / 2,
    lineK: 4,
    lines: [
        new Line(360, 755, 1240, 755, dotRadius, levelLineColor, 'line'),
        new Line(1240, 755, 1240, 70, dotRadius, levelLineColor, 'line'),
        new Line(360, 755, 360, 70, dotRadius, levelLineColor, 'line'),
        new Line(360, 70, 1240, 70, dotRadius, levelLineColor, 'line'),
        new Line(694, 377, 894, 377, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (790, 755) facing up (0, -1),
    // B at (794, 377) on the shelf's underside facing down (0, 1)
    portals: [
        { line: 0, u: (790 - 360) / 880, side: -1, h: 45, name: 'A' },
        { line: 4, u: 0.5, side: 1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 14, 'horizontal acceleration' (the user's editor export, squared): the same ceiling and
    // short wall as level 12, and two big portals (h 90, twice the default) each cut into its own
    // vertical wall facing the other one: B on the left facing right, A on the right facing left.
    // The flag hangs upside down on the right.
    ballX: 197,
    ballY: 436,
    flagX: 1081,
    flagY: 192,
    flagRotate: -Math.PI,
    lineK: 1,
    lines: [
        new Line(43, 112, 453, 112, dotRadius, levelLineColor, 'line'),
        new Line(43, 112, 43, 209, dotRadius, levelLineColor, 'line'),
        new Line(121, 270, 121, 510, dotRadius, levelLineColor, 'line'),
        new Line(845, 422, 845, 662, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (845, 542) facing left (-1, 0),
    // B at (121, 390) facing right (1, 0)
    portals: [
        { line: 3, u: 0.5, side: 1, h: 90, name: 'A' },
        { line: 2, u: 0.5, side: -1, h: 90, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 15 (source: artifacts/new_level15.json, the user's editor export, numbers kept verbatim):
    // a tall wall with portal A on its right face, a corner around the flag next to the wall top, and
    // portal B on a floor pad at the bottom left, facing up.
    ballX: 499.690965229397,
    ballY: 197.81974248927037,
    flagX: 637.5743052452814,
    flagY: 168.90987124463518,
    flagRotate: 4.71238898038469,
    lineK: 1,
    lines: [
        new Line(633, 90, 633, 791, dotRadius, levelLineColor, 'line'),
        new Line(1239, 623.0504101869152, 1239, 30, dotRadius, levelLineColor, 'line'),
        new Line(1239, 30, 999, 30, dotRadius, levelLineColor, 'line'),
        new Line(60.01501619660557, 667.9957087306927, 225.98710429701066, 667.9957087306927, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A on the wall at x 633 facing right (1, 0),
    // B on the floor pad facing up (0, -1)
    portals: [
        { line: 0, u: 0.30527817403708984, side: -1, h: 45, name: 'A' },
        { line: 3, u: 0.4761173752350055, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 16 (the user's editor export 'level (2)', squared; both free-standing portals got their own
    // 160 px pads): portal A on a floor pad facing up, portal B on a short wall at the bottom left
    // facing right, a ledge under the flag and a sloped ramp on the right.
    ballX: 291,
    ballY: 255,
    flagX: 1035,
    flagY: 114,
    flagRotate: Math.PI,
    lineK: 1,
    lines: [
        new Line(43, 750, 165, 750, dotRadius, levelLineColor, 'line'),
        new Line(312, 244, 312, 475, dotRadius, levelLineColor, 'line'),
        new Line(920, 110, 1137, 110, dotRadius, levelLineColor, 'line'),
        new Line(1233, 670, 829, 778, dotRadius, levelLineColor, 'line'),
        new Line(437, 469, 597, 469, dotRadius, levelLineColor, 'line'),
        new Line(64, 590, 64, 750, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (517, 469) on the pad facing up (0, -1),
    // B at (64, 689) facing right (1, 0)
    portals: [
        { line: 4, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 5, u: (689 - 590) / 160, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 17 (the user's editor export 'level (3)', squared; portal A snapped onto its wall, the
    // free-standing B portal got its own 160 px pad): the flag sits in a pocket on the right, behind
    // the wall that carries portal A on its left face; B is on a floor pad at the left.
    ballX: 519,
    ballY: 317,
    flagX: 1239,
    flagY: 645,
    flagRotate: Math.PI / 2,
    lineK: 1,
    lines: [
        new Line(308, 253, 308, 475, dotRadius, levelLineColor, 'line'),
        new Line(1091, 749, 1091, 245, dotRadius, levelLineColor, 'line'),
        new Line(1242, 34, 1242, 748, dotRadius, levelLineColor, 'line'),
        new Line(1091, 697, 1242, 697, dotRadius, levelLineColor, 'line'),
        new Line(1242, 34, 996, 34, dotRadius, levelLineColor, 'line'),
        new Line(38, 342, 198, 342, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (1091, 561) facing left (-1, 0),
    // B at (118, 342) on the pad facing up (0, -1)
    portals: [
        { line: 1, u: (749 - 561) / 504, side: -1, h: 45, name: 'A' },
        { line: 5, u: 0.5, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 18, 'send it back' (TASK-129, lineK 2): a full-height wall x = 640 (y 0 to 800) shuts the ball's chamber off
    // from the flag pit (floor y = 700 between x 640 and 1000). Portal A is cut into the wall's left face
    // (facing left), portal B into the right face of the short pit wall x = 1000 (facing right), so B fires
    // the ball AWAY from the pit. One line feeds A, a second, steep line on the right must turn the exit
    // stream back up and over the pit wall onto the flag (the two lines need opposite slopes).
    ballX: 220,
    ballY: 140,
    flagX: 820,
    flagY: 700,
    flagRotate: 0,
    lineK: 2,
    lines: [
        new Line(640, 0, 640, 800, dotRadius, levelLineColor, 'line'),
        new Line(640, 700, 1000, 700, dotRadius, levelLineColor, 'line'),
        new Line(1000, 450, 1000, 700, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (640, 560) facing left (-1, 0),
    // B at (1000, 620) facing right (1, 0)
    portals: [
        { line: 0, u: 0.7, side: 1, h: 45, name: 'A' },
        { line: 2, u: 0.68, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 19, 'kick it up' (TASK-131, lineK 2): portal A is cut into the UNDERSIDE of the middle shelf y = 450
    // (facing down), so the ball can only enter it moving up. The ball starts above the short right floor y = 300 and
    // the flag sits on a high shelf (y = 170) above the ball's start, out of reach without the portal. One line rolls
    // the ball off the floor's left end (it drops under the middle shelf), a second line below the shelf kicks it up
    // into A; B, high on the left wall x = 40 facing right, fires it up and over onto the flag shelf.
    ballX: 900,
    ballY: 250,
    flagX: 420,
    flagY: 170,
    flagRotate: 0,
    lineK: 2,
    lines: [
        new Line(700, 300, 1000, 300, dotRadius, levelLineColor, 'line'),
        new Line(250, 450, 550, 450, dotRadius, levelLineColor, 'line'),
        new Line(40, 400, 40, 60, dotRadius, levelLineColor, 'line'),
        new Line(300, 170, 500, 170, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (400, 450) on the middle shelf's underside
    // facing down (0, 1), B at (40, 200) facing right (1, 0)
    portals: [
        { line: 1, u: 0.5, side: 1, h: 45, name: 'A' },
        { line: 2, u: 200 / 340, side: 1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 20, 'through the window twice' (TASK-133, lineK 3): a divider floor y = 420 splits the field; its only
    // opening is the window x 480..800. The ball starts on the upper-left part (it bounces in place there until a
    // line moves it; the lip x = 40 stops it rolling off the left end). The flag hangs under a shelf y = 180 right
    // above the window, 200 px higher than the ball's start, so only a teleported ball can reach it. Portal A is on
    // a floor pad at the bottom left (facing up), portal B low on the right wall x = 1240 (facing left), 250 px
    // above A. One line rolls the ball down through the window, a second line under the window feeds A, and B's
    // leftward exit stream needs a third line that turns it back up through the same window onto the flag.
    ballX: 300,
    ballY: 380,
    flagX: 660,
    flagY: 180,
    flagRotate: Math.PI,
    lineK: 3,
    lines: [
        new Line(40, 420, 480, 420, dotRadius, levelLineColor, 'line'),
        new Line(800, 420, 1240, 420, dotRadius, levelLineColor, 'line'),
        new Line(560, 180, 760, 180, dotRadius, levelLineColor, 'line'),
        new Line(120, 770, 280, 770, dotRadius, levelLineColor, 'line'),
        new Line(1240, 760, 1240, 440, dotRadius, levelLineColor, 'line'),
        new Line(40, 360, 40, 420, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (200, 770) on the bottom pad facing up (0, -1),
    // B at (1240, 520) on the right wall facing left (-1, 0)
    portals: [
        { line: 3, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 4, u: 0.75, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 21, 'bank shot' (TASK-135, lineK 2): portal A is cut into a 45-degree slope (x 480..680, rising to the right)
    // facing up-left, the first portal on a slanted line. A teleport turns the velocity by the angle between the two
    // portal fronts, so the direction the ball enters A decides where it leaves B (a floor pad on the left facing up,
    // 400 px higher than A and above the ball's start, so the ball can never drop into B): only a ball entering A
    // head-on (moving down-right) leaves B straight up into the flag that hangs under the ceiling right above B. The ball starts on a pad up and to the RIGHT of A (it bounces in place
    // there until a line moves it), so it can only fall onto A from the right, which sends it out of B to the right.
    // One line rolls it off the pad to the left, a second, steep line under that bank-shots it back down-right into A.
    ballX: 900,
    ballY: 300,
    flagX: 220,
    flagY: 80,
    flagRotate: Math.PI,
    lineK: 2,
    lines: [
        new Line(820, 320, 980, 320, dotRadius, levelLineColor, 'line'),
        new Line(480, 760, 680, 560, dotRadius, levelLineColor, 'line'),
        new Line(140, 260, 300, 260, dotRadius, levelLineColor, 'line'),
        new Line(140, 80, 300, 80, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (580, 660) on the slope facing up-left
    // (-0.71, -0.71), B at (220, 260) on the pad facing up (0, -1)
    portals: [
        { line: 1, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 2, u: 0.5, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
}
)
// Every level is open from the start (no need to win the previous one); a win still
// marks it completed (unlock 2, coral in the level grid).
for (const l of levels) l.unlock = Math.max(l.unlock || 0, 1)
let thisLevel = 0