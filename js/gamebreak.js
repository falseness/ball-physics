/*
Сделай гейм брейки после рестарта или перехода на след уровень
Сделай в меню показ уровней и отмечай уже пройденные
Сделай еще хотя бы 4 уровня
*/

let levelCompletedWindow = false
function levelCompleted()
{
    if (levelCompletedWindow)
    {
        // Same look and layout code as the pause menu (menuLayout('win'), js/menu.js); the click handler in
        // index.html hit-tests the same rects (menuButtonAt('win', ...)).
        applyViewTransform()
        eclipse()
        drawMenuLayout('win')
    }
}
