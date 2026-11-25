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
//   editor:open:<ctx>:<from>         from = 'menu' (pause menu) | 'win' (completion window)
//   editor:sum:<ctx>:<h>:lines       value = level lines      } sent at play, export and exit,
//   editor:sum:<ctx>:<h>:portals     value = portals (0 | 2)  } before the action itself
//   editor:sum:<ctx>:<h>:linek       value = lineK            }
//   editor:sum:<ctx>:<h>:changed     value = 1 if editorLevelToJSON differs from the copy taken at open, else 0
//   editor:actions:<ctx>             value = toolbar button clicks + object edits this session (before exit / abandon)
//   editor:exit:<ctx>                value = seconds in the editor since open, play-test time excluded
//   editor:abandon:<ctx>             pagehide while the editor is open (not during a play-test), value = seconds
// Per-user counters: PLATFORM.storage key STATS_STORE ('bp.stats.v1'), JSON
//   {[srcId]: {attempts, wins, restarts, offmap, abandons, seconds}}; seconds = time inside attempts (wall clock).
// Boot (index.html) reads the key with getMany and passes the values to TELEMETRY.load.
// Play-tests and the editor send and count nothing (active() is false there).
const STATS_STORE = 'bp.stats.v1'
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

    return {
        editor: editorEvent,
        editorActive,
        levelHash,
        editorSession() { return ed },
        // editorOpen (editor.level is the fresh copy, editorMode on); from = 'menu' | 'win'
        editorOpened(from)
        {
            if (!editorActive())
                return
            ed = {ctx: 'L' + srcId(), t0: now(), json0: editorLevelToJSON(editor.level), actions: 0, playAt: null, playMs: 0}
            editorEvent('open:' + ed.ctx + ':' + from)
        },
        // a toolbar button click or an object edit (a field click / drop / key that changed the working copy)
        editorAction()
        {
            if (ed && editorActive())
                ++ed.actions
        },
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
            start(reason)
        },
        // a button. name: run, pause, restart, menu_open, menu_close, resume, map_open, map_close, map_level,
        // preview_play, next_level, speed_on, speed_off, editor_open, line_delete_bin; value: srcId for map_level
        // and preview_play, else none
        ui(name, value)
        {
            if (uiActive())
                ANALYTICS.design('ui:' + name + ':' + ctxSegment(), value)
        },
        // line events (see the header); place() numbers the lines placed in the open attempt
        linePlaced()
        {
            if (!active())
                return
            const a = attempt && attempt.srcId === srcId() ? attempt : null
            lineEvent('place', a ? ++a.placed : 1)
        },
        lineDeleted() { lineEvent('delete') },
        lineDragged(accepted) { lineEvent('drag', accepted ? 1 : 0) },
        lineRejectLimit() { lineEvent('reject_limit') },
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
