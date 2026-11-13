# ball-physics
## Recording freezes in your own browser (`?visualsPerf=1`)

1. Open the game with `?visualsPerf=1` added to the address, e.g.
   `index.html?visualsPerf=1`. A small panel appears in the bottom-left corner.
2. Press **Start**, then play until a freeze happens. The panel counts freezes
   (frames over 50 ms), shows the worst one and the slowest layer of the last one.
3. Press **Export**. This stops the recording and downloads
   `visuals-performance.json`.
4. `python3 tools/freeze_report.py visuals-performance.json` labels each freeze.

Without the flag nothing is wrapped or recorded and no panel is shown. Nothing
is sent anywhere. The report format (schemaVersion 4) and every field are
described in the header of `js/visualsperf.js`. When the page is opened as a
file, `buildIdMethod` is `'globals'`. Chrome cannot fetch `file:` scripts, and it
logs one "Fetch API cannot load" console error per script when you press Start.
