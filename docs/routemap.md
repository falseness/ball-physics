# Route map (level select)

The pause menu's **Levels** button opens a full-screen route map (concept
`artifacts/concepts/routemap/305-wall-full.png`). Every level is a flag on a platform ("slot");
hovering or the first click/tap on a level shows its preview card, the card's play button or a
second click/tap on the same level starts it. The HUD menu icon goes back to the pause menu.

Files:

| File | Role |
| --- | --- |
| `js/routemap.js` | Data only: `ROUTEMAP` (slots, branches, wall, portals, obstacles, hops) and helpers (`routeBranch`, `routeAssign`, `routeSlotBox`, `routeLevelAt`, `routeLevelPoint`, `routeFlagRect`, `routeSlotOf`). |
| `js/mapdraw.js` | Drawing (cached map layer + live hover/selection/card layer), input (`mapOpen`, `mapClick`, `mapMove`) and the debug hook. |
| `js/levelsRects.js` | `levelPick(i)`: the single "start level i from a menu" path. The old 8-column grid is gone. |
| `tests/visual/map_check.mjs` | Node validator of the map data (no browser). |
| `tests/visual/map_slots.py` | Debug render of the validated boxes over the concept image. |

## Level order and srcId

`js/levels.js` defines the levels in a fixed source order. Each level gets
`srcId` = its 1-based position in that definition list. srcIds are never renumbered; tools, tests
and saved progress address a level by srcId through `levelBySrc(n)` (index into the play order).

The play order (the `levels` array the game uses) is built from the definitions:

1. level srcId 1,
2. level srcId 2,
3. every other level with a non-empty `portals` list, in definition order,
4. every remaining (non-portal) level, in definition order.

The map follows the same rule (`routeBranch`): play-order levels 0 and 1 are the **start** branch,
portal levels the **main** branch (left of the central wall, through portal A/B, up the right
side), the rest the **extra** branch (floor row). `routeAssign` gives each branch's levels to that
branch's slots (`ROUTEMAP.branches`) in play order. The number shown on a flag is the play-order
position (index + 1), not the srcId.

## Saved progress

Solved levels are stored in `localStorage['bp.progress.v1']` as JSON `{"solved": [srcId, ...]}`
(sorted srcIds, never play-order indices, so reordering levels keeps progress). All levels are
unlocked from the start (`unlock` 1); a solved level has `unlock` 2 (completed flag on the map).
Reads and writes are guarded: blocked storage or a malformed value means "nothing solved" without
console errors. To reset progress: `localStorage.removeItem('bp.progress.v1')`.

## Adding a slot for a new level

1. Add the level to `js/levels.js` (at the end, so existing srcIds do not change).
2. Decide its branch: portal level -> `main`, otherwise `extra`.
3. Check whether the branch has a spare slot: `node tests/visual/map_check.mjs` prints
   `branchLevels`, `slotsUsed`, `spareSlots` and `assignment`. The main branch keeps spare slots
   (M23-M27 at the time of writing, the validator requires at least 4); the extra branch
   (X1-X8) is full, so a new non-portal level needs a new `X` slot.
4. To add a slot, in `js/routemap.js`:
   - add `ID: [cx, top, w, s]` to `slots` (platform centre x, platform top y, platform width,
     flag scale; 1280x800 game coordinates);
   - append the id to its branch in `branches` (the array order is the play order on the map);
   - add a hop `[prevId, ID]` (optionally with via points `[[x, y], ...]` for banks/bounces, or
     `'gap'` for a portal crossing) so the route line reaches it.
5. Run the validator and, if needed, the debug render:

   ```sh
   node tests/visual/map_check.mjs            # one JSON line, exit 1 on any problem
   python3 tests/visual/map_slots.py --out /tmp/slots.png   # boxes over the concept image
   ```

   map_check fails when a level has no slot, two slots are closer than 70 px, an obstacle / the
   wall / a portal intersects a platform or flag box, a hop is missing or references an unknown
   slot, a slot or obstacle is off the 30..1250 x 30..772 area, a slot overlaps the menu icon, or
   fewer than 4 spare main slots remain. `problems` lists the failures.
6. Run the map scenarios: `python3 tests/visual/shoot.py --task <dir> --scenarios map,map_progress,map_open,map_play`.

## Debug hook

In the browser console (or from tests via `page.evaluate`):

```js
window.mapDebug([1, 2, 11, 12])   // srcIds to show as solved
```

It opens the map with exactly those srcIds solved (all others unlocked, unsolved), in memory only
(nothing is written to `bp.progress.v1`), stops physics and closes the menus. It returns the
1-based number of the next level to play (the lamp). After drawing, `window.mapState` holds the
render stats (`next`, `hops`, `coralHops`, `lamps`, `flags`, `slots`, `builds`); `window.mapCard` /
`window.mapCardInfo` describe the preview card, and `window.mapCardCheck()` returns the card
layout of every level (overlap / on-screen check). `shoot.py` scenarios `map` and `map_progress`
use the hook.
