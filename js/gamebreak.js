/*
Сделай гейм брейки после рестарта или перехода на след уровень
Сделай в меню показ уровней и отмечай уже пройденные
Сделай еще хотя бы 4 уровня
*/

let levelCompletedWindow = false
let blocks = [295, 370, 455]
function levelCompleted()
{
    if (levelCompletedWindow)
    {
        applyViewTransform()
        // Same look as the pause menu: navy overlay, dark glass panel, cyan outlined buttons.
        // Button rects are exactly the ones the click handler in index.html tests (blocks[1], blocks[2]).
        const bx = menuCoords[0] + (menuSize[0] - menuTextRect[0]) / 2
        const cx = menuCoords[0] + menuSize[0] / 2
        eclipse()
        glassPanel(menuCoords[0], menuCoords[1], menuSize[0], menuSize[1])
        menuLabel('Level completed!', cx, menuCoords[1] + blocks[0] + menuTextRect[1] / 2, 38, THEME.coral)
        if (playtestLevel)
            menuButton(bx, menuCoords[1] + blocks[1], menuTextRect[0], menuTextRect[1], 'editor')
        else if (thisLevel + 1 < levels.length)
            menuButton(bx, menuCoords[1] + blocks[1], menuTextRect[0], menuTextRect[1], 'next level')
        else
            menuLabel('Thanks for playing!', cx, menuCoords[1] + blocks[1] + menuTextRect[1] / 2, 34, THEME.soft)
        menuButton(bx, menuCoords[1] + blocks[2], menuTextRect[0], menuTextRect[1], 'restart')
        drawLevels()
        drawLogo()
        // same small 'editor' button and rect as the pause menu; in play-test the 'editor' button
        // above (in place of 'next level') is the way back, so no duplicate
        if (!playtestLevel)
        {
            const er = editorButtonRect()
            menuButton(er[0], er[1], er[2], er[3], 'editor')
        }
    }
}
