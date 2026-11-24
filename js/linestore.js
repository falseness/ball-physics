'use strict'
// TASK-185: the player's lines per level, saved through the platform facade (platform.js, PLATFORM.storage).
// Key LINES_STORE holds JSON {[srcId]: {draft: [[x1, y1, x2, y2], ...], passed: [...] | null, sha}}.
//   draft  - the player's lines after the last draw / end drag / delete (saved by linesSaveDraft)
//   passed - the player's lines at the moment of the last real win (linesSavePassed), or null
//   sha    - levelGeometrySha(level) when the entry was written; an entry whose sha differs from the
//            current level's geometry (edited in the editor) is ignored.
// Boot (index.html) reads the key with getMany and passes the values to linesLoad. levelChoosed restores
// passed, else draft, else nothing (linesRestore), at most lineK lines. Entries are keyed by srcId, never by
// play-order index. The editor and play-tests never read or write this key.
const LINES_STORE = 'bp.lines.v1'
let linesStore = {}

// values: the PLATFORM.storage.getMany result ({key: string | null}); garbage means an empty store
function linesLoad(values)
{
    linesStore = {}
    try
    {
        const v = JSON.parse(values && values[LINES_STORE])
        if (v && typeof v == 'object' && !Array.isArray(v))
            linesStore = v
    }
    catch (e) { linesStore = {} }
}
// FNV-1a (32 bit, hex) of the level's own geometry: its lines, portals, ball start and flag
function levelGeometrySha(L)
{
    const g = JSON.stringify([
        (L.lines || []).map(l => [l.posX, l.posY, l.posX2, l.posY2]),
        (L.portals || []).map(p => [p.line, p.u, p.side, p.h]),
        [L.ballX, L.ballY], [L.flagX, L.flagY, L.flagRotate || 0]])
    let h = 0x811c9dc5
    for (let i = 0; i < g.length; ++i)
    {
        h ^= g.charCodeAt(i)
        h = Math.imul(h, 0x01000193) >>> 0
    }
    return ('0000000' + h.toString(16)).slice(-8)
}
function linesActive()
{
    return !playtestLevel && !editorMode && levels[thisLevel] !== undefined
}
function playerLineCoords()
{
    return lines.filter(l => l.type == 'player').map(l => [l.posX, l.posY, l.posX2, l.posY2])
}
// the entry of levels[i] for writing: a missing entry or one for other geometry starts fresh
function linesEntry(i)
{
    const L = levels[i], sha = levelGeometrySha(L)
    let e = linesStore[L.srcId]
    if (!e || typeof e != 'object' || e.sha !== sha)
        e = linesStore[L.srcId] = { draft: [], passed: null, sha }
    return e
}
function linesWrite()
{
    try
    {
        const p = PLATFORM.storage.setMany({ [LINES_STORE]: JSON.stringify(linesStore) })
        if (p && p.catch)
            p.catch(function() {})
        return p
    }
    catch (e) { return Promise.resolve(false) } // blocked storage: keep playing, the in-memory copy stays
}
// after a draw, end drag or delete of a player line (not in play-tests / the editor)
function linesSaveDraft()
{
    if (!linesActive())
        return
    linesEntry(thisLevel).draft = playerLineCoords()
    return linesWrite()
}
// on a real win: the player's lines at that moment
function linesSavePassed()
{
    if (!linesActive())
        return
    const e = linesEntry(thisLevel)
    e.passed = playerLineCoords()
    return linesWrite()
}
function linesValid(a)
{
    return Array.isArray(a) && a.every(c => Array.isArray(c) && c.length == 4 && c.every(Number.isFinite))
}
// lines to show for levels[i]: passed (rule b), else draft (rule a), else none; at most lineK
function linesSaved(i)
{
    const L = levels[i]
    const e = L && linesStore[L.srcId]
    if (!e || typeof e != 'object' || e.sha !== levelGeometrySha(L))
        return []
    const src = linesValid(e.passed) ? e.passed : linesValid(e.draft) ? e.draft : []
    return src.slice(0, Math.max(0, L.lineK | 0))
}
// levelChoosed: rebuild the player Line objects of levels[i] and set linesK from them
function linesRestore(i)
{
    if (playtestLevel || editorMode)
        return
    const saved = linesSaved(i)
    for (const c of saved)
    {
        const l = new Line(c[0], c[1], c[2], c[3], dotRadius, '#0000ff', 'line')
        l.type = 'player'
        lines.push(l)
    }
    linesK = saved.length
}
