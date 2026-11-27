# Route map (level select)

The **Levels** button (the last button) of the pause menu (resume / restart / editor / Levels) and of the level-complete
window (next level / restart / editor / Levels; TASK-255, both from `menuLayout(kind)` in js/menu.js) opens a full-screen route map (concept
`artifacts/concepts/routemap/305-wall-full.png`). Every level is a flag on a platform ("slot");
hovering or the first click/tap on a level shows its preview card, the card's play button or a
second click/tap on the same level starts it. The HUD menu icon goes back to the pause menu.

TASK-258: a plain `editor` button (the menus' `menuButton` look, 150x50) sits after the last level, on the floor row:
`routeEditorButton(levels)` (js/routemap.js) puts it 20 px right of the box of the last used extra-branch slot
(`routeAssign`; X7 = play-order level 27 with 27 levels), its bottom 4 px above that platform's top, so it follows the
level count. A click or tap sends `ui:map_editor:map` and opens the editor on a blank level (`editorBlankLevel()`, the
`new` content) with `editor.origin = 'map'` (`editor:open:new:map`); play-test / back, export and import work as
usual, and `exit` returns to the map without writing anything into `levels[]` or changing `thisLevel`. Preview cards
avoid the button (`mapCardLayout`), and map_check fails when the button leaves the 30..1250 area or overlaps a used
flag / platform, an obstacle, a preview card or the menu icon.
Regression (TASK-259): the shoot scenario `map_editor` (tests/visual/shoot.py: click the button, blank editor, exit
back to the map, `levels[]` sha256 unchanged) runs in `tests/regression/run_checks.sh` preview (SH1) and full
(tests/regression/shard1.txt); map_check (both modes) checks the button position and overlaps.

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

## Level table (27 levels)

TASK-247 removed srcId 8, 11, 14, 27 and 29 (display 30, 3, 6, 19 and 21 of the earlier 32-level order; user:
"lets remove completely levels: 3, 6, 19, 21, 30"). Their entries in `js/levels.js` are `null` placeholders, so the
remaining levels keep their srcId; display numbers and map slots close the gaps. Current play order
(display = number on the flag; from `node tests/visual/map_check.mjs` `assignment`):

| display | srcId | branch | slot |
| --- | --- | --- | --- |
| 1 | 1 | start | S1 |
| 2 | 2 | start | S2 |
| 3 | 12 | main | M1 |
| 4 | 13 | main | M2 |
| 5 | 15 | main | M3 |
| 6 | 16 | main | M4 |
| 7 | 17 | main | M5 |
| 8 | 18 | main | M6 |
| 9 | 19 | main | M7 |
| 10 | 20 | main | M8 |
| 11 | 21 | main | M9 |
| 12 | 22 | main | M10 |
| 13 | 23 | main | M11 |
| 14 | 24 | main | M12 |
| 15 | 25 | main | M13 |
| 16 | 26 | main | M14 |
| 17 | 28 | main | M15 |
| 18 | 30 | main | M16 |
| 19 | 31 | main | M17 |
| 20 | 32 | main | M18 |
| 21 | 3 | extra | X1 |
| 22 | 4 | extra | X2 |
| 23 | 5 | extra | X3 |
| 24 | 6 | extra | X4 |
| 25 | 7 | extra | X5 |
| 26 | 9 | extra | X6 |
| 27 | 10 | extra | X7 |

Spare slots: main M19-M27, extra X8.

## Saved progress

Solved levels are stored under the key `bp.progress.v1` as JSON `{"solved": [srcId, ...]}`
(sorted srcIds, never play-order indices, so reordering levels keeps progress). All levels are
unlocked from the start (`unlock` 1); a solved level has `unlock` 2 (completed flag on the map).
All storage goes through the platform facade (`PLATFORM.storage`, see docs/platform-sdk.md): boot
(index.html `boot()`) awaits `PLATFORM.init()`, reads `bp.progress.v1` and `bp.editorBar.v1` with
`getMany` before the first frame (`loadProgress`, `editorBarLoad`), and `saveProgress` writes with
`setMany`. Blocked storage or a malformed value means "nothing solved" without console errors (the
local backend keeps values in memory). To reset progress with the local backend:
`localStorage.removeItem('bp.progress.v1')`.

## Storage (platform facade)

The game never touches `localStorage` directly; every read and write goes through `PLATFORM.storage`
(`platform.js` + one backend under `platform/backends/`, copied as-is from grapnelninja c61a049).
Boot (`boot()` in index.html) awaits `PLATFORM.init()`, then reads all four keys in one
`PLATFORM.storage.getMany([...])` call before the first frame and sets `bootComplete = true`.

| key | owner | value |
| --- | --- | --- |
| `bp.progress.v1` | js/levels.js (`PROGRESS_STORE`, `loadProgress` / `saveProgress`) | `{"solved": [srcId, ...]}` |
| `bp.lines.v1` | js/linestore.js (`LINES_STORE`, `linesLoad` / `linesSaveDraft` / `linesSavePassed`) | `{[srcId]: {draft, passed, sha}}`, see Saved lines |
| `bp.editorBar.v1` | js/editor.js (`EDITOR_BAR_STORE`, `editorBarLoad` / `editorBarSave`) | editor toolbar position |
| `bp.speed.v1` | index.html (`SPEED_STORE`, `speedLoad` / `speedToggle`) | `'3'` = 3x, anything else 1x; see Speed button |

Writes use `PLATFORM.storage.setMany`; a throwing or rejecting backend (blocked storage) is swallowed,
so the game keeps playing with in-memory values and no console errors.

Switching the backend: index.html loads `platform/backends/local.js` and then `platform.js`. For a
portal build add the portal SDK tag (if any) and the portal backend tag right after `local.js`, e.g.

```html
<script src = "platform/backends/local.js"></script>
<script src = "platform/backends/itch.js"></script>
<script src = "platform.js"></script>
```

The SDK tags and backend ids (`local`, `itch`, `gamepix`, `y8`, `playgama`) are listed in
docs/platform-sdk.md ("Selecting a backend"). `python3 tests/platform/test_backends.py --out <json>`
does this tag swap in a Playwright route for all five backends and checks a storage round trip and
zero page errors.

## Saved lines

The player's lines are saved per level in `bp.lines.v1`, keyed by `srcId` (never the play-order
index). When a level is opened (`levelChoosed(i)` = `levelReset(i)` + `linesRestore(i)`):

- a) level not passed yet: the last state of the lines is shown (`draft`, written by
  `linesSaveDraft` after a line is drawn, a dragged line is dropped, or a line is deleted);
- b) level passed at least once: the lines of the last pass are shown (`passed`, written by
  `linesSavePassed` once per real win). `passed` wins over `draft`; nothing saved means no lines.

At most `lineK` lines are restored; `linesK` is set to the restored count. Saved values survive a page
reload (they are read at boot through the facade).

Sha guard: each entry stores `sha = levelGeometrySha(level)` (FNV-1a over the level's lines, portals,
ball start and flag). If the level's geometry changes (edited in the editor), the sha no longer matches,
the stale entry is ignored and the next save replaces it, so lines are never restored onto a different
layout. The editor and play-tests (`editorMode`, `playtestLevel`) never read or write this key.

Restart: the menu 'restart', the win-window 'restart' and a ball falling off the map call
`restartKeepLines()`: the ball and level go back to the start and the player's current lines (and
`linesK`) are kept, not reloaded from storage. `restart()` (used by tests/portal/sim.py) is
`levelChoosed(thisLevel)` and restores the saved lines. Checked by the `lines_*` scenarios of
tests/visual/shoot.py.

## Speed button

Placement and visibility: a square 63x63 HUD box with two arrows and a "3x" label (concept
artifacts/concepts/speed/14-arrow-centre-big3x-v2.png), drawn by `drawSpeedIcon()` in js/menu.js.
`speedIconRect()` in index.html is the restart box shifted 73 px left (63 px box + 10 px gap), i.e.
`(978, 20, 63, 63)`, left of the restart box; the run/play box is unchanged. `speedIconVisible()` is
`restartIconVisible()`: shown only after 'run' was clicked (`levelStarted`), and hidden in the editor,
the level menu and the win window. Off = plain HUD box and ink; on = coral box with green arrows. A
click or tap toggles `speedMul` 1 <-> 3 (`speedToggle()`); it is checked before the restart box and
never starts a player line. The play-test 'edit' box moved to `x-292` to make room.

Storage: key `bp.speed.v1` via `PLATFORM.storage` (`'3'` or `'1'`). `speedLoad()` reads it in the
boot `getMany`, so the choice survives a reload; a blocked backend is swallowed and the game keeps the
in-memory value.

Chunked stepping: `gameMechanics()` runs `speedMul` chunks per frame; each chunk is exactly one 1x
frame (`cyclesPerTact` physics steps with the same per-step flag-collision, play-test and off-map
handling). The frame ends after a chunk with an off-map restart, physics turned off, or a new win
(`levelCompletedWindow` false -> true), so a 3x run reaches the same state as 1x in ceil(n/3) frames.

Trail rule: one `trailRecord` sample per chunk (a teleport during the chunk starts a new segment),
so a 3x run draws the same trail points as 1x, only faster.

Checks: `tests/visual/speed_check.py` (srcId 1, 12, 24 win at 1x and 3x, 0 state mismatches,
identical trails) and the `speed_*` scenarios of tests/visual/shoot.py.

## Adding a slot for a new level

1. Add the level to `js/levels.js` (at the end, so existing srcIds do not change).
2. Decide its branch: portal level -> `main`, otherwise `extra`.
3. Check whether the branch has a spare slot: `node tests/visual/map_check.mjs` prints
   `branchLevels`, `slotsUsed`, `spareSlots` and `assignment`. The main branch keeps spare slots
   (M19-M27 at the time of writing, the validator requires at least 4); the extra branch
   (X1-X8) has one spare slot (X8); once it is used, a new non-portal level needs a new `X` slot.
   The map's `editor` button follows the last used `X` slot: with X8 used it would leave the field, so
   map_check fails until the floor row (or `ROUTE_EDITOR_BTN`) is rearranged.
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
   fewer than 4 spare main slots remain, or the `editor` button (TASK-258) is misplaced or overlaps
   something. `problems` lists the failures.
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
