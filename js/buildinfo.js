// Build id (TASK-190): '<git short sha>-<YYYYMMDD>'. tools/stamp_build.py
// rewrites the line below in a release copy; the repo keeps it empty and an
// unstamped page uses 'dev-<YYYYMMDD of today>' (analyticsBuild in index.html).
// gameanalytics.js reads BUILD_CONFIG.build as the GameAnalytics build name.
var BUILD_CONFIG = {build: ''}
