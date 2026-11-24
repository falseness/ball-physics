# Telemetry

Game telemetry goes through the ANALYTICS facade (`analytics.js`, ported from grapnelninja in TASK-190;
backends in `analytics/backends/`). Game code never calls the backend directly. Level telemetry lives in
`js/telemetry.js` (`TELEMETRY`, TASK-191; UI, line and session events TASK-192). Builds from automated browsers start with `test-` (see
`analyticsBuild()` in `index.html`) so reports can leave them out.

## Level attempts (TASK-191)

Each level start is one **attempt** of that level. Levels are identified by `srcId` (`levels[thisLevel].srcId`),
never by play-order index. An attempt starts when:

| reason    | where                                                                     |
|-----------|---------------------------------------------------------------------------|
| `boot`    | the page opens the current level (`boot()` in `index.html`)               |
| `map`     | a level is picked on the route map (`levelPick`, `js/levelsRects.js`)     |
| `next`    | 'next level' on the completion window                                     |
| `restart` | a restart button: HUD restart box, pause menu 'restart', completion window 'restart' |
| `offmap`  | the automatic restart after the ball left the map                         |
| `resume`  | a run starts and no attempt is open (back from the editor, map closed back to the level, bfcache restore) |

An attempt ends once: a win (`Complete`), off-map / restart / abandon (`Fail`), or silently when the editor
is opened from the level. Leaving an unwon attempt by opening the map, by 'next level' or by page hide sends
`abandon`. Play-tests and the editor send nothing and count nothing.

## Event catalogue

`<srcId>` is the level's source id, level names in progression events are `L<srcId>`.

| event id | when | value | ticket |
|----------|------|-------|--------|
| progression `Start`, `L<srcId>` | an attempt starts (any reason above) | - | TASK-191 |
| progression `Complete`, `L<srcId>` | the attempt's first win (ball reaches the flag) | - | TASK-191 |
| progression `Fail`, `L<srcId>` | an unwon attempt ends by off-map, restart button or abandon | - | TASK-191 |
| `level:<srcId>:attempt` | an attempt starts, right after progression `Start` | attempt number of this user for this level (1, 2, ...) | TASK-191 |
| `level:<srcId>:win` | win, right after progression `Complete` | seconds from the attempt's first run to the win | TASK-191 |
| `level:<srcId>:win_attempt` | win, after `win` | attempt number of the winning attempt | TASK-191 |
| `level:<srcId>:first_win` | the user's first win of this level (once per user, from `bp.stats.v1`) | - | TASK-191 |
| `level:<srcId>:fail:offmap` | the ball left the map (automatic restart follows) | - | TASK-191 |
| `level:<srcId>:restart` | the player pressed a restart button (HUD, pause menu, completion window) | - | TASK-191 |
| `level:<srcId>:abandon` | an unwon attempt was left: map opened, next level, page hide | - | TASK-191 |
| facade `startSession` | the page boots (`analyticsStart()`), and a page restored from the back/forward cache | - | TASK-190 |
| facade `endSession` | `pagehide` (after `flush`) | - | TASK-190 |
| `ui:run:<ctx>` | the HUD play box starts or resumes the run | - | TASK-192 |
| `ui:pause:<ctx>` | the HUD play box pauses the run | - | TASK-192 |
| `ui:restart:<ctx>` | a restart button: HUD restart box, pause menu 'restart', completion window 'restart' (before the `level:` events) | - | TASK-192 |
| `ui:menu_open:<ctx>` | the HUD menu icon opens the pause menu | - | TASK-192 |
| `ui:menu_close:<ctx>` | the pause menu closes by any of its buttons, right after that button's event | - | TASK-192 |
| `ui:resume:<ctx>` | pause menu 'resume' | - | TASK-192 |
| `ui:map_open:<ctx>` | pause menu 'Levels' opens the route map | - | TASK-192 |
| `ui:map_close:<ctx>` | the map closes: its menu icon (back to the pause menu) or a level starts from it | - | TASK-192 |
| `ui:map_level:<ctx>` | a click / tap on a level slot on the map (selects it, or starts the selected one) | srcId of that level | TASK-192 |
| `ui:preview_play:<ctx>` | the preview card's play button | srcId of that level | TASK-192 |
| `ui:next_level:<ctx>` | completion window 'next level' | - | TASK-192 |
| `ui:speed_on:<ctx>` | the HUD speed box switches to 3x | - | TASK-192 |
| `ui:speed_off:<ctx>` | the HUD speed box switches back to 1x | - | TASK-192 |
| `ui:editor_open:<ctx>` | the editor button (pause menu or completion window; not in play-tests) | - | TASK-192 |
| `ui:line_delete_bin:<ctx>` | the bin of a selected player line | - | TASK-192 |
| `lines:<srcId>:place` | a player line is placed (second click / touch release) | the line's index in this attempt (1, 2, ...) | TASK-192 |
| `lines:<srcId>:delete` | a player line is deleted with the bin (after `ui:line_delete_bin`) | - | TASK-192 |
| `lines:<srcId>:drag` | a player line end is dragged and dropped | 1 = drop accepted, 0 = rejected (end put back) | TASK-192 |
| `lines:<srcId>:reject_limit` | a click / tap on the field while the level's `lineK` limit is reached | - | TASK-192 |
| `lines:<srcId>:used` | every run start (last line placed, play box run / resume) | player lines on the field | TASK-192 |
| `session:play_seconds` | active play time reaches a milestone | 30, 60, 120, 300, 600 (each once per session) | TASK-192 |
| `session:hide` | `visibilitychange` to hidden | - | TASK-192 |
| `session:levels_seen` | `pagehide` (before `flush` / `endSession`) | distinct srcIds with an attempt this session | TASK-192 |

Order on a restart: `restart`, then `Fail` (only for an unwon attempt), then `Start` + `attempt`.
Order on an off-map: `fail:offmap`, `Fail`, then `Start` + `attempt`.

## UI, line and session events (TASK-192)

`<ctx>` is the context segment of a button event: `L<srcId>` inside a level, `map` on the route map. Buttons are
sent outside the editor and outside play-tests (the map counts even when it was opened from a play-test). Line
events are sent for real levels only. Nothing is sampled, rate-limited or deduplicated; touch taps and drags go
through the same handlers as mouse clicks (`handleClick`, `dragDrop`), so they send the same events.

Order of a pause menu button: the button (`resume`, `restart`, `map_open`, `editor_open`), then `menu_close`, then
the level events it causes (`restart` / `Fail` / `Start`, `abandon`). A level started from the map:
`map_level` or `preview_play`, `map_close`, then `Start` + `attempt`.

Active play (`session:play_seconds`) counts game-loop frame time (at most 1 s per frame) while a level is shown
without the map, the pause menu or the completion window, outside the editor and play-tests, in a visible page.

On `pagehide`: `abandon` / `Fail` for an unwon attempt, `session:levels_seen`, then `flush` and `endSession`.

## Per-user counters

`PLATFORM.storage` key `bp.stats.v1` (platform facade, never `localStorage` directly), read at boot with the
other keys (`getMany`) and passed to `TELEMETRY.load`:

```
{"<srcId>": {"attempts": n, "wins": n, "restarts": n, "offmap": n, "abandons": n, "seconds": s}}
```

`seconds` is the wall-clock time spent inside attempts (attempt start to end). Counters survive reloads; a
blocked storage keeps them in memory only.

## Checks

- `python3 tests/visual/shoot.py --task TASK-NNN --scenarios telemetry_levels`: none backend over a local http
  server, real input script; `ANALYTICS.debugLog` (level events) must equal
  `tests/visual/telemetry_expected_levels.json`; writes `sequence_levels.json` (TASK-191: `sequence.json`) and `counters.json` (`bp.stats.v1`
  after a reload).
- `python3 tests/visual/shoot.py --task TASK-NNN --scenarios telemetry_levels,telemetry_ui`: telemetry_ui plays every
  button, line and session event (one touch tap on the HUD menu icon; play-time milestones driven with
  `TELEMETRY.tick`); the ui:/lines:/session: events must equal `tests/visual/telemetry_expected_ui.json` in order
  (`sequence.json`). With telemetry_levels in the same run it writes `coverage.json`: every first-cell event id of the
  catalogue above (progression status, facade function, or design id with `<srcId>` / `<ctx>` as patterns) found in
  the two full debug logs; `uncovered` must be `[]`.
- `python3 tests/platform/test_analytics.py`: facade boot with both backends (TASK-190).
