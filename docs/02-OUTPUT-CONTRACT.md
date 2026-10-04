# Part 2 - Output contract (per capture)

Every capture, at every tier, must produce:

- Dimensioned per-room plan: walls, ceiling height, floor area, openings
- Stitched multi-room plan with correct adjacency
- Per-surface damage regions with class + metric extent
- Concealed-damage flags with the rule that fired
- Scope line items keyed to surfaces
- Confidence interval on EVERY measurement
- One command per capture
- JSON to the published schema
- Rendered plan

The stitched plan is the product surface: one whole-property floor plan a homeowner would recognise from poly.cam or magicplan, with every room placed, connected and dimensioned, produced from every tier including photos.
