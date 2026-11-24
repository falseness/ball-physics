// TASK-179: level route map data (concept artifacts/concepts/routemap/305-wall-full.png).
// Data only: nothing here draws. All coordinates are in the 1280x800 logical game space.
//
// slots[id] = [cx, top, w, s]: platform centre x, platform top y, platform width, flag scale. Every
// slot is hand-placed: the concept's 27 slots (305: start 1-2, left side 3-11, right side 12-19, floor
// 20-27) are kept, rows were widened by hand to fit the 22 portal levels at HEAD plus spares, and a
// top row R4 holds the spare main-branch slots.
// branches: the slot order of each branch. Levels are given to slots in play order (TASK-177):
//   start = the first two levels (srcId 1, 2), main = the levels with portals (left side of the
//   central wall climbing L1 -> L2 -> L3, through portal A/B, then R1 -> R2 -> R3 -> R4 on the right),
//   extra = the remaining (non-portal) levels on the floor row. Unused main slots are spares.
// obstacles: decorative course objects, each with its geometry (see ROUTEMAP_KINDS below).
// hops: [from, to, via]: one per consecutive slot pair of each branch plus S2 -> X1 and S2 -> M1.
//   via = optional bank/bounce points [x, y]; 'gap' marks the portal crossing (no line drawn there).
const ROUTEMAP = (() =>
{
    const MAIN_S = 0.58, EXTRA_S = 0.56, W = 60
    const slots = {
        // start (concept 1, 2)
        S1: [70, 735, W, MAIN_S], S2: [180, 690, W, MAIN_S],
        // main, left of the wall. L1 low row left -> right (hurdles), concept 3-5
        M1: [260, 610, W, MAIN_S], M2: [365, 590, W, MAIN_S], M3: [470, 610, W, MAIN_S], M4: [575, 590, W, MAIN_S],
        // L2 middle row right -> left under the gated ceiling, concept 6-8
        M5: [575, 460, W, MAIN_S], M6: [470, 440, W, MAIN_S], M7: [365, 460, W, MAIN_S], M8: [260, 440, W, MAIN_S],
        // L3 high row left -> right, last one hops into portal A, concept 9-11
        M9: [280, 310, W, MAIN_S], M10: [375, 290, W, MAIN_S], M11: [470, 310, W, MAIN_S], M12: [565, 290, W, MAIN_S],
        // main, right of the wall. R1 low row left -> right from portal B, concept 12-15
        M13: [720, 610, W, MAIN_S], M14: [840, 590, W, MAIN_S], M15: [960, 610, W, MAIN_S], M16: [1080, 590, W, MAIN_S],
        // R2 middle row right -> left (bank off the side wall into it, spring out of it), concept 16-18
        M17: [1150, 440, W, MAIN_S], M18: [1040, 420, W, MAIN_S], M19: [930, 440, W, MAIN_S], M20: [820, 420, W, MAIN_S],
        // R3 upper row left -> right, concept 19
        M21: [790, 260, W, MAIN_S], M22: [900, 240, W, MAIN_S], M23: [1010, 260, W, MAIN_S],
        // R4 top row right -> left (spares at HEAD)
        M24: [1160, 130, W, MAIN_S], M25: [1050, 110, W, MAIN_S], M26: [940, 130, W, MAIN_S], M27: [830, 110, W, MAIN_S],
        // extra, floor row left -> right, concept 20-27
        X1: [300, 745, W, EXTRA_S], X2: [418, 727, W, EXTRA_S], X3: [536, 745, W, EXTRA_S], X4: [654, 727, W, EXTRA_S],
        X5: [772, 745, W, EXTRA_S], X6: [890, 727, W, EXTRA_S], X7: [1008, 745, W, EXTRA_S], X8: [1126, 727, W, EXTRA_S]
    }
    const branches = {
        start: ['S1', 'S2'],
        main: ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10', 'M11', 'M12', 'M13', 'M14',
            'M15', 'M16', 'M17', 'M18', 'M19', 'M20', 'M21', 'M22', 'M23', 'M24', 'M25', 'M26', 'M27'],
        extra: ['X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'X8']
    }
    // central wall (concept: x 628, w 24, y 60; bottom raised 680 -> 650 to clear the floor-row flag X4)
    const wall = { x: 628, y: 60, w: 24, h: 590 }
    // portal openings: centre, facing normal, half height. A high on the left face, B low on the right face.
    const portals = [
        { name: 'A', x: 626, y: 236, nx: -1, ny: 0, h: 26 },
        { name: 'B', x: 654, y: 560, nx: 1, ny: 0, h: 26 }
    ]
    // kinds: hurdle / gate / ceiling / sidewall / pad = line {x1, y1, x2, y2, w (stroke width)};
    // gate.ceiling names its ceiling beam; bumper = circle {x, y, r}; spring = {x, y (base), h, w (half)};
    // block = rect {x, y, w, h}.
    const obstacles = [
        // L1 hurdles (M1-M2, M2-M3): x = midpoint, from min top - 20 down 46
        { id: 'hurdle_L1a', kind: 'hurdle', x1: 312.5, y1: 570, x2: 312.5, y2: 616, w: 3 },
        { id: 'hurdle_L1b', kind: 'hurdle', x1: 417.5, y1: 570, x2: 417.5, y2: 616, w: 3 },
        // L2 ceiling beam and its gates (M5-M6, M6-M7): from the beam down to min top - 58
        { id: 'ceiling_L', kind: 'ceiling', x1: 260, y1: 345, x2: 610, y2: 345, w: 2.5 },
        { id: 'gate_L2a', kind: 'gate', ceiling: 'ceiling_L', x1: 522.5, y1: 345, x2: 522.5, y2: 382, w: 3 },
        { id: 'gate_L2b', kind: 'gate', ceiling: 'ceiling_L', x1: 417.5, y1: 345, x2: 417.5, y2: 382, w: 3 },
        // bumper banking M8 -> M9 (concept 232,388 r20, moved left/up to clear M8's flag)
        { id: 'bumper_L', kind: 'bumper', x: 210, y: 375, r: 18 },
        // R1 hurdles (M13-M14, M15-M16) and the tilted pad under M14-M15
        { id: 'hurdle_R1a', kind: 'hurdle', x1: 780, y1: 570, x2: 780, y2: 616, w: 3 },
        { id: 'hurdle_R1b', kind: 'hurdle', x1: 1020, y1: 570, x2: 1020, y2: 616, w: 3 },
        { id: 'pad_R1', kind: 'pad', x1: 900 - 16 * Math.cos(-0.25), y1: 645 - 16 * Math.sin(-0.25),
            x2: 900 + 16 * Math.cos(-0.25), y2: 645 + 16 * Math.sin(-0.25), w: 3, angle: -0.25 },
        // side wall for the M16 -> M17 bank shot
        { id: 'sidewall_R', kind: 'sidewall', x1: 1215, y1: 430, x2: 1215, y2: 600, w: 3 },
        // R2 ceiling beam and its gate (M17-M18)
        { id: 'ceiling_R', kind: 'ceiling', x1: 860, y1: 330, x2: 1190, y2: 330, w: 2.5 },
        { id: 'gate_R2', kind: 'gate', ceiling: 'ceiling_R', x1: 1095, y1: 330, x2: 1095, y2: 362, w: 3 },
        // spring left of M20, launching up to M21
        { id: 'spring_R2', kind: 'spring', x: 774, y: 422, h: 26, w: 14 },
        // decorative bumpers (concept 760,250 / 1150,200; the first moved off M21's flag)
        { id: 'bumper_R3', kind: 'bumper', x: 720, y: 170, r: 16 },
        { id: 'bumper_R4', kind: 'bumper', x: 1150, y: 200, r: 14 },
        // floor blocks between X1-X2, X3-X4, X5-X6, X7-X8
        { id: 'block_X12', kind: 'block', x: 348, y: 752, w: 22, h: 20 },
        { id: 'block_X34', kind: 'block', x: 584, y: 752, w: 22, h: 20 },
        { id: 'block_X56', kind: 'block', x: 820, y: 752, w: 22, h: 20 },
        { id: 'block_X78', kind: 'block', x: 1056, y: 752, w: 22, h: 20 }
    ]
    const hops = [
        ['S1', 'S2'], ['S2', 'M1'], ['S2', 'X1'],
        ['M1', 'M2'], ['M2', 'M3'], ['M3', 'M4'],
        ['M4', 'M5', [[622, 545]]],                 // bank off the wall's left face
        ['M5', 'M6'], ['M6', 'M7'], ['M7', 'M8'],
        ['M8', 'M9', [[230, 366]]],                 // bumper_L
        ['M9', 'M10'], ['M10', 'M11'], ['M11', 'M12'],
        ['M12', 'M13', [[618, 232], 'gap', [664, 560]]], // into A, out of B
        ['M13', 'M14'],
        ['M14', 'M15', [[900, 641]]],               // pad_R1
        ['M15', 'M16'],
        ['M16', 'M17', [[1208, 520]]],              // sidewall_R
        ['M17', 'M18'], ['M18', 'M19'], ['M19', 'M20'],
        ['M20', 'M21', [[774, 392]]],               // spring_R2
        ['M21', 'M22'], ['M22', 'M23'],
        ['M23', 'M24', [[1134, 194]]],              // bumper_R4
        ['M24', 'M25'], ['M25', 'M26'], ['M26', 'M27'],
        ['X1', 'X2'],
        ['X2', 'X3', [[477, 768]]],                 // floor bounce
        ['X3', 'X4'],
        ['X4', 'X5', [[713, 768]]],
        ['X5', 'X6'],
        ['X6', 'X7', [[949, 768]]],
        ['X7', 'X8']
    ]
    // box sizes used by the validator and the renderers
    const box = { platformDepth: 12, flagW: 50, flagH: 70 }
    return { slots, branches, wall, portals, obstacles, hops, box }
})()

// Branch of a level by the TASK-177 rule: the first two play-order levels are the start, levels
// with portals are the main branch, the rest the extra branch.
function routeBranch(levels, i)
{
    if (i < 2) return 'start'
    return levels[i].portals && levels[i].portals.length ? 'main' : 'extra'
}

// Slot of every level: {slotId: levelIndex}; each branch fills its slots in play order. A level
// that finds no free slot in its branch is left out (the validator reports it).
function routeAssign(levels, map = ROUTEMAP)
{
    const out = {}, next = { start: 0, main: 0, extra: 0 }
    for (let i = 0; i < levels.length; ++i)
    {
        const b = routeBranch(levels, i), id = map.branches[b][next[b]++]
        if (id !== undefined) out[id] = i
    }
    return out
}
