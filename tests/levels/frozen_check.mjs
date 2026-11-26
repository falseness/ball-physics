// TASK-243: frozen level layouts. The user asked to undo the TASK-202..212 layout changes ("undo change to levels
// pls"); srcId 1, 2, 3, 9, 11, 13, 15, 19, 21, 27, 30 were restored to their definitions at git 5685fc4^ and must
// not be edited again (docs/level_rubric.md, 'Frozen layouts').
//
// Usage: node tests/levels/frozen_check.mjs [--levels FILE]       check FILE (default js/levels.js) against frozen.json
//        node tests/levels/frozen_check.mjs --write-from FILE      write frozen.json from FILE (e.g. git show 5685fc4^:js/levels.js)
//        node tests/levels/frozen_check.mjs --dump [--levels FILE] print {srcId: normalised level} for every level
// Loads levels.js the way the game does (one plain script scope; Line, PLATFORM and GAME_W/GAME_H stubbed), normalises
// each level (JSON of its fields with sorted keys, lines as [x1, y1, x2, y2] arrays, srcId left out) and compares a
// sha256 per frozen srcId. Exit 0 = all equal, 1 = a mismatch or missing level (named), 2 = usage/load error.
import fs from 'fs'
import path from 'path'
import vm from 'vm'
import crypto from 'crypto'
import { fileURLToPath } from 'url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(HERE, '..', '..')
const FROZEN = path.join(HERE, 'frozen.json')
const SET = [1, 2, 3, 9, 13, 15, 19, 21, 30] // TASK-247: srcId 11 and 27 were removed from the game
const args = process.argv.slice(2)
const opt = name => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null }

function load(file)
{
    const ctx = {
        console, Math, JSON, GAME_W: 1280, GAME_H: 800, dotRadius: 5, levelLineColor: '#000',
        Line: class { constructor(x1, y1, x2, y2, r, color, type) { Object.assign(this, { x1, y1, x2, y2, r, color, type }) } },
        PLATFORM: { storage: { getMany() { return {} }, setMany() {} } }
    }
    const gw = /const\s+GAME_W\s*=\s*(\d+)\s*,\s*GAME_H\s*=\s*(\d+)/.exec(fs.readFileSync(path.join(ROOT, 'js', 'theme.js'), 'utf8'))
    if (gw) { ctx.GAME_W = +gw[1]; ctx.GAME_H = +gw[2] }
    vm.createContext(ctx)
    vm.runInContext(fs.readFileSync(file, 'utf8') + '\n;this.__levels = levels', ctx)
    return ctx.__levels
}
function sortKeys(v)
{
    if (Array.isArray(v)) return v.map(sortKeys)
    if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map(k => [k, sortKeys(v[k])]))
    return v
}
function normalise(l)
{
    const o = {}
    for (const k of Object.keys(l)) if (k !== 'srcId') o[k] = l[k]
    if (o.lines) o.lines = o.lines.map(s => [s.x1, s.y1, s.x2, s.y2])
    return sortKeys(o)
}
function table(file)
{
    const t = {}
    for (const l of load(file)) t[l.srcId] = normalise(l)
    return t
}
const sha = o => crypto.createHash('sha256').update(JSON.stringify(o)).digest('hex')

try
{
    if (args.includes('--write-from'))
    {
        const src = path.resolve(opt('--write-from')), t = table(src)
        const out = { source: opt('--source') || src, srcIds: SET, sha256: Object.fromEntries(SET.map(n => [n, sha(t[n])])) }
        fs.writeFileSync(FROZEN, JSON.stringify(out, null, 1) + '\n')
        console.log('wrote', FROZEN, JSON.stringify(out.sha256))
        process.exit(0)
    }
    const file = path.resolve(opt('--levels') || path.join(ROOT, 'js', 'levels.js'))
    const t = table(file)
    if (args.includes('--dump')) { console.log(JSON.stringify(t)); process.exit(0) }
    const frozen = JSON.parse(fs.readFileSync(FROZEN, 'utf8'))
    const bad = []
    for (const n of frozen.srcIds)
    {
        const got = t[n] ? sha(t[n]) : 'missing'
        const ok = got === frozen.sha256[n]
        console.log(`${ok ? 'PASS' : 'FAIL'} srcId ${n} ${got.slice(0, 16)}${ok ? '' : ' expected ' + frozen.sha256[n].slice(0, 16)}`)
        if (!ok) bad.push(n)
    }
    console.log(bad.length ? `FROZEN MISMATCH srcId ${bad.join(',')} (${file})` : `FROZEN OK ${frozen.srcIds.length}/${frozen.srcIds.length} (${file})`)
    process.exit(bad.length ? 1 : 0)
}
catch (e) { console.log('ERROR', e.message); process.exit(2) }
