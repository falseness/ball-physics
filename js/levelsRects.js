// TASK-181: the old 8-column square grid is gone; levels are picked on the route map (js/mapdraw.js,
// hit boxes from js/routemap.js routeSlotBox). levelPick() is the one path that starts a level from a menu
// (the old levelsRectCollision body): thisLevel is set, a play-test ends, and every menu closes.
function levelPick(i)
{
    thisLevel = i
    playtestLevel = null // picking a real level ends a play-test
    levelChoosed(thisLevel)
    drawMenu = false
    drawMap = false
    levelCompletedWindow = false
    drawMenuIcon = true
}
