'use strict'
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
    font: 'Caveat',                                    // handwriting font family
    fontStack: '"Caveat", cursive'
})
window.THEME = THEME
// Page background behind the canvas (the canvas is not resized when the window grows,
// so the area around it must match the darkest background stop instead of white).
document.documentElement.style.background = THEME.bg[2]
if (document.body) document.body.style.background = THEME.bg[2]
