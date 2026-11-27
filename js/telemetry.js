'use strict'
// TASK-191: level telemetry (TELEMETRY) on top of the ANALYTICS facade (analytics.js). Catalogue: docs/telemetry.md.
//
// Attempts. Every level start is one attempt of that level (by srcId, never by play-order index):
//   boot      - the page opens the current level (index.html boot)
//   map       - a level picked on the route map (levelPick)
//   next      - 'next level' on the completion window
//   restart   - a restart button (HUD box, pause menu, completion window)
//   offmap    - the automatic restart after the ball left the map
//   resume    - the first run when no attempt is open (back from the editor, after the map was closed, bfcache)
// An attempt ends exactly once: win (Complete), off-map / restart / abandon (Fail), or silently (editor opened).
// Leaving an unwon attempt for the map (mapOpen), by 'next level' or by page hide sends 'abandon'.
//
// Events (srcId = levels[thisLevel].srcId):
//   ANALYTICS.progression('Start' | 'Complete' | 'Fail', 'L' + srcId)
//   design level:<srcId>:attempt      value = attempt number of this user for this level
//          level:<srcId>:win          value = seconds from the attempt's first run to the win
//          level:<srcId>:win_attempt  value = attempt number of the winning attempt
//          level:<srcId>:first_win    once per user (the first win in bp.stats.v1)
//          level:<srcId>:fail:offmap
//          level:<srcId>:restart      the player pressed a restart button
//          level:<srcId>:abandon      left an unwon attempt (map, next level, page hide)
//
// TASK-192: UI, line and session events (same facade, catalogue in docs/telemetry.md):
//   ui:<name>:<ctx>            a button; ctx = 'L<srcId>' inside a level, 'map' on the route map; value: see ui()
//   lines:<srcId>:place        value = the line's index in this attempt (1, 2, ...)
//   lines:<srcId>:delete       the bin removed a player line
//   lines:<srcId>:drag         a player line end was dragged and dropped; value 1 = accepted, 0 = rejected
//   lines:<srcId>:reject_limit a click on the field while the level's lineK limit is reached
//   lines:<srcId>:used         value = player lines on the field, on every run start (run / resume)
//   session:play_seconds       value = milestone (30, 60, 120, 300, 600) of active play time
//   session:hide               the page became hidden (visibilitychange)
//   session:levels_seen        value = distinct srcIds that had an attempt this session (on pagehide)
// Nothing is sampled or rate-limited; touch input goes through the same handlers as the mouse.
//
// TASK-232: editor session and level summary events (catalogue in docs/telemetry.md), sent through editor(name, value)
// only while editorActive() (editorMode on, no play-test). <ctx> = 'L<srcId>' of the level the editor was opened on,
// <h> = levelHash(working copy) (8-hex FNV-1a of editorLevelToJSON):
//   editor:open:<ctx>:<from>         from = 'menu' (pause menu) | 'win' (completion window) | 'map' (route map
//                                    'editor' button: blank level, <ctx> = 'new' for the whole session, TASK-258)
//   editor:sum:<ctx>:<h>:lines       value = level lines      } sent at play, export and exit,
//   editor:sum:<ctx>:<h>:portals     value = portals (0 | 2)  } before the action itself
//   editor:sum:<ctx>:<h>:linek       value = lineK            }
//   editor:sum:<ctx>:<h>:changed     value = 1 if editorLevelToJSON differs from the copy taken at open, else 0
//   editor:actions:<ctx>             value = toolbar button clicks + object edits this session (before exit / abandon)
//   editor:exit:<ctx>                value = seconds in the editor since open, play-test time excluded
//   editor:abandon:<ctx>             pagehide while the editor is open (not during a play-test), value = seconds
// TASK-233: toolbar events (editorToolbar; each counts as one action):
//   editor:tool:<ctx>:<select|line|portal|delete>, editor:snap:<ctx>:<on|off>,
//   editor:rotate:<ctx>:<cw|ccw>:<flag|portal|line>, editor:portal_size:<ctx>:<bigger|smaller> (value = new h, 0 = refused),
//   editor:linek:<ctx>:<inc|dec> (value = lineK after the click), editor:btn:<ctx>:<new|play|export|import|exit>,
//   editor:import:<ctx>:<ok|invalid|old_format> (editorImportText finished), editor:bar_move:<ctx> (toolbar dragged)
// TASK-234: object edits (editorEdit; each counts as one action) and errors (editorError; not an action):
//   editor:line:<ctx>:add (value = level lines after it) | editor:line:<ctx>:cancel (2nd click on the pending point),
//   editor:line_move:<ctx>:<ok|refused>, editor:line_end:<ctx>:<ok|refused|degenerate>, editor:line_del:<ctx>:<tool|key>,
//   editor:portal:<ctx>:<a|b> (A placed / pair completed), editor:portal_move:<ctx>:<ok|refused>, editor:portal_del:<ctx>,
//   editor:move:<ctx>:<ball|flag> (a drag moved it), editor:error:<ctx>:<code> (code = editorShowError text slugged)
// TASK-235: play-test events 'edit:<h>:<name>' (playtest(name, value)), only while a play-test runs (playtestLevel set,
// editor closed); <h> = levelHash of the play-tested copy (= the editor:sum hash sent at 'play'):
//   edit:<h>:attempt     value = attempt number for this h in this session (play start, restart, off-map)
//   edit:<h>:run | restart | offmap | line_delete | speed_on | speed_off
//   edit:<h>:win         value = seconds from the first run of the attempt
//   edit:<h>:line_place  value = the line's index in the attempt
//   edit:<h>:line_drag   value = 1 accepted / 0 rejected
//   edit:<h>:back        back to the editor (HUD 'edit' box, completion window 'editor', pause menu 'editor')
// Play-tests send no level:, lines: or ui: events and never touch bp.stats.v1.
// Per-user counters: PLATFORM.storage key STATS_STORE ('bp.stats.v1'), JSON
//   {[srcId]: {attempts, wins, restarts, offmap, abandons, seconds}}; seconds = time inside attempts (wall clock).
// Boot (index.html) reads the key with getMany and passes the values to TELEMETRY.load.
// Play-tests and the editor send and count nothing (active() is false there).
const STATS_STORE = 'bp.stats.v1'
// TASK-238: first-30-seconds telemetry, part 1: load timing and session context, sent once per page load at t0
// (the first gameLoop frame after bootComplete, TELEMETRY.firstFrame). Values = integer ms since navigation start
// (performance.timeOrigin; Navigation Timing Level 2 entry):
//   load:html (responseEnd), load:dom (domContentLoadedEventEnd), load:onload (loadEventEnd, -1 before the load event),
//   load:boot (boot() entry), load:platform (after PLATFORM.init), load:storage (after storage getMany),
//   load:fonts (after fontsReady), load:first_frame (t0)                         <- TELEMETRY.loadMark(stage) in boot()
//   load:transfer_kb (navigation + resource transferSize / 1024, rounded), load:resources (resource entry count),
//   load:nav:<navigate|reload|back_forward|prerender>
//   ctx:input:<touch|mouse> (pointer: coarse), ctx:embed:<top|iframe>, ctx:platform:<PLATFORM.platformId>,
//   ctx:vw:<lt480|lt768|lt1024|lt1440|ge1440> (innerWidth), ctx:visitor:<new|ret>
// Visitor: PLATFORM.storage key FIRST_STORE ('bp.first.v1') read by boot's getMany (TELEMETRY.load); missing = 'new'.
// It is written at t0 (after the window starts) with the time of the first session. A stage that cannot be measured
// (no navigation entry) sends -1. Entries come from performance.getEntriesByType, else from a buffered
// PerformanceObserver (some environments stub the performance object, e.g. test fake clocks).
const FIRST_STORE = 'bp.first.v1'
// TASK-239: first-30-seconds funnel. The window is t0..t0+30 s (F30_WINDOW_MS). Each step is sent once per page load,
// at its first occurrence inside the window, as 'f30:<k>:<step>' (value = integer ms since t0); <k> = 'new' for a
// visitor's first-ever session (no bp.first.v1 at boot), else 'ret'. Steps in funnel order (index = position + 1):
//   pointer:    first_move (mousemove / touchmove), first_press (mousedown / touchstart anywhere)
//   line:       point1 (a line's first point: handleClick's new Line, startLineAtEnd, a touch drag start),
//               point2 (the line placed, TELEMETRY.linePlaced), line_drag, line_delete, reject_limit
//   play:       run (TELEMETRY.run: the auto-run after the last line or the play box), pause, offmap, restart, win
//   navigation: menu_open, map_open, level_change (a level started from the map or by 'next level')
//   tab:        hidden (visibilitychange to hidden)
//   f30:<k>:end              at t0+30 s if the page is still open; value = furthest funnel index reached (0 = none)
//   f30:<k>:leave            pagehide / visibility hidden inside the window, once; value = ms since t0
//   f30:<k>:leave_step:<s>   with leave: the last step sent before it (or 'none'); then ANALYTICS.flush()
// Nothing is sampled or coalesced; an action after the window sends nothing.
const F30_STEPS = ['first_move', 'first_press', 'point1', 'point2', 'line_drag', 'line_delete', 'reject_limit',
    'run', 'pause', 'offmap', 'restart', 'win', 'menu_open', 'map_open', 'level_change', 'hidden']
const F30_WINDOW_MS = 30000
// TASK-240: presses and heartbeat inside the same window (nothing sampled, throttled or coalesced):
//   f30:press:<target>:<gx>_<gy>  every mousedown / touchstart; value = ms since t0; gx = floor(x / 40),
//                                 gy = floor(y / 40) on the logical 1280x800 field (clamped to the edge cell).
//                                 target (index.html f30PressTarget, decided before any game handler runs):
//                                 hud_play, hud_menu, hud_restart, hud_speed, bin, line_end, line, ball, flag,
//                                 field, menu (pause menu open), map (route map open), other (completion window,
//                                 editor, play-test edit box, outside the field)
//   f30:hb:<s>:moved | idle | visible | step   at s = 5, 10, 15, 20, 25, 30 s after t0 while the page is open
//                                 (not after a pagehide): moved = pointer path length in logical px since the
//                                 previous beat (rounded; a touchstart starts a new path, every other pointer event
//                                 adds its distance from the previous pointer position); idle = ms since the last
//                                 pointer or key input (or since t0) at the beat's nominal time; visible = 1 / 0;
//                                 step = furthest funnel index
const F30_CELL = 40
const F30_BEATS = [5, 10, 15, 20, 25, 30]
const TELEMETRY = (function()
{
    let stats = {}
    let attempt = null // {srcId, n, t0, runAt, won, ended, placed}
    const PLAY_MILESTONES = [30, 60, 120, 300, 600]
    let playMs = 0        // active play time this session (tick)
    let milestone = 0     // index of the next PLAY_MILESTONES entry
    const seen = new Set() // srcIds with an attempt this session

    function now()
    {
        return performance.now()
    }
    function secs(ms)
    {
        return Math.max(0.01, Math.round(ms / 10) / 100)
    }
    function active()
    {
        return typeof playtestLevel !== 'undefined' && !playtestLevel && !editorMode && levels[thisLevel] !== undefined
    }
    function srcId()
    {
        return levels[thisLevel].srcId
    }
    function entry(id)
    {
        let e = stats[id]
        if (!e || typeof e != 'object')
            e = stats[id] = {}
        for (const k of ['attempts', 'wins', 'restarts', 'offmap', 'abandons', 'seconds'])
            if (typeof e[k] != 'number' || !isFinite(e[k]))
                e[k] = 0
        return e
    }
    function save()
    {
        try
        {
            const p = PLATFORM.storage.setMany({ [STATS_STORE]: JSON.stringify(stats) })
            if (p && p.catch)
                p.catch(function() {})
        }
        catch (e) {} // blocked storage: counters stay in memory
    }
    function design(id, name, value)
    {
        ANALYTICS.design('level:' + id + ':' + name, value)
    }
    function open()
    {
        return attempt && !attempt.ended ? attempt : null
    }
    // end the open attempt: its time goes into seconds; status 'Fail' sends progression Fail, null sends nothing
    function end(status)
    {
        const a = open()
        if (!a)
            return null
        a.ended = true
        entry(a.srcId).seconds = Math.round((entry(a.srcId).seconds + (now() - a.t0) / 1000) * 100) / 100
        if (status)
            ANALYTICS.progression(status, 'L' + a.srcId)
        save()
        return a
    }
    // leave the open attempt without a win: 'abandon' + Fail; a won attempt just ends
    function leave()
    {
        const a = open()
        if (!a)
            return
        if (a.won)
            return void end(null)
        design(a.srcId, 'abandon')
        ++entry(a.srcId).abandons
        end('Fail')
    }
    function start(reason)
    {
        if (!active())
            return
        leave()
        const id = srcId(), e = entry(id)
        const n = ++e.attempts
        attempt = {srcId: id, n, t0: now(), runAt: null, won: false, ended: false, reason, placed: 0}
        seen.add(id)
        ANALYTICS.progression('Start', 'L' + id)
        design(id, 'attempt', n)
        save()
    }

    // a button outside the editor and outside play-tests (the route map counts even after a play-test)
    function uiActive()
    {
        return typeof editorMode !== 'undefined' && !editorMode && (drawMap || !playtestLevel) && levels[thisLevel] !== undefined
    }
    function ctxSegment()
    {
        return drawMap ? 'map' : 'L' + srcId()
    }
    function lineEvent(name, value)
    {
        if (active())
            ANALYTICS.design('lines:' + srcId() + ':' + name, value)
    }
    // active play: a level on screen (no map, menu, completion window, editor or play-test) in a visible page
    function playing()
    {
        return active() && !drawMap && !drawMenu && !levelCompletedWindow && !document.hidden
    }

    // TASK-232: editor session {ctx, t0, json0, actions, playAt, playMs}; null when the editor is closed
    let ed = null
    function editorActive()
    {
        return typeof editorMode !== 'undefined' && editorMode && !playtestLevel
    }
    function editorEvent(name, value)
    {
        if (editorActive())
            ANALYTICS.design('editor:' + name, value)
    }
    // TASK-234: error message -> GA-safe slug [a-z0-9_] ('portals overlap' -> 'portals_overlap'), at most 64 chars
    function editorErrorCode(text)
    {
        return (String(text).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'unknown').slice(0, 64)
    }
    // 8-hex FNV-1a (32 bit) of editorLevelToJSON(W)
    function levelHash(W)
    {
        const s = editorLevelToJSON(W)
        let h = 0x811c9dc5
        for (let i = 0; i < s.length; ++i)
            h = Math.imul(h ^ s.charCodeAt(i), 0x01000193)
        return (h >>> 0).toString(16).padStart(8, '0')
    }
    function editorSummary()
    {
        if (!ed || !editorActive())
            return
        const W = editor.level, h = levelHash(W), pre = 'sum:' + ed.ctx + ':' + h + ':'
        editorEvent(pre + 'lines', W.lines.length)
        editorEvent(pre + 'portals', W.portals.length)
        editorEvent(pre + 'linek', W.lineK)
        editorEvent(pre + 'changed', editorLevelToJSON(W) === ed.json0 ? 0 : 1)
    }
    function editorSeconds()
    {
        return secs(now() - ed.t0 - ed.playMs)
    }
    // the session ends: actions, then 'exit' / 'abandon' with the seconds
    function editorEnd(kind)
    {
        if (!ed || !editorActive())
            return
        editorEvent('actions:' + ed.ctx, ed.actions)
        editorEvent(kind + ':' + ed.ctx, editorSeconds())
        ed = null
    }

    // TASK-235: play-test session {h, level (the playtestLevel object), a: {n, runAt, placed, won}}; ptAttempts: h -> attempts this session
    let pt = null
    const ptAttempts = {}
    function ptActive()
    {
        return pt !== null && typeof playtestLevel !== 'undefined' && playtestLevel === pt.level && !editorMode
    }
    function ptEvent(name, value)
    {
        if (ptActive())
            ANALYTICS.design('edit:' + pt.h + ':' + name, value)
    }
    function ptAttempt()
    {
        const n = ptAttempts[pt.h] = (ptAttempts[pt.h] || 0) + 1
        pt.a = {n, runAt: null, placed: 0, won: false}
        ptEvent('attempt', n)
    }

    // TASK-238: load marks (performance.now() at each boot stage), observed entries, visitor kind, t0
    const loadMarks = {}
    const observed = {navigation: [], resource: []}
    let firstVisitor = null // 'new' | 'ret' once load() ran
    let t0 = null
    try
    {
        for (const type of ['navigation', 'resource'])
            new PerformanceObserver(function(list) { observed[type].push(...list.getEntries()) })
                .observe({type, buffered: true})
    }
    catch (e) {} // no PerformanceObserver: getEntriesByType only
    function perfEntries(type)
    {
        let a = []
        try
        {
            a = performance.getEntriesByType(type) || []
        }
        catch (e) {}
        return a.length ? a : observed[type]
    }
    function ms(v)
    {
        return typeof v == 'number' && isFinite(v) ? Math.max(0, Math.round(v)) : -1
    }
    function viewportBucket(w)
    {
        return w < 480 ? 'lt480' : w < 768 ? 'lt768' : w < 1024 ? 'lt1024' : w < 1440 ? 'lt1440' : 'ge1440'
    }
    function inIframe()
    {
        try
        {
            return window.self !== window.top
        }
        catch (e)
        {
            return true // a cross-origin top throws
        }
    }
    // TASK-239: first-30 funnel state (see F30_STEPS)
    const f30 = {sent: {}, last: 'none', furthest: 0, left: false, ended: false, closed: false}
    // TASK-240: pointer path since the previous beat, last pointer position, last input time (performance.now())
    const f30In = {moved: 0, at: null, inputAt: null, beats: []}
    function f30Kind()
    {
        return firstVisitor == 'ret' ? 'ret' : 'new'
    }
    function f30Since()
    {
        return t0 === null ? null : Math.round(performance.now() - t0)
    }
    function f30Open()
    {
        const t = f30Since()
        return t !== null && t <= F30_WINDOW_MS && !f30.ended && !f30.closed
    }
    function f30Step(step)
    {
        const i = F30_STEPS.indexOf(step)
        if (i < 0 || f30.sent[step] !== undefined || !f30Open())
            return
        const t = f30Since()
        f30.sent[step] = t
        f30.last = step
        f30.furthest = Math.max(f30.furthest, i + 1)
        ANALYTICS.design('f30:' + f30Kind() + ':' + step, t)
    }
    // leave + leave_step once (inside the window); flush is left to the caller
    function f30Leave()
    {
        if (f30.left || !f30Open())
            return false
        f30.left = true
        ANALYTICS.design('f30:' + f30Kind() + ':leave', f30Since())
        ANALYTICS.design('f30:' + f30Kind() + ':leave_step:' + f30.last)
        return true
    }
    function f30End()
    {
        if (f30.ended || f30.closed)
            return
        ANALYTICS.design('f30:' + f30Kind() + ':end', f30.furthest)
        f30.ended = true
    }
    // TASK-240: heartbeat s (seconds after t0); only while the page is open (no pagehide, before 'end')
    function f30Beat(s)
    {
        if (f30.closed || f30.ended || t0 === null)
            return
        // idle is measured at the beat's nominal time t0 + s (a timer can fire a few ms late; an input in that
        // gap counts as idle 0), so the value does not depend on timer latency
        const at = t0 + s * 1000
        const since = f30In.inputAt === null || f30In.inputAt < t0 ? t0 : f30In.inputAt
        const id = 'f30:hb:' + s + ':'
        ANALYTICS.design(id + 'moved', Math.round(f30In.moved))
        ANALYTICS.design(id + 'idle', Math.max(0, Math.round(at - since)))
        ANALYTICS.design(id + 'visible', document.visibilityState === 'hidden' ? 0 : 1)
        ANALYTICS.design(id + 'step', f30.furthest)
        f30In.moved = 0
        f30In.beats.push([s, performance.now() - at]) // [beat, timer latency ms] (f30State, test evidence)
    }
    function f30Cell(v, max)
    {
        const c = Math.floor((typeof v == 'number' && isFinite(v) ? v : 0) / F30_CELL)
        return Math.max(0, Math.min(Math.floor(max / F30_CELL) - 1, c))
    }
    function sendLoad()
    {
        const nav = perfEntries('navigation')[0] || null
        const res = perfEntries('resource')
        const stage = (name, v) => ANALYTICS.design('load:' + name, v)
        stage('html', nav ? ms(nav.responseEnd) : -1)
        stage('dom', nav && nav.domContentLoadedEventEnd > 0 ? ms(nav.domContentLoadedEventEnd) : -1)
        stage('onload', nav && nav.loadEventEnd > 0 ? ms(nav.loadEventEnd) : -1)
        for (const name of ['boot', 'platform', 'storage', 'fonts'])
            stage(name, name in loadMarks ? ms(loadMarks[name]) : -1)
        stage('first_frame', ms(t0))
        let bytes = nav && nav.transferSize || 0
        for (const r of res)
            bytes += r.transferSize || 0
        stage('transfer_kb', Math.round(bytes / 1024))
        stage('resources', res.length)
        const type = nav && ['navigate', 'reload', 'back_forward', 'prerender'].includes(nav.type) ? nav.type : 'navigate'
        ANALYTICS.design('load:nav:' + type)
        let coarse = false
        try
        {
            coarse = window.matchMedia('(pointer: coarse)').matches
        }
        catch (e) {}
        ANALYTICS.design('ctx:input:' + (coarse ? 'touch' : 'mouse'))
        ANALYTICS.design('ctx:embed:' + (inIframe() ? 'iframe' : 'top'))
        ANALYTICS.design('ctx:platform:' + (PLATFORM.platformId || 'local'))
        ANALYTICS.design('ctx:vw:' + viewportBucket(window.innerWidth))
        ANALYTICS.design('ctx:visitor:' + firstVisitor)
    }

    return {
        // TASK-238: boot stage reached (index.html boot: 'boot', 'platform', 'storage', 'fonts')
        loadMark(stage)
        {
            if (!(stage in loadMarks))
                loadMarks[stage] = performance.now()
        },
        // TASK-238: t0 = the first gameLoop frame after bootComplete; sends load:/ctx: once, then writes FIRST_STORE
        // TASK-240: t0 = the frame's rAF timestamp when it is a valid time not before the last boot mark, else
        // performance.now() (the timestamp does not depend on how late the callback runs, so test fake clocks give
        // frame-exact step times)
        firstFrame(frameTime)
        {
            if (t0 !== null)
                return
            const now = performance.now()
            const marks = Object.keys(loadMarks).map(k => loadMarks[k])
            t0 = typeof frameTime == 'number' && isFinite(frameTime) && frameTime <= now
                && frameTime >= Math.max(0, ...marks) ? frameTime : now
            if (firstVisitor === null)
                firstVisitor = 'new'
            sendLoad()
            f30In.moved = 0 // TASK-240: the first beat's path starts at t0
            for (const b of F30_BEATS)
                setTimeout(function() { f30Beat(b) }, b * 1000) // TASK-240: before 'end' at 30 s (same delay, earlier timer)
            setTimeout(f30End, F30_WINDOW_MS) // TASK-239: f30:<k>:end at t0+30 s
            if (firstVisitor == 'new')
            {
                try
                {
                    const p = PLATFORM.storage.setMany({ [FIRST_STORE]: JSON.stringify({first: Date.now()}) })
                    if (p && p.catch)
                        p.catch(function() {})
                }
                catch (e) {} // blocked storage: the next session is 'new' again
            }
        },
        // TASK-238: 'new' | 'ret' (null before boot read the storage); ms since t0 (null before t0)
        firstVisitor() { return firstVisitor },
        sinceT0() { return t0 === null ? null : Math.round(performance.now() - t0) },
        loadMarks() { return Object.assign({}, loadMarks) },
        // TASK-239: first-30 funnel step (F30_STEPS); sent once, only inside the window
        f30: f30Step,
        // visibilitychange to hidden: leave (+ leave_step), the 'hidden' step, then flush
        f30Hidden()
        {
            f30Leave()
            f30Step('hidden')
            ANALYTICS.flush()
        },
        // pagehide: leave (+ leave_step) inside the window; no 'end' after it (the caller flushes)
        f30PageHide()
        {
            f30Leave()
            f30.closed = true
        },
        f30State() { return JSON.parse(JSON.stringify(Object.assign({}, f30, {input: f30In, t0: t0}))) },
        // TASK-240: a mousedown / touchstart at logical (x, y) on target (index.html f30PressTarget)
        f30Press(target, x, y)
        {
            if (!f30Open())
                return
            ANALYTICS.design('f30:press:' + target + ':' + f30Cell(x, 1280) + '_' + f30Cell(y, 800), f30Since())
        },
        // TASK-240: a pointer event at logical (x, y); newPath (touchstart) starts a new path; key input passes no point
        f30Input(x, y, newPath)
        {
            f30In.inputAt = performance.now()
            if (x === undefined)
                return
            if (!newPath && f30In.at)
                f30In.moved += Math.hypot(x - f30In.at[0], y - f30In.at[1])
            f30In.at = [x, y]
        },
        editor: editorEvent,
        playtest: ptEvent,
        playtestActive: ptActive,
        // editorStartPlaytest, after playtestLevel is the clone and editorMode is off
        playtestStarted()
        {
            pt = {h: levelHash(playtestLevel), level: playtestLevel, a: null}
            if (ptActive())
                ptAttempt()
            else
                pt = null
        },
        // editorEndPlaytest, before playtestLevel is cleared
        playtestBack()
        {
            ptEvent('back')
            pt = null
        },
        editorActive,
        levelHash,
        editorSession() { return ed },
        // editorOpen (editor.level is the fresh copy, editorMode on); from = 'menu' | 'win' | 'map' (TASK-258: blank level, ctx 'new')
        editorOpened(from)
        {
            if (!editorActive())
                return
            ed = {ctx: from == 'map' ? 'new' : 'L' + srcId(), t0: now(), json0: editorLevelToJSON(editor.level), actions: 0, playAt: null, playMs: 0}
            editorEvent('open:' + ed.ctx + ':' + from)
        },
        // TASK-233: toolbar event 'editor:<kind>:<ctx>[:<rest>]' (tool, snap, rotate, portal_size, linek, btn, import,
        // bar_move); each one is one editor action
        editorToolbar(kind, rest, value)
        {
            if (!ed || !editorActive())
                return
            ++ed.actions
            editorEvent(kind + ':' + ed.ctx + (rest ? ':' + rest : ''), value)
        },
        // TASK-234: object edit event 'editor:<kind>:<ctx>[:<rest>]' (line, line_move, line_end, line_del, portal,
        // portal_move, portal_del, move); each one is one editor action (also cancel / refused / degenerate)
        editorEdit(kind, rest, value) { this.editorToolbar(kind, rest, value) },
        // TASK-234: 'editor:error:<ctx>:<code>' once per editorShowError (not an action); code = editorErrorCode(text)
        editorError(text)
        {
            if (ed && editorActive())
                editorEvent('error:' + ed.ctx + ':' + editorErrorCode(text))
        },
        editorErrorCode,
        // 'play' (before the play-test starts) / back from the play-test (after editorMode is on again)
        editorPlay()
        {
            editorSummary()
            if (ed && editorActive())
                ed.playAt = now()
        },
        editorBack()
        {
            if (ed && ed.playAt !== null && editorActive())
            {
                ed.playMs += now() - ed.playAt
                ed.playAt = null
            }
        },
        // 'export' (before the download)
        editorExport() { editorSummary() },
        // 'exit' (before the copy is written back): summary, actions, exit
        editorExit()
        {
            editorSummary()
            editorEnd('exit')
        },
        // pagehide with the editor open
        editorAbandon() { editorEnd('abandon') },
        // values: the PLATFORM.storage.getMany result ({key: string | null}); garbage means empty counters
        load(values)
        {
            firstVisitor = values && values[FIRST_STORE] != null ? 'ret' : 'new' // TASK-238
            stats = {}
            try
            {
                const v = JSON.parse(values && values[STATS_STORE])
                if (v && typeof v == 'object' && !Array.isArray(v))
                    stats = v
            }
            catch (e) { stats = {} }
        },
        stats() { return stats },
        attempt() { return attempt },
        // a level start (see the reasons above)
        levelStart(reason)
        {
            if (reason == 'map' || reason == 'next')
                f30Step('level_change') // TASK-239
            start(reason)
        },
        // a button. name: run, pause, restart, menu_open, menu_close, resume, map_open, map_close, map_level,
        // preview_play, next_level, speed_on, speed_off, editor_open, map_editor, line_delete_bin; value: srcId for map_level
        // and preview_play, else none
        ui(name, value)
        {
            if (name == 'pause' || name == 'menu_open' || name == 'map_open')
                f30Step(name) // TASK-239
            if (ptActive() && !drawMap)
            {
                if (name == 'speed_on' || name == 'speed_off')
                    ptEvent(name)
                return
            }
            if (uiActive())
                ANALYTICS.design('ui:' + name + ':' + ctxSegment(), value)
        },
        // line events (see the header); place() numbers the lines placed in the open attempt
        linePlaced()
        {
            f30Step('point2') // TASK-239
            if (ptActive())
                return void ptEvent('line_place', ++pt.a.placed)
            if (!active())
                return
            const a = attempt && attempt.srcId === srcId() ? attempt : null
            lineEvent('place', a ? ++a.placed : 1)
        },
        lineDeleted() { f30Step('line_delete'); ptActive() ? ptEvent('line_delete') : lineEvent('delete') },
        lineDragged(accepted) { f30Step('line_drag'); ptActive() ? ptEvent('line_drag', accepted ? 1 : 0) : lineEvent('drag', accepted ? 1 : 0) },
        lineRejectLimit() { f30Step('reject_limit'); lineEvent('reject_limit') },
        // frame time (ms, capped by the caller); counts only while playing(); sends every milestone crossed
        tick(ms)
        {
            if (!(ms > 0) || !playing())
                return
            playMs += ms
            while (milestone < PLAY_MILESTONES.length && playMs >= PLAY_MILESTONES[milestone] * 1000)
                ANALYTICS.design('session:play_seconds', PLAY_MILESTONES[milestone++])
        },
        playSeconds() { return playMs / 1000 },
        // visibilitychange to hidden
        hidden() { ANALYTICS.design('session:hide') },
        // pagehide: distinct levels with an attempt this session
        pageHide() { ANALYTICS.design('session:levels_seen', seen.size) },
        // the run starts (last line placed or the play box); an attempt without a run yet records the time.
        // players = player lines on the field -> lines:<srcId>:used
        run(players)
        {
            f30Step('run') // TASK-239
            if (ptActive())
            {
                ptEvent('run')
                if (pt.a.won)
                    ptAttempt()
                if (pt.a.runAt === null)
                    pt.a.runAt = now()
                return
            }
            if (!active())
                return
            if (typeof players == 'number')
                lineEvent('used', players)
            if (!open() || open().srcId !== srcId())
                start('resume')
            const a = open()
            if (a && a.runAt === null)
                a.runAt = now()
        },
        // first win of the open attempt (index.html gameMechanics, real levels only)
        win()
        {
            f30Step('win') // TASK-239
            if (ptActive())
            {
                if (!pt.a.won)
                {
                    pt.a.won = true
                    ptEvent('win', secs(now() - (pt.a.runAt === null ? now() : pt.a.runAt)))
                }
                return
            }
            const a = open()
            if (!active() || !a || a.won || a.srcId !== srcId())
                return
            a.won = true
            const e = entry(a.srcId)
            const first = e.wins == 0
            ++e.wins
            ANALYTICS.progression('Complete', 'L' + a.srcId)
            design(a.srcId, 'win', secs(now() - (a.runAt === null ? a.t0 : a.runAt)))
            design(a.srcId, 'win_attempt', a.n)
            if (first)
                design(a.srcId, 'first_win')
            end(null)
        },
        // after the automatic off-map restart: Fail + fail:offmap, then a new attempt (nothing behind a win window)
        offMap()
        {
            f30Step('offmap') // TASK-239
            if (ptActive())
            {
                if (!pt.a.won)
                {
                    ptEvent('offmap')
                    ptAttempt()
                }
                return
            }
            const a = open()
            if (!active() || !a || a.won)
                return
            design(a.srcId, 'fail:offmap')
            ++entry(a.srcId).offmap
            end('Fail')
            start('offmap')
        },
        // after a restart button: 'restart' (+ Fail for an unwon attempt), then a new attempt
        restart()
        {
            f30Step('restart') // TASK-239
            if (ptActive())
            {
                ptEvent('restart')
                return void ptAttempt()
            }
            if (!active())
                return
            const a = open(), id = a ? a.srcId : srcId()
            design(id, 'restart')
            ++entry(id).restarts
            if (a && !a.won)
                end('Fail')
            else
                end(null)
            start('restart')
        },
        // the player leaves the level: map opened, next level (before the new level starts), page hide
        leave()
        {
            if (!active())
                return void end(null)
            leave()
        },
        // the editor opens: the attempt ends without an event
        close()
        {
            end(null)
        },
    }
})()
