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
}
)
// Every level is open from the start (no need to win the previous one); a win still
// marks it completed (unlock 2, coral in the level grid).
for (const l of levels) l.unlock = Math.max(l.unlock || 0, 1)
let thisLevel = 0