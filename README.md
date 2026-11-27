# ball-physics

## Font and logo

All game text uses **Finger Paint** (`fonts/finger-paint-400.woff2`, one 400 weight,
SIL Open Font License: `fonts/OFL-FingerPaint.txt`). The boot waits for it to load.

The logo in the pause menu and the level-complete window is drawn in code by
`drawLogo()` in `js/logo.js` (concept 129): a tilted 'Ball physics' title on a coral line,
purple portal B high-left and orange portal A low-right drawn as tunnel holes, and a
comet trail ending in the game ball, with faint dots into A. It is rendered once to an
offscreen canvas and redrawn only when the logo box, the pixel ratio or the font changes.

## Recording freezes in your own browser (`?visualsPerf=1`)

1. Open the game with `?visualsPerf=1` added to the address, e.g.
   `index.html?visualsPerf=1`. A small panel appears in the bottom-left corner.
2. Press **Start**, then play until a freeze happens. The panel counts freezes
   (frames over 50 ms), shows the worst one and the slowest layer of the last one.
3. Press **Export**. This stops the recording and downloads
   `visuals-performance.json`.
4. `python3 tools/freeze_report.py visuals-performance.json` labels each freeze.
   Each row shows the level (`thisLevel`), whether the ball was moving
   (`physics`) and the slowest timed layer (e.g. `lines`). Add `--json out.json`
   to also write the summary and rows as JSON.

Without the flag nothing is wrapped or recorded and no panel is shown. Nothing
is sent anywhere. The report format (schemaVersion 4) and every field are
described in the header of `js/visualsperf.js`. When the page is opened as a
file, `buildIdMethod` is `'globals'`. Chrome cannot fetch `file:` scripts, and it
logs one "Fetch API cannot load" console error per script when you press Start.
