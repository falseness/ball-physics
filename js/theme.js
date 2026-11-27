'use strict'
// Fixed logical game resolution: all game/drawing coordinates are GAME_W x GAME_H.
// fitCanvas() (index.html) letterbox-scales the canvas to the window with CSS and sizes
// its backing store to the on-screen size x devicePixelRatio (drawing uses a k transform).
const GAME_W = 1280, GAME_H = 800
// Visual theme tokens for the "61 Noir" style (engineering pad glowing on navy).
// Loaded before every other game script; purely visual, no gameplay values here.
const THEME = Object.freeze({
    bg: ['#071a30', '#0b2747', '#040f1e'],            // diagonal background gradient stops
    blot: ['rgba(40,110,190,0.10)', 'rgba(0,5,15,0.18)'], // soft exposure blotches (light / dark)
    grid: Object.freeze({
        minor: 'rgba(92,200,255,0.07)',
        major: 'rgba(92,200,255,0.20)'
    }),
    ink: '#e9f6ff',                                    // ice ink: level lines, ball, text
    coral: '#ff6a55',                                  // player lines, flag, accents
    soft: '#9fc6e6',                                   // secondary ink: hints, annotations
    cyan: 'rgba(130,210,255,0.9)',                     // HUD outlines, path preview
    physicsOn: '#59f0a0',                              // start triangle while physics runs
    font: 'Finger Paint',                              // game font family (single 400 weight, no bold)
    fontStack: '"Finger Paint", cursive'
})
window.THEME = THEME
// Page background behind the canvas (fills the letterbox bars around the scaled canvas).
document.documentElement.style.background = THEME.bg[2]
if (document.body) document.body.style.background = THEME.bg[2]
