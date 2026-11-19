# Level rubric: is a new level "interesting enough"?

Used by the level tickets (levels 18-22, TASK-129 onwards). A level passes only if **every hard gate G1-G4
passes** and the **subjective score passes**. All measurements use `tools/level_search.py` (placement through
the game's own `handleClick`, physics through `gameMechanics()` frames; see the tool's docstring). A level
that is still being designed is tested in-page with `--level INDEX --level-json FILE` (an editor export);
the final gates run on the committed `js/levels.js` entry (`--level INDEX` only).

Notation: `lineK` = the level's line count (2 or 3); the *reference* = the designer's k-line winning solution
(k = lineK), stored with the level ticket's evidence.

## Hard gates (metrics)

| Gate | Requirement | How to measure |
|------|-------------|----------------|
| **G1 – fewer lines cannot win** | No win with fewer than `lineK` lines. One line: `dense1` must simulate **>= 12000 valid** candidates and find **0 wins** (refinement included). For `lineK` 3 also two lines: `sample --lines 2` with **>= 10000 valid** pairs and **0 wins**. | `--mode dense1 --lines 1 [--step 40] [--shard i/n]` (+ `--mode merge`); `--mode sample --lines 2 --random 10000 --seed S` |
| **G2 – every line is needed** | Each drop-one-line variant of the reference **loses** (valid placement, no win). | `--mode necessity --lines lineK --solution REF` -> `allDropsLose: true` |
| **G3 – the reference is robust** | **>= 50 %** of the single-coordinate ±2 px variants of the reference win (`variantsWin / variants >= 0.5`); the reference itself wins. | `--mode local --lines lineK --solution REF` |
| **G4 – not trivially solvable, portals matter** | A random sample of **3000 valid** `lineK`-line candidates has a win rate **< 10 %**, and **every distinct win found has >= 1 teleport** (`winsWithoutTeleport == 0`). | `--mode sample --lines lineK --random 3000 --seed S` |

Notes:
- "valid" = every line of the candidate was accepted by the game exactly like a real click (snap, ball
  refusal, line count). Invalid candidates do not count towards the totals.
- G1 counts only simulated valid candidates; if the whole-field lattice at `--step 40` has fewer than 12000
  valid lines, use a finer step (or more shards) until the count is reached.
- A run ending at `--max-frames` (default 2000 frames, ~33 s of play) without a win counts as a loss; the
  reference must win well within it (see Flow).
- Record each gate as compact JSON with the command line, the counts the gate names and pass/fail.

## Subjective score (rubric)

Score each item 1-5 using the anchors below and write one sentence of justification per item.
**Pass = every item >= 3 and the mean >= 3.5.**

### Idea – one clear sentence, distinct from levels 1-17
- **1** No describable idea, or a copy of an existing level's idea with a different layout.
- **3** A clear one-sentence idea, but a close variant of an existing level (same portal use, same trick).
- **5** A clear one-sentence idea that no level 1-17 uses (new use of portal orientation, using a portal twice,
  redirecting the exit stream, speed gained through height, a gate passed twice ...).

### Aha – the solution is not obvious from the screenshot; each line does a different job
- **1** The solution is the first thing anyone would draw; the lines do the same job (e.g. two halves of one ramp).
- **3** Needs a moment of thought; the lines have different roles but one of them is obvious.
- **5** The winning idea becomes clear only after understanding how the portals redirect the ball; every line
  has a distinct, necessary role (catch, redirect, launch, guard ...).

### Readability – portal fronts, flag and obstacles readable, nothing under the HUD
- **1** Portal fronts ambiguous, flag or walls hard to see, or something under the HUD icons (top right).
- **3** Everything readable after a short look; minor clutter.
- **5** Instantly readable: portal fronts and pair obvious, the flag pocket and obstacles clear, generous
  space for the player's lines, nothing near the HUD.

### Flow – the winning run looks deliberate, not a lucky bounce chain; win within ~25 s of physics
- **1** The win is a chaotic bounce chain or takes far longer than 25 s (~1500 frames).
- **3** The run is mostly understandable, with one surprising bounce; win within ~25 s.
- **5** A clean, deliberate path (roll, drop, teleport, land) that the player can predict; win well within 25 s.

## Report template (per level)

```
G1 dense1: valid N (>= 12000) wins 0 [ + sample k=2: valid N (>= 10000) wins 0 ]   PASS/FAIL
G2 necessity: drops lose [true, true(, true)]                                        PASS/FAIL
G3 local ±2: variantsWin/variants = a/b (>= 0.5), reference win frame F              PASS/FAIL
G4 sample k=lineK: valid 3000, win rate r (< 0.10), winsWithoutTeleport 0            PASS/FAIL
Idea s/5, Aha s/5, Readability s/5, Flow s/5, mean m (every >= 3, mean >= 3.5)        PASS/FAIL
```
