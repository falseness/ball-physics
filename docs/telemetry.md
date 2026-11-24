# Telemetry

Game telemetry goes through the ANALYTICS facade (`analytics.js`, ported from grapnelninja in TASK-190;
backends in `analytics/backends/`). Game code never calls the backend directly. Level telemetry lives in
`js/telemetry.js` (`TELEMETRY`, TASK-191). Builds from automated browsers start with `test-` (see
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

Order on a restart: `restart`, then `Fail` (only for an unwon attempt), then `Start` + `attempt`.
Order on an off-map: `fail:offmap`, `Fail`, then `Start` + `attempt`.

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
  `tests/visual/telemetry_expected_levels.json`; writes `sequence.json` and `counters.json` (`bp.stats.v1`
  after a reload).
- `python3 tests/platform/test_analytics.py`: facade boot with both backends (TASK-190).
