# Part 4 - Fix loop (25% of score)

Acknowledge a one-page fix declaration:

1. Single worst-performing gate in your own benchmark, with the failing number
2. Root-cause hypothesis + evidence
3. Intended fix + predicted number after it

Then ship it. Final submission contains before run, after run (both regenerable), readable diff.

Scoring:
- Correct root cause + shipped fix + gate fail->pass: full marks
- Correct root cause + shipped fix + meaningful movement short of gate: majority marks when report says why it fell short
- Prediction badly wrong either direction: marks for post-mortem honesty, none for prediction
- Analysis with no shipped fix: zero regardless of quality
- Fix with no regenerable before/after: zero
