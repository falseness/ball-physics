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
null, // srcId 8: removed (TASK-247)
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
null, // srcId 11: removed (TASK-247)
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
null, // srcId 14: removed (TASK-247)
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
},
{
    // Level 22, 'two laps' (TASK-137, lineK 3): portal A is on a small floor pad at the bottom (facing up), portal B
    // on the right wall (facing left) 200 px higher. A ball that falls into A comes out of B higher than it went in,
    // so every A->B lap adds that height to its energy. The flag hangs under a ceiling in the top-left corner, shielded
    // on the right by a wall x = 340 down to y = 300; it is 300 px above the ball's start (the ball bounces in place
    // on its pad until a line moves it), more than one lap can give. One line rolls the ball off its pad into A, a
    // second line under B's exit stream turns it back into A for the second lap, and the faster ball then needs a
    // third line to reach the shielded flag. A sloped roof over the start pad keeps the pad from doing line 3's job.
    ballX: 180,
    ballY: 400,
    flagX: 200,
    flagY: 100,
    flagRotate: Math.PI,
    lineK: 3,
    lines: [
        new Line(100, 420, 260, 420, dotRadius, levelLineColor, 'line'),
        new Line(480, 760, 620, 760, dotRadius, levelLineColor, 'line'),
        new Line(1240, 720, 1240, 400, dotRadius, levelLineColor, 'line'),
        new Line(120, 100, 280, 100, dotRadius, levelLineColor, 'line'),
        new Line(340, 40, 340, 300, dotRadius, levelLineColor, 'line'),
        // sloped roof over the start pad (TASK-138): a ball bouncing on the pad (or falling onto it) cannot rise
        // straight into the flag above, and the slope keeps the roof itself from becoming a launch pad
        new Line(60, 390, 260, 340, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (550, 760) on the bottom pad facing up (0, -1),
    // B at (1240, 560) on the right wall facing left (-1, 0)
    portals: [
        { line: 1, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 2, u: 0.5, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 23, 'wrong way in' (TASK-141, lineK 2): the ball starts on a slope and rolls off it by itself, straight
    // into floor portal B (facing up) in the long floor below. That is the trap: going in through B drops the ball
    // out of A, which is on a low wall under the floor (facing right) 215 px lower than B, so it loses that height
    // and flies off to the right; it can never come back up to the flag. The flag hangs under a ceiling high above
    // B, higher than the ball's start, so only an A -> B teleport (which gains the 215 px) can reach it. One line
    // has to make the ball jump over B (a bridge over B would also block B's exit stream), and a second line under
    // the floor's open right end has to send the falling ball back left into A, so that it comes out of B going up.
    ballX: 110,
    ballY: 238,
    flagX: 500,
    flagY: 50,
    flagRotate: Math.PI,
    lineK: 2,
    lines: [
        new Line(60, 240, 330, 330, dotRadius, levelLineColor, 'line'),
        new Line(40, 520, 760, 520, dotRadius, levelLineColor, 'line'),
        new Line(600, 600, 600, 800, dotRadius, levelLineColor, 'line'),
        new Line(420, 50, 580, 50, dotRadius, levelLineColor, 'line'),
        new Line(60, 180, 60, 240, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (600, 735) on the low wall facing right (1, 0),
    // B at (555, 520) on the floor facing up (0, -1)
    portals: [
        { line: 2, u: 0.675, side: -1, h: 45, name: 'A' },
        { line: 1, u: 0.715, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 24, 'pick the half' (TASK-143, lineK 3): a teleport keeps the ball's offset along the opening but
    // mirrors it (a ball touching A at s along A's opening leaves B at -s), so WHERE the ball goes into A decides
    // where it comes out of B. B is on the left wall x = 60 (facing right), and a long shelf y = 360 starts right at
    // B's centre and splits B's mouth into two lanes: the upper lane leads above the shelf to the flag, the lower
    // lane into a tunnel (shelf + floor y = 410) that throws the ball off the right edge of the field. A is on a
    // floor pad at the bottom (facing up), 400 px lower than B. The ball starts on a pad to the left of A (it bounces
    // in place there until a line moves it); rolled off its pad it drops onto A's LEFT half, which is the tunnel
    // lane. A's right half (the upper lane) is under a small roof, so it can only be reached from the right: one line
    // carries the ball past A, a second banks it back left under the roof into A's right half, and the flag, in a
    // pocket under the ceiling that is open only to the right, needs a third line that sends the ball back left.
    ballX: 260,
    ballY: 470,
    flagX: 820,
    flagY: 110,
    flagRotate: Math.PI,
    lineK: 3,
    lines: [
        new Line(60, 200, 60, 520, dotRadius, levelLineColor, 'line'),
        new Line(60, 360, 1240, 360, dotRadius, levelLineColor, 'line'),
        new Line(60, 410, 1240, 410, dotRadius, levelLineColor, 'line'),
        new Line(400, 760, 560, 760, dotRadius, levelLineColor, 'line'),
        new Line(180, 490, 340, 490, dotRadius, levelLineColor, 'line'),
        new Line(700, 110, 900, 110, dotRadius, levelLineColor, 'line'),
        new Line(470, 610, 560, 630, dotRadius, levelLineColor, 'line'),
        new Line(700, 110, 700, 260, dotRadius, levelLineColor, 'line'),
        new Line(700, 260, 900, 260, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (480, 760) on the bottom pad facing up (0, -1),
    // B at (60, 360) on the left wall facing right (1, 0), right where the shelf (line 1) meets the wall
    portals: [
        { line: 3, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 0, u: 0.5, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 25, 'skim, don't drop' (TASK-145, lineK 2): portal A lies in the floor of a pocket at the bottom right
    // (facing up), portal B on a wall at the right edge (facing right), 240 px higher, at the foot of a narrow chimney
    // whose top holds the flag, higher than the ball's start. A floor portal and a wall portal are a quarter turn
    // apart, so the ball's speed ALONG A's floor comes out of B going straight up the wall, and only its speed INTO
    // the floor comes out sideways. A ball dropped into A shoots out of B sideways, under the chimney and straight off
    // the right edge; only a ball that skims into A fast and flat climbs the chimney to the flag. A tall crest wall
    // (x = 840, top y = 450) closes A's pocket off from the well the ball drops into from its start slope: one line in
    // the well has to lift the ball over the crest, and a second line inside the pocket has to turn its steep fall
    // into a flat skim into A. Over the crest the ball is too slow and, on any line ridden over it, enters A too
    // steeply, so one line cannot do both jobs.
    ballX: 440,
    ballY: 300,
    flagX: 1225,
    flagY: 140,
    flagRotate: Math.PI,
    lineK: 2,
    lines: [
        new Line(400, 250, 400, 310, dotRadius, levelLineColor, 'line'),
        new Line(400, 310, 490, 335, dotRadius, levelLineColor, 'line'),
        new Line(1180, 140, 1180, 600, dotRadius, levelLineColor, 'line'),
        new Line(1270, 140, 1270, 380, dotRadius, levelLineColor, 'line'),
        new Line(1180, 140, 1270, 140, dotRadius, levelLineColor, 'line'),
        new Line(840, 760, 1240, 760, dotRadius, levelLineColor, 'line'),
        new Line(840, 450, 840, 760, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (1080, 760) in the pocket floor facing up
    // (0, -1), B at (1180, 520) on the right-edge wall facing right (1, 0), below the chimney (x = 1180 wall + x = 1270
    // wall under the y = 140 ceiling)
    portals: [
        { line: 5, u: 0.6, side: -1, h: 45, name: 'A' },
        { line: 2, u: 0.82609, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 26, 'one line, two jobs' (TASK-147, lineK 4): the ball bounces in place on a pad in the top-left
    // corner, under the flag's pocket (a ceiling, a wall x = 240 on the right and the pad as the floor, open only
    // to the left). Portal A lies in the floor of a shaft at the bottom (facing up), portal B on a short wall
    // on the right (facing left), 360 px higher, so only an A -> B teleport gives the ball the height the flag
    // needs. The trip has five jobs and the player has four lines: (1) tip the ball off the pad to the left,
    // (2) a long ramp under the pad's open side that carries the falling ball right to the shaft, (3) a
    // backboard right of the shaft (TASK-148: the shaft has a roof and only a side window on its right, above
    // a short right wall, so a ball arcing in from the left cannot drop into A; it must be bounced back; the
    // roof slants up to the right, so a ball that enters B from the left and leaves A upwards is deflected out
    // of the window instead of falling back into A, i.e. B is no shortcut around the backboard), (4) a
    // lift for B's almost flat exit stream, which flies back left over the field and would fall off its left
    // edge, and (5) a reflector at the left edge that turns the rising ball right into the pocket. B's stream
    // comes back over the ramp of job 2 in the opposite direction, so the same line can do job 4: a ball that
    // lands on it going left bounces up-left steeply. One line has to work on both sides of the teleport.
    ballX: 170,
    ballY: 280,
    flagX: 175,
    flagY: 130,
    flagRotate: Math.PI,
    lineK: 4,
    lines: [
        new Line(100, 300, 240, 300, dotRadius, levelLineColor, 'line'),
        new Line(240, 130, 240, 300, dotRadius, levelLineColor, 'line'),
        new Line(60, 130, 260, 130, dotRadius, levelLineColor, 'line'),
        new Line(690, 760, 810, 760, dotRadius, levelLineColor, 'line'),
        new Line(1060, 340, 1060, 460, dotRadius, levelLineColor, 'line'),
        new Line(690, 640, 690, 760, dotRadius, levelLineColor, 'line'),
        new Line(810, 720, 810, 760, dotRadius, levelLineColor, 'line'),
        new Line(690, 640, 810, 580, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (750, 760) in the shaft floor facing up
    // (0, -1), B at (1060, 400) on the short right wall facing left (-1, 0)
    portals: [
        { line: 3, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 4, u: 0.5, side: 1, h: 45, name: 'B' }
    ],
    unlock: 0
},
null, // srcId 27: removed (TASK-247)
{
    // Level 28, 'wrap-around' (TASK-151, lineK 2): the field wraps sideways. Portal A is cut into a wall at the
    // LEFT edge (facing right) and portal B into a wall at the RIGHT edge (facing left), at the same height, so the
    // pair maps velocity unchanged: a ball that flies out through the left edge comes back in through the right edge
    // still moving left, on the same arc. A wall in the middle (x = 760, y 200..790) stands higher than the ball can
    // ever reach (it starts bouncing in place on a pad at y 300, peak y 260), so the flag's half of the field is
    // reachable only by sending the ball AWAY from it: off the left edge into A. The flag sits in a pocket at the
    // top right that is open only on its left side, so the ball coming back in moving left has to be turned around
    // by a second line and thrown up-right into the pocket.
    ballX: 520,
    ballY: 260,
    flagX: 1190,
    flagY: 450,
    flagRotate: 0,
    lineK: 2,
    lines: [
        new Line(20, 470, 20, 730, dotRadius, levelLineColor, 'line'),
        new Line(1260, 470, 1260, 730, dotRadius, levelLineColor, 'line'),
        new Line(460, 300, 580, 300, dotRadius, levelLineColor, 'line'),
        new Line(760, 200, 760, 790, dotRadius, levelLineColor, 'line'),
        new Line(1100, 330, 1270, 330, dotRadius, levelLineColor, 'line'),
        new Line(1100, 450, 1270, 450, dotRadius, levelLineColor, 'line'),
        new Line(1270, 330, 1270, 450, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (20, 600) on the left-edge wall facing right
    // (1, 0), B at (1260, 600) on the right-edge wall facing left (-1, 0); same height, so a teleport keeps the
    // velocity as it is (a horizontal wrap-around)
    portals: [
        { line: 0, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 1, u: 0.5, side: 1, h: 45, name: 'B' }
    ],
    unlock: 0
},
null, // srcId 29: removed (TASK-247)
{
    // Level 30, 'sky is lava' (TASK-155, lineK 2): the ball bounces in place on a pad at the left (peak y 420). Portal
    // A lies in the floor of a shaft (y 780), portal B in a floating plate high up (y 260), both facing up: a ball that
    // falls into A comes out of B rising at the same speed (the velocity is reversed), 520 px higher. That is more
    // energy than the field holds: B's stream would climb to y = -100 and leave through the top edge, which ends the
    // run. So line 1 knocks the ball off its pad into the shaft, and line 2 is a roof under the sky: the rising ball
    // hits its underside and is turned down onto the flag tower (top y 300, 120 px above the ball's peak, so the flag
    // needs the teleport).
    ballX: 200,
    ballY: 420,
    flagX: 1150,
    flagY: 300,
    flagRotate: 0,
    lineK: 2,
    lines: [
        new Line(140, 560, 260, 560, dotRadius, levelLineColor, 'line'),
        new Line(500, 640, 500, 780, dotRadius, levelLineColor, 'line'),
        new Line(700, 640, 700, 780, dotRadius, levelLineColor, 'line'),
        new Line(500, 780, 700, 780, dotRadius, levelLineColor, 'line'),
        new Line(840, 260, 960, 260, dotRadius, levelLineColor, 'line'),
        new Line(1100, 300, 1200, 300, dotRadius, levelLineColor, 'line'),
        new Line(1100, 300, 1100, 790, dotRadius, levelLineColor, 'line'),
        new Line(1200, 300, 1200, 790, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (600, 780) in the shaft floor facing up
    // (0, -1), B at (900, 260) in the floating plate facing up (0, -1); same facing, so a teleport reverses the velocity
    portals: [
        { line: 3, u: 0.5, side: -1, h: 45, name: 'A' },
        { line: 4, u: 0.5, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 31, 'low door' (TASK-157, lineK 4): portal A is a tall door (h 120, y 520..760) facing right in the
    // divider wall x = 600, and a thick porch slab (y 680..700) splits it into an upper and a lower part. A
    // teleport keeps the ball's speed, and the ball is faster the lower it goes into the door, so the entry height
    // is an energy dial: B (a small floor portal facing up, far left, under a roof) throws a ball from the upper part
    // only to an energy level of y >= 240, one from the lower part to y 146..200. The flag hangs in a bell under the
    // top edge that is open only at the bottom, and it needs y <= ~219. So the ball, which bounces in place on a pad at
    // the top right, has to be (1) kicked off the pad and (2) turned into the low tunnel under the porch (a kick alone
    // cannot get that low before the tunnel), then after B (3) thrown out under B's roof towards the bell and
    // (4) turned straight up into the bell.
    ballX: 1180,
    ballY: 300,
    flagX: 520,
    flagY: 110,
    flagRotate: Math.PI,
    lineK: 4,
    lines: [
        new Line(1120, 440, 1240, 440, dotRadius, levelLineColor, 'line'),
        new Line(600, 780, 680, 780, dotRadius, levelLineColor, 'line'),
        new Line(600, 680, 680, 680, dotRadius, levelLineColor, 'line'),
        new Line(600, 700, 680, 700, dotRadius, levelLineColor, 'line'),
        new Line(680, 680, 680, 700, dotRadius, levelLineColor, 'line'),
        new Line(600, 240, 600, 780, dotRadius, levelLineColor, 'line'),
        new Line(100, 620, 220, 620, dotRadius, levelLineColor, 'line'),
        new Line(60, 470, 260, 470, dotRadius, levelLineColor, 'line'),
        new Line(260, 470, 260, 560, dotRadius, levelLineColor, 'line'),
        new Line(440, 110, 600, 110, dotRadius, levelLineColor, 'line'),
        new Line(440, 110, 440, 220, dotRadius, levelLineColor, 'line'),
        new Line(600, 110, 600, 220, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (600, 640) on the divider wall facing right
    // (1, 0), h 120; B at (160, 620) in the small floor plate facing up (0, -1), h 45
    portals: [
        { line: 5, u: 0.740741, side: -1, h: 120, name: 'A' },
        { line: 6, u: 0.5, side: -1, h: 45, name: 'B' }
    ],
    unlock: 0
},
{
    // Level 32, 'under the wall' (TASK-159, lineK 3): a wall stands on floor portal A (centre (560, 720), h 50,
    // facing up), so A's left half opens into the start side and its right half into a closed shaft that holds the
    // flag. B is a wall portal (x 760, centre y 650, h 50) facing right over open ground. A teleport mirrors the
    // offset along the opening, so a ball that goes down A's left half comes out of B's lower half, and a ball sent
    // back in through B comes out of A on the side that matches the half of B it went in through: back through the
    // lower half -> out of A's left half again (the start side); back through the UPPER half -> out of A's right half,
    // under the wall, into the flag shaft. So the ball, which bounces in place on a pad at the top left, has to be
    // (1) kicked off the pad, (2) turned flat into the low tunnel under the lid, so it drops into A's left half (the
    // tunnel has no floor before A, a kick alone falls into the pit), and (3) after B, turned back up into B's upper
    // half.
    ballX: 160,
    ballY: 300,
    flagX: 630,
    flagY: 400,
    flagRotate: Math.PI,
    lineK: 3,
    lines: [
        new Line(100, 440, 220, 440, dotRadius, levelLineColor, 'line'),
        new Line(490, 720, 680, 720, dotRadius, levelLineColor, 'line'),
        new Line(560, 240, 560, 720, dotRadius, levelLineColor, 'line'),
        new Line(420, 620, 560, 620, dotRadius, levelLineColor, 'line'),
        new Line(640, 240, 640, 720, dotRadius, levelLineColor, 'line'),
        new Line(560, 400, 640, 400, dotRadius, levelLineColor, 'line'),
        new Line(760, 240, 760, 720, dotRadius, levelLineColor, 'line')
    ],
    // wall portals {line, u, side, h, name} (see portalResolve): A at (560, 720) in the floor facing up (0, -1),
    // h 50, the wall x = 560 standing on its centre; B at (760, 650) on the wall x = 760 facing right (1, 0), h 50
    portals: [
        { line: 1, u: 0.368421, side: -1, h: 50, name: 'A' },
        { line: 6, u: 0.854167, side: -1, h: 50, name: 'B' }
    ],
    unlock: 0
}
)
// TASK-177: stable source ids and play order. srcId = the level's definition number (1-based, the
// order above, never renumbered). Play order: level 1, level 2, then every level with a non-empty
// `portals` list, then every remaining level (both groups in definition order). Tools and tests
// address a level by srcId through levelBySrc(n) (index into the reordered levels).
// TASK-247: srcId 8, 11, 14, 27 and 29 were removed from the game; their definitions are null placeholders
// above so every remaining level keeps its srcId. levelBySrc() returns -1 for them; saved data naming them
// (bp.progress.v1, bp.lines.v1, bp.stats.v1) is ignored on load and left as stored.
levels.forEach((l, i) => { if (l) l.srcId = i + 1 })
levels = levels.filter(l => l)
{
    const hasPortals = l => !!(l.portals && l.portals.length)
    const head = levels.slice(0, 2), rest = levels.slice(2)
    levels = head.concat(rest.filter(hasPortals), rest.filter(l => !hasPortals(l)))
}
function levelBySrc(n)
{
    return levels.findIndex(l => l.srcId === n)
}
// Every level is open from the start (no need to win the previous one); a win still
// marks it completed (unlock 2, coral in the level grid).
for (const l of levels) l.unlock = Math.max(l.unlock || 0, 1)
// TASK-178: saved progress. The solved levels are stored by srcId (never by play-order index) under
// the key PROGRESS_STORE as JSON {solved: [srcId, ...]}. TASK-184: storage goes through the platform
// facade (platform.js, PLATFORM.storage); boot (index.html) reads the key with getMany before the
// first frame and passes the result to loadProgress. Blocked storage or an invalid value means
// nothing solved, without console errors.
const PROGRESS_STORE = 'bp.progress.v1'
function progressSolved()
{
    return levels.filter(l => l.unlock == 2).map(l => l.srcId).sort((a, b) => a - b)
}
// values: the PLATFORM.storage.getMany result ({key: string | null})
function loadProgress(values)
{
    let solved = []
    try
    {
        const v = JSON.parse(values && values[PROGRESS_STORE])
        if (v && Array.isArray(v.solved)) solved = v.solved
    }
    catch (e) { solved = [] }
    for (const id of solved)
    {
        const i = Number.isInteger(id) ? levelBySrc(id) : -1
        if (i >= 0) levels[i].unlock = 2
    }
}
function saveProgress()
{
    return PLATFORM.storage.setMany({ [PROGRESS_STORE]: JSON.stringify({ solved: progressSolved() }) })
}
let thisLevel = 0