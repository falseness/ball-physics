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
| `ui:menu_open:<ctx>` | the HUD menu icon opens the pause menu (buttons top to bottom: resume / restart / editor / Levels, TASK-255) | - | TASK-192 |
| `ui:menu_close:<ctx>` | the pause menu closes by any of its buttons, right after that button's event | - | TASK-192 |
| `ui:resume:<ctx>` | pause menu 'resume' | - | TASK-192 |
| `ui:map_open:<ctx>` | pause menu or completion window 'Levels' opens the route map (TASK-255: the completion window has no `menu_close`; TASK-256: after a win it sends no `abandon`, the won attempt is already closed; a play-test's completion window sends no `ui:` event) | - | TASK-192 |
| `ui:map_close:<ctx>` | the map closes: its menu icon (back to the pause menu) or a level starts from it | - | TASK-192 |
| `ui:map_level:<ctx>` | a click / tap on a level slot on the map (selects it, or starts the selected one) | srcId of that level | TASK-192 |
| `ui:preview_play:<ctx>` | the preview card's play button | srcId of that level | TASK-192 |
| `ui:next_level:<ctx>` | completion window 'next level' (buttons top to bottom: next level / restart / editor / Levels; no 'next level' on the last level or in a play-test, TASK-255) | - | TASK-192 |
| `ui:speed_on:<ctx>` | the HUD speed box switches to 3x | - | TASK-192 |
| `ui:speed_off:<ctx>` | the HUD speed box switches back to 1x | - | TASK-192 |
| `ui:editor_open:<ctx>` | the editor button, under 'restart' (pause menu or completion window; the small logo-frame editor button is gone, TASK-255; not in play-tests) | - | TASK-192 |
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
| `editor:line:<ctx>:<add\|cancel>` | line tool: `add` = the second click appended a line, `cancel` = the second click hit the pending point | `add`: level lines after it | TASK-234 |
| `editor:line_move:<ctx>:<ok\|refused>` | a dropped whole-line drag (select tool): `ok` = the line moved, `refused` = reverted with an error | - | TASK-234 |
| `editor:line_end:<ctx>:<ok\|refused\|degenerate>` | a dropped line-end drag: `ok` = the end moved, `refused` = reverted with an error, `degenerate` = reverted (< 1 px) | - | TASK-234 |
| `editor:line_del:<ctx>:<tool\|key>` | a line removed by the delete tool / by Delete or Backspace | - | TASK-234 |
| `editor:portal:<ctx>:<a\|b>` | portal tool: `a` = portal A placed (pending), `b` = the pair completed | - | TASK-234 |
| `editor:portal_move:<ctx>:<ok\|refused>` | a dropped portal drag: `ok` = it moved, `refused` = reverted (`portals overlap`) | - | TASK-234 |
| `editor:portal_del:<ctx>` | the delete tool removed the portal pair | - | TASK-234 |
| `editor:move:<ctx>:<ball\|flag>` | a dropped ball start / flag drag that moved it | - | TASK-234 |
| `editor:error:<ctx>:<code>` | once per `editorShowError` call (sent by it); `<code>` = the message slugged to `[a-z0-9_]` | - | TASK-234 |
| `edit:<h>:attempt` | play-test: an attempt starts (`play`, a restart, an off-map restart, a run after a win) | attempt number for this `<h>` in this session | TASK-235 |
| `edit:<h>:run` | play-test: the run starts (last line or the play box) | - | TASK-235 |
| `edit:<h>:restart` | play-test: a restart button (HUD box, pause menu, completion window), before the new `attempt` | - | TASK-235 |
| `edit:<h>:offmap` | play-test: the ball left the map (automatic restart), before the new `attempt` | - | TASK-235 |
| `edit:<h>:win` | play-test: the ball reached the flag (once per attempt) | seconds from the attempt's first run | TASK-235 |
| `edit:<h>:line_place` | play-test: a player line placed | the line's index in this attempt | TASK-235 |
| `edit:<h>:line_delete` | play-test: the bin removed a player line | - | TASK-235 |
| `edit:<h>:line_drag` | play-test: a player line end dropped | 1 = accepted, 0 = rejected | TASK-235 |
| `edit:<h>:<speed_on\|speed_off>` | play-test: the HUD speed box | - | TASK-235 |
| `edit:<h>:back` | play-test: back to the editor (HUD `edit` box, completion window `editor`, pause menu `editor`) | - | TASK-235 |

Order on a restart: `restart`, then `Fail` (only for an unwon attempt), then `Start` + `attempt`.
Order on an off-map: `fail:offmap`, `Fail`, then `Start` + `attempt`.

## UI, line and session events (TASK-192)

`<ctx>` is the context segment of a button event: `L<srcId>` inside a level, `map` on the route map. Buttons are
sent outside the editor and outside play-tests (the map counts even when it was opened from a play-test). Line
events are sent for real levels only. Nothing is sampled, rate-limited or deduplicated; touch taps and drags go
through the same handlers as mouse clicks (`handleClick`, `dragDrop`), so they send the same events.

Order of a pause menu button (menu order resume / restart / editor / Levels): the button (`resume`, `restart`, `editor_open`, `map_open`), then `menu_close`, then
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
or one object event (TASK-234 below). Play-test time is subtracted from the
`exit` / `abandon` seconds. Script and expected list: shoot.py `telemetry_editor`, tests/visual/telemetry_expected_editor.json.

TASK-233: every toolbar event above (`tool`, `snap`, `rotate`, `portal_size`, `linek`, `btn`, `import`, `bar_move`)
is one editor action (it replaces the plain button-click count of TASK-232; an `import` thus counts `btn` and the
outcome). They are sent from `editorClick` / `editorMouseUp` / `editorImportText`, which mouse and touch input share.

TASK-234: object events (`line`, `line_move`, `line_end`, `line_del`, `portal`, `portal_move`, `portal_del`, `move`) are
sent from `editorLineClick`, `editorPortalClick`, `editorDeleteAt`, `editorMouseUp` (mouse and touch) and `editorKeyDown`
(`TELEMETRY.editorEdit`). Each one is one editor action, also `cancel`, `refused` and `degenerate`; they replace the
TASK-232 "changed the working copy" edit count. A press that only selects (no change) and the first click of a line
send nothing. `editor:error:<ctx>:<code>` is sent by `editorShowError` itself (codes: `portals_overlap`,
`portals_go_on_lines`, `portal_does_not_fit`, `line_would_leave_the_field`, `line_too_short_for_its_portal`,
`invalid_level_file`, `old_portal_format`) and is not an action; it comes before the refused event of the same drop
(`error`, then `line_end:...:refused`) and after `import:...:<invalid|old_format>`.

TASK-235: play-test events `edit:<h>:<name>` go through `TELEMETRY.playtest(name, value)` and are sent only while the
play-test started by the editor's `play` runs (`playtestLevel` is that copy, editor closed). `<h>` is
`levelHash(playtestLevel)` taken at `play`, so it equals the `editor:sum:<ctx>:<h>` hash sent right before. The play-test
sends no `level:`, `lines:` or `ui:` events (the route map, opened from a play-test, still sends `ui:`) and never touches
`bp.stats.v1`. Order at `play`: `editor:btn:...:play`, the four `editor:sum` rows, `edit:<h>:attempt`. Order on a
restart / off-map: `restart` / `offmap`, then `attempt`. `back` comes before the editor is on again.

Order at `exit`: `btn:...:exit`, `sum:...:lines`, `portals`, `linek`, `changed`, `actions`, `exit`. Order on `pagehide` with the editor open:
`editor:actions`, `editor:abandon`, then the level / session events below.

On `pagehide`: `abandon` / `Fail` for an unwon attempt, `session:levels_seen`, then `flush` and `endSession`.

## First 30 seconds (TASK-238..241)

Why players leave at the start. **t0** = the rAF time of the first `gameLoop` frame after `bootComplete`
(`TELEMETRY.firstFrame`, `index.html` `boot()`). The **window** is t0..t0+30 s. `load:` / `ctx:` rows are sent once per
page load at t0; `f30:` rows only inside the window (plus one `leave` when the page hides or closes inside it). Times are
integer ms (load stages: since navigation start; `f30:` values: since t0). `<k>` = `new` for a visitor's first-ever session
(no `bp.first.v1` at boot; the key is read and written only through `PLATFORM.storage`, written after t0) or `ret`.
Ids follow the GameAnalytics design-id form (at most 5 parts, `[A-Za-z0-9_.-]`, 64 chars each, numeric values). Nothing
is sampled, throttled or coalesced; touch input goes through the same listeners as the mouse. Scripts and expected
values: shoot.py `telemetry_first30` (visitors A-E under a paused `page.clock`), `tests/visual/telemetry_expected_first30.json`.

| event id | when | value | ticket |
|----------|------|-------|--------|
| `load:html` | t0, once per page load | ms since navigation start: `responseEnd` of the navigation entry; -1 = not measurable | TASK-238 |
| `load:dom` | t0, once per page load | ms since navigation start: `domContentLoadedEventEnd`; -1 = not measurable | TASK-238 |
| `load:onload` | t0, once per page load | ms since navigation start: `loadEventEnd`; -1 when the load event has not ended yet; -1 = not measurable | TASK-238 |
| `load:boot` | t0, once per page load | ms since navigation start: `boot()` entry (`TELEMETRY.loadMark`); -1 = not measurable | TASK-238 |
| `load:platform` | t0, once per page load | ms since navigation start: after `PLATFORM.init`; -1 = not measurable | TASK-238 |
| `load:storage` | t0, once per page load | ms since navigation start: after the storage `getMany`; -1 = not measurable | TASK-238 |
| `load:fonts` | t0, once per page load | ms since navigation start: after `fontsReady`; -1 = not measurable | TASK-238 |
| `load:first_frame` | t0, once per page load | ms since navigation start: t0 itself; -1 = not measurable | TASK-238 |
| `load:transfer_kb` | t0, after the stages | navigation + resource `transferSize` / 1024, rounded | TASK-238 |
| `load:resources` | t0 | resource entries loaded so far | TASK-238 |
| `load:nav:<navigate\|reload\|back_forward\|prerender>` | t0 | - | TASK-238 |
| `ctx:input:<touch\|mouse>` | t0; `touch` = `(pointer: coarse)` | - | TASK-238 |
| `ctx:embed:<top\|iframe>` | t0 | - | TASK-238 |
| `ctx:platform:<platformId>` | t0; `PLATFORM.platformId` (`local` without one) | - | TASK-238 |
| `ctx:vw:<lt480\|lt768\|lt1024\|lt1440\|ge1440>` | t0; `innerWidth` bucket | - | TASK-238 |
| `ctx:visitor:<new\|ret>` | t0; `<k>` of this page load | - | TASK-238 |
| `f30:<k>:first_move` | funnel step 1 (pointer): the first `mousemove` / `touchmove`; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:first_press` | funnel step 2 (pointer): the first `mousedown` / `touchstart` anywhere on the page; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:point1` | funnel step 3 (line): a line's first point (`handleClick`'s new `Line`, `startLineAtEnd`, a touch drag start); once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:point2` | funnel step 4 (line): a player line placed (`TELEMETRY.linePlaced`); once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:line_drag` | funnel step 5 (line): a player line end dropped (accepted or not); once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:line_delete` | funnel step 6 (line): a player line deleted with the bin; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:reject_limit` | funnel step 7 (line): a press on the field with the `lineK` limit reached; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:run` | funnel step 8 (play): a run starts (auto-run after the last line, or the play box); once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:pause` | funnel step 9 (play): the HUD play box pauses the run; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:offmap` | funnel step 10 (play): the ball left the map; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:restart` | funnel step 11 (play): a restart button; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:win` | funnel step 12 (play): the ball reached the flag; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:menu_open` | funnel step 13 (navigation): the HUD menu icon opens the pause menu; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:map_open` | funnel step 14 (navigation): the route map opens; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:level_change` | funnel step 15 (navigation): a level started from the map or by 'next level'; once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:hidden` | funnel step 16 (tab): `visibilitychange` to hidden (after `leave`); once, first time inside the window | ms since t0 | TASK-239 |
| `f30:<k>:end` | t0+30 s, if the page is still open (no `pagehide` before) | furthest funnel index reached (0 = none) | TASK-239 |
| `f30:<k>:leave` | `visibilitychange` hidden or `pagehide` inside the window, once | ms since t0 | TASK-239 |
| `f30:<k>:leave_step:<step>` | right after `leave` (then `ANALYTICS.flush`) | - (`<step>` = last step sent before, or `none`) | TASK-239 |
| `f30:press:<target>:<gx>_<gy>` | every `mousedown` / `touchstart` inside the window | ms since t0 | TASK-240 |
| `f30:hb:<s>:moved` | heartbeat at `<s>` = 5, 10, 15, 20, 25, 30 s after t0 while the page is open | pointer path in logical px since the previous beat | TASK-240 |
| `f30:hb:<s>:idle` | same beat, after `moved` | ms since the last pointer / key input (or t0) at the nominal beat time | TASK-240 |
| `f30:hb:<s>:visible` | same beat | 1 = visible, 0 = hidden | TASK-240 |
| `f30:hb:<s>:step` | same beat | furthest funnel index so far | TASK-240 |

Funnel indexes (`end` / `hb:<s>:step` values; index = position in `F30_STEPS` + 1):

| index | step | group |
|---|---|---|
| 1 | first_move | pointer |
| 2 | first_press | pointer |
| 3 | point1 | line |
| 4 | point2 | line |
| 5 | line_drag | line |
| 6 | line_delete | line |
| 7 | reject_limit | line |
| 8 | run | play |
| 9 | pause | play |
| 10 | offmap | play |
| 11 | restart | play |
| 12 | win | play |
| 13 | menu_open | navigation |
| 14 | map_open | navigation |
| 15 | level_change | navigation |
| 16 | hidden | tab |

Press targets (`<target>`, `index.html` `f30PressTarget`, decided in the capture phase before any game handler, in
`handleClick`'s priority): `map` (route map open), `other` (editor, completion window, play-test edit box, outside the
field / letterbox), `menu` (pause menu open), `hud_menu`, `hud_play`, `hud_restart`, `hud_speed`, `bin`, `line_end`,
`line`, `ball`, `flag` (bounding box of the flag), `field` (anything else on the field). `<gx>_<gy>` = `floor(x / 40)` _
`floor(y / 40)` on the logical 1280x800 field, clamped to 0..31 / 0..19.

Order at t0: `load:html` .. `load:resources`, `load:nav`, `ctx:input`, `embed`, `platform`, `vw`, `visitor`. A press: `f30:press`
first (capture phase), then the steps it causes (`first_press`, `point1`, ...). Hide inside the window: `leave`,
`leave_step`, `hidden`. A beat at 30 s comes before `end`.

Checks: `shoot.py --scenarios telemetry_first30` (TASK-238..240: load/ctx sequence, visitors A-E exact ids and values,
`funnel.json`, `window.json`, `targets.json`, `heartbeat.json`). Since TASK-241 the scenario's log (both loads of the
first part + every visitor's debug log) covers every `load:` / `ctx:` / `f30:` row above (`sequence_first30.json`
`coverage`), and with `telemetry_levels,telemetry_ui,telemetry_editor` in the same run it rewrites `coverage.json` over
every catalogue row against the four logs (`scope`: `all rows, levels+ui+editor+first30 logs`). Without the first30
scenario the other three keep their old scopes (first-30 rows left out).

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
- `python3 tests/visual/shoot.py --task TASK-NNN --scenarios telemetry_levels,telemetry_ui,telemetry_editor` (TASK-236):
  telemetry_editor rewrites `coverage.json` over every catalogue row, `editor:` / `edit:` included (`<h>`, `<from>`,
  `<code>` and `<a\|b>` alternatives as patterns), against all three full debug logs (`scope`: `all rows,
  levels+ui+editor logs`); `uncovered` must be `[]`.
- `python3 tests/platform/test_analytics.py`: facade boot with both backends (TASK-190).
- `python3 tests/platform/live_check.py --out DIR` (TASK-193): live delivery through the relay. Plays the
  telemetry_ui script with the committed gameanalytics backend and build `test-live-<YYYYMMDD>` (buildinfo stamped
  `live-<day>`; a preview should pass `--build livepre-<day>` so it stays out of that count), waits 9 s at two
  menu-open steps so the SDK's 8 s timer sends several batches, then reads the tap's raw copy
  `/var/lib/ga-tap/events-<game key>-<UTC day>.jsonl` (lines whose path holds the game key and whose body build matches). The
  design + progression events there must equal the ones in `ANALYTICS.debugLog` (count, ids, unique uuids), every
  relay answer 200/201, every tap line `test: true`. Writes `live.json` and `live_excerpt.jsonl` (5 lines as
  recorded, user ids kept). Sends real events: run it once per day per build name.
  `--scenario telemetry_editor` (TASK-237) plays the telemetry_editor script instead (9 s waits at `export`,
  `import x3`, `portals`, editor open) and adds `live.json` `editor`: the `editor:`/`edit:` design ids sent vs the ones
  counted in the tap file (checks `editorSent`, `editorTapEqualsSent`).
  `--scenario telemetry_first30` (TASK-242) plays a real-clock first-30 session (the SDK's send timer needs real time,
  so not shoot's page.clock script): visitor 1 (new) moves, presses the ball, places a line by mouse, taps the field by
  touch and stays past t0 + 30 s (heartbeats + `end`), then pagehide; visitor 2 (ret: visitor 1's localStorage copied
  to its origin) presses once and leaves at ~4 s. Writes `sequence_first30_live.json` and `live.json` `first30`: the
  `load:`/`ctx:`/`f30:` design ids sent vs the ones counted in the tap file, ids and counts only (checks
  `first30Sent`, `first30TapEqualsSent`). The regression runs the page.clock scenario in shard 3 (preview and full);
  seq_check.py compares its `sequence_first30.json` with `telemetry_expected_first30.json`.
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
- `editor` (TASK-236), from the `editor:` / `edit:` rows of the catalogue (`<ctx>` = `L<srcId>` the editor was opened on,
  `<h>` = 8-hex FNV-1a of `editorLevelToJSON`, see "Editor events"):
  - `editor.users[<user>]` (users with any editor / play-test event): editor sessions (`open`) by source (`menu` / `win`),
    exits, abandons, seconds in the editor (sum of `exit` + `abandon` values, play-test time already excluded),
    actions (counted: every editor event except `open`, `sum`, `actions`, `exit`, `abandon`, `error`) and
    `actions_reported` (sum of the `editor:actions` values; the two agree for complete sessions), event counts by name
    (second id part), tool switches by tool, `snap` on/off, `rotate` by `<dir>:<target>`, `portal_size` bigger /
    smaller / refused (value 0), `linek` inc/dec, action buttons, imports by outcome (`ok` / `invalid` / `old_format`),
    exports (`btn:export`), toolbar moves, lines added / cancelled / moved / move refused / ends moved / end refused /
    end degenerate / deleted (tool, key), portals A placed / pairs placed / moved / move refused / deleted, ball and flag
    moves, errors by `<code>`, `hashes_summarised` (distinct `<h>` with a `sum`), and per `<h>`: the base levels, number
    of summaries, the latest `lines` / `portals` / `linek` / `changed` values, and the play-test (`edit:<h>:...`)
    attempts, highest attempt number, runs, wins, win seconds, restarts, off-map fails, lines placed / deleted /
    dragged / drag rejected, speed on / off, backs; `playtest` = totals over the hashes;
  - `editor.levels[<ctx>]`: editor opens by source, distinct users, exits, abandons.
  An `editor:` / `edit:` id that does not fit the catalogue (unknown name, wrong part, non-hex hash) goes to
  `unknown_events`. Error codes: `portals_overlap`, `portals_go_on_lines`, `portal_does_not_fit`,
  `line_would_leave_the_field`, `line_too_short_for_its_portal`, `invalid_level_file`, `old_portal_format` (any other
  `[a-z0-9_]` code is counted as is).

- `first30` (TASK-241), from the `load:` / `ctx:` / `f30:` rows ("First 30 seconds" above), per GA session (one page
  load), split `kinds.new` / `kinds.ret` (by `ctx:visitor`, else the `<k>` of the `f30:` ids) / `kinds.all`; sessions =
  sessions with any of these rows:
  - `load[<stage>]` for `html`, `dom`, `onload`, `boot`, `platform`, `storage`, `fonts`, `first_frame`, `transfer_kb`,
    `resources`: count, `missing` (value -1, left out), median, p75, p90 (nearest rank: the value at rank ceil(q * n));
    `context`: counts of `nav`, `input`, `embed`, `platform`, `vw`, `visitor`;
  - `funnel`: for each step in funnel order (index 1..16): sessions that reached it, `pct` of the sessions with
    `load:first_frame`, `conversion` = sessions at this step / sessions at the previous step (the first step: / first-frame
    sessions; `null` when the previous step has 0; steps are not nested, so it can exceed 1), `median_ms` since t0. The
    `point1` row = sessions that placed the first point of a line, `point2` = sessions that placed a whole line.
    `end`: sessions still open at 30 s and their furthest index;
  - `leaves`: count, by `leave_step`, by 5 s bucket of the `leave` value (`0_5` .. `25_30`);
  - `presses`: total, by target, the top 20 `<gx>_<gy>` cells per target (count desc, then cell), and `field`: field
    presses, those made before the session's `point1` (or with no `point1`), and of those the ones not followed by
    `point1` within 2 s (`no_point1_2s`: presses on the field that did not start a line);
  - `heartbeat[<s>]`: sessions with that beat, median `moved` and `idle`, sessions idle more than 10 s (`idle` > 10000)
    and their share, sessions with `visible` 0.
  Medians are ints when whole. A `load:` / `ctx:` / `f30:` id that does not fit the rows (unknown step or target,
  non-numeric value) goes to `unknown_events`. Markdown: `## First 30 seconds`, one subsection per kind.

Check: `python3 tools/stats_report.py --root tests/stats/fixture --out DIR && python3 tests/stats/check_fixture.py
DIR/report.json` (fixture written by `tests/stats/make_fixture.py`, expected report hand-written in
`tests/stats/fixture_expected.json`; since TASK-236 the fixture has editor and play-test events for user-a and user-b
and one malformed `edit:` id; since TASK-241 five first-30 sessions of users d, e, f (new + ret) and h: one win, two
leaves, one malformed `f30:` id).

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
