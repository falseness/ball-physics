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
// Per-user counters: PLATFORM.storage key STATS_STORE ('bp.stats.v1'), JSON
//   {[srcId]: {attempts, wins, restarts, offmap, abandons, seconds}}; seconds = time inside attempts (wall clock).
// Boot (index.html) reads the key with getMany and passes the values to TELEMETRY.load.
// Play-tests and the editor send and count nothing (active() is false there).
const STATS_STORE = 'bp.stats.v1'
const TELEMETRY = (function()
{
    let stats = {}
    let attempt = null // {srcId, n, t0, runAt, won, ended}

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
        attempt = {srcId: id, n, t0: now(), runAt: null, won: false, ended: false, reason}
        ANALYTICS.progression('Start', 'L' + id)
        design(id, 'attempt', n)
        save()
    }

    return {
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
        // the run starts (last line placed or the play box); an attempt without a run yet records the time
        run()
        {
            if (!active())
                return
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
