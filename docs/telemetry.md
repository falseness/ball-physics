# Telemetry

Game telemetry goes through the ANALYTICS facade (`analytics.js`, ported from grapnelninja in TASK-190;
backends in `analytics/backends/`). Game code never calls the backend directly. Level telemetry lives in
`js/telemetry.js` (`TELEMETRY`, TASK-191; UI, line and session events TASK-192). Builds from automated browsers start with `test-` (see
`analyticsBuild()` in `index.html`) so reports can leave them out.

## Where the data goes

```
game (TELEMETRY -> ANALYTICS facade -> gameanalytics backend + GA SDK v5.0.0)
  -> relay https://stats.playdiplomacy.online  (first-party host, so ad blockers do not drop it)
       -> tap ga_tap.py -> GameAnalytics api.gameanalytics.com -> game "ball-physics" (dashboards)
                        -> raw copy of every request body, user id kept, one file per game key and UTC day
            /var/lib/ga-tap/events-<game key>-<YYYY-MM-DD>.jsonl
```

- **GameAnalytics game**: "ball-physics". Its keys are `GA_KEYS` in `analytics/backends/gameanalytics.js` (copy in
  `/root/credentials/ball-physics/gameanalytics.json`). `GA_COLLECTOR_HOST` points the SDK at the relay; the browser
  never talks to `gameanalytics.com`.
- **Relay**: Caddy on `stats.playdiplomacy.online` (`/etc/caddy/Caddyfile`) reverse-proxies to the tap
  (`/usr/local/bin/ga_tap.py`, systemd unit `ga-tap`, 127.0.0.1:8790), which saves each request and forwards it
  unchanged to `https://api.gameanalytics.com` (`/v2/<key>/init`, `/v2/<key>/events`). The relay is shared with
  grapnelninja; the per-key files keep the two games apart.
- **Raw files**: `/var/lib/ga-tap/events-<game key>-<day>.jsonl` (since TASK-194, 2026-11-24 03:11 UTC). Older days
  are in the combined `events-<day>.jsonl` (all games; the request path holds the key). Requests without a key go to
  `events-unknown-<day>.jsonl`. Each line is one request record (`ts`, `test`, `ip`, `ua`, `path`, `status`, `body`: GA event list with
  `user_id`, `session_id`, `build`, `event_id`, `value`, `event_uuid`). This is the source of `tools/stats_report.py`;
  GameAnalytics keeps aggregated dashboards only.
- **Backend `none`** (`analytics/backends/none.js`): sends nothing, only fills `ANALYTICS.debugLog`. Used by the
  `telemetry_levels` / `telemetry_ui` shoot scenarios and `tests/platform/test_analytics.py --backend none`; the
  other regression scenarios load the `gameanalytics` backend (see "Regression (TASK-196)" below).

## Test builds

The GA build name is `<build id>` from `js/buildinfo.js` (`BUILD_CONFIG.build`). The repo keeps it empty: a page
served straight from the repo reports `dev-<YYYYMMDD>`; a release copy is stamped with
`python3 tools/stamp_build.py --root DIR` -> `<git short sha>-<YYYYMMDD>` (with a portal source:
`<portal>-<build id>`). Any automated browser (`navigator.webdriver`, i.e. playwright: shoot.py, sim.py, the
platform checks) or a page opened with `?gaTest=1` gets the prefix `test-` (`test-dev-20261124`,
`test-live-20261124`). The backend adds the prefix itself, so `BUILD_CONFIG.build` must never carry it. Test
records are also flagged `test: true` by the tap. `tools/stats_report.py` drops both unless `--include-test`;
in GameAnalytics filter out builds starting with `test-`. Live checks use a new build name per run
(`--build <name>-<day>`) so their counts are not mixed with an earlier run.

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
`abandon`. Play-tests and the editor send no level events and count nothing (editor events: TASK-232 section below).

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
| `editor:open:<ctx>:<from>` | the editor opens; `<from>` = `menu` (pause menu button) or `win` (completion window button) | - | TASK-232 |
| `editor:sum:<ctx>:<h>:lines` | level summary at `play`, `export` and `exit`, before the action | level lines | TASK-232 |
| `editor:sum:<ctx>:<h>:portals` | same moment, after `lines` | portals (0 or 2) | TASK-232 |
| `editor:sum:<ctx>:<h>:linek` | same moment, after `portals` | `lineK` | TASK-232 |
| `editor:sum:<ctx>:<h>:changed` | same moment, after `linek` | 1 = `editorLevelToJSON` differs from the copy taken at open, 0 = same | TASK-232 |
| `editor:actions:<ctx>` | right before `editor:exit` / `editor:abandon` | toolbar button clicks + object edits this editor session | TASK-232 |
| `editor:exit:<ctx>` | toolbar `exit` (after the summary and `actions`) | seconds in the editor since open, play-test time excluded | TASK-232 |
| `editor:abandon:<ctx>` | `pagehide` while the editor is open (not during a play-test), after `actions` | seconds, as `exit` | TASK-232 |
| `editor:tool:<ctx>:<select\|line\|portal\|delete>` | a tool button | - | TASK-233 |
| `editor:snap:<ctx>:<on\|off>` | the `snap` toggle (state after the click) | - | TASK-233 |
| `editor:rotate:<ctx>:<cw\|ccw>:<flag\|portal\|line>` | ⟳ / ⟲; the last part is what the button rotated (selected portal, selected line, else the flag) | - | TASK-233 |
| `editor:portal_size:<ctx>:<bigger\|smaller>` | `size +` / `size −` | new opening h; 0 = refused or no change (no portal selected, limit, does not fit) | TASK-233 |
| `editor:linek:<ctx>:<inc\|dec>` | `lines +` / `lines −` | `lineK` after the click (also when clamped at 0 / 5) | TASK-233 |
| `editor:btn:<ctx>:<new\|play\|export\|import\|exit>` | an action button, before its action (so before the `sum` rows of `play` / `export` / `exit`) | - | TASK-233 |
| `editor:import:<ctx>:<ok\|invalid\|old_format>` | `editorImportText` finished (after the picked file was read) | - | TASK-233 |
| `editor:bar_move:<ctx>` | a toolbar drag that moved the panel (mouseup / touchend) | - | TASK-233 |

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

## Editor events (TASK-232)

`<ctx>` of an editor event is `L<srcId>` of the level the editor was opened on (kept for the whole editor session,
also after `new` / `import`). `<h>` = `TELEMETRY.levelHash(W)`: 8-hex FNV-1a (32 bit) of `editorLevelToJSON(W)` of
the working copy (at `play`: the copy that gets play-tested, which has the same JSON). Editor events go through
`TELEMETRY.editor(name, value)` and are sent only while `TELEMETRY.editorActive()` (editor on, no play-test).
An editor action is one toolbar button click (tool, `snap`, every action button including `play`, `export` and `exit`)
or one object edit: a field click (line / portal / delete tool), a dropped drag or the Delete key that changed
`editorLevelToJSON` of the working copy. Refused or no-op edits do not count. Play-test time is subtracted from the
`exit` / `abandon` seconds. Script and expected list: shoot.py `telemetry_editor`, tests/visual/telemetry_expected_editor.json.

TASK-233: every toolbar event above (`tool`, `snap`, `rotate`, `portal_size`, `linek`, `btn`, `import`, `bar_move`)
is one editor action (it replaces the plain button-click count of TASK-232; an `import` thus counts `btn` and the
outcome). They are sent from `editorClick` / `editorMouseUp` / `editorImportText`, which mouse and touch input share.

Order at `exit`: `btn:...:exit`, `sum:...:lines`, `portals`, `linek`, `changed`, `actions`, `exit`. Order on `pagehide` with the editor open:
`editor:actions`, `editor:abandon`, then the level / session events below.

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
- `python3 tests/platform/live_check.py --out DIR` (TASK-193): live delivery through the relay. Plays the
  telemetry_ui script with the committed gameanalytics backend and build `test-live-<YYYYMMDD>` (buildinfo stamped
  `live-<day>`; a preview should pass `--build livepre-<day>` so it stays out of that count), waits 9 s at two
  menu-open steps so the SDK's 8 s timer sends several batches, then reads the tap's raw copy
  `/var/lib/ga-tap/events-<game key>-<UTC day>.jsonl` (lines whose path holds the game key and whose body build matches). The
  design + progression events there must equal the ones in `ANALYTICS.debugLog` (count, ids, unique uuids), every
  relay answer 200/201, every tap line `test: true`. Writes `live.json` and `live_excerpt.jsonl` (5 lines as
  recorded, user ids kept). Sends real events: run it once per day per build name.
- `python3 tests/platform/tap_split_check.py --out FILE` (TASK-194, on the relay host): the tap (`/usr/local/bin/ga_tap.py`)
  writes one file per game key, `events-<key>-<UTC day>.jsonl` (key from `/v2/<key>/...` or `?game_key=`; none ->
  `events-unknown-<day>.jsonl`); the old combined `events-<day>.jsonl` files are no longer written. Sends one signed
  init (build `test-split`) per game (ball-physics, grapnelninja) and checks each lands only in its own file.
  Rollback: `cp -p /usr/local/bin/ga_tap.py.bak-before-split-20261124 /usr/local/bin/ga_tap.py; systemctl restart ga-tap`.

## Stats report (TASK-195)

`python3 tools/stats_report.py [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--include-test] [--out DIR] [--root DIR]`
reads the tap's raw copy (on the relay host): every `events-<ball-physics key>-<day>.jsonl` plus the older combined
`events-<day>.jsonl` files (lines whose request path holds the key), found by glob in `--root` (default
`/var/lib/ga-tap`); `--since` / `--until` filter on the file day. Test traffic (record `test` flag or an event
build starting with `test-`) is left out unless `--include-test`. Events are de-duplicated by `event_uuid`. Lines
that are not tap records, or carry a body that is not a GA body, are counted as `unparsed` and listed `file:line`;
bodiless GET / OPTIONS records are counted as `no_body_records`; design ids not in the catalogue go to
`unknown_events`.

Writes `DIR/report.json` and `DIR/report.md`:
- per user (GA `user_id`): first/last seen, builds, inits, sessions (id, build, events, play-time milestone,
  `session_end` length), levels tried, per level attempts / highest attempt number / wins / first-win attempt /
  win seconds / restarts / abandons / off-map / progression Start-Complete-Fail / lines placed, deleted, dragged,
  drag rejected, over the limit, runs, max lines used; button counts by name (and by `<ctx>`), play seconds (sum of
  the highest `session:play_seconds` milestone per session), hides, totals;
- per level: users tried / won, attempts, wins, win rate (wins / attempts), median attempt number of the first win.

Check: `python3 tools/stats_report.py --root tests/stats/fixture --out DIR && python3 tests/stats/check_fixture.py
DIR/report.json` (fixture written by `tests/stats/make_fixture.py`, expected report hand-written in
`tests/stats/fixture_expected.json`).

Typical use on the relay host: `python3 tools/stats_report.py --since 2026-11-25 --out /tmp/bp-stats` and read
`report.md` (per user: levels tried, attempts, wins, restarts, buttons, lines, play time; per level totals).

## Regression (TASK-196)

The telemetry rows of the full regression: `shoot.py` (all scenarios, includes `telemetry_levels` and
`telemetry_ui`, whose debug logs must equal `tests/visual/telemetry_expected_levels.json` /
`telemetry_expected_ui.json`, and `coverage.json` `uncovered: []`), `tests/platform/test_backends.py`
(`pageErrors=0` on all five platform backends) and the stats fixture check above. The two telemetry scenarios use
the `none` backend; the other shoot / sim scenarios load the committed `gameanalytics` backend and send `test-`
builds to the relay (left out of reports). `test_analytics.py`, `live_check.py` and `tap_split_check.py` send
real requests to the relay and are run on purpose, not in every regression.
